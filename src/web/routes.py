"""API routes and ChatStore for the chat UI."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.agent.loop import process_message
from src.agent.models import Conversation
from src.agent.prompts import build_system_prompt
from src.config.settings import get_config
from src.tools.definitions import TOOLS

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ── ChatStore ──────────────────────────────────────────────────────────────

class ChatStore:
    """Thread-safe store for chat conversations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._conversations: dict[str, Conversation] = {}

    def create(self) -> Conversation:
        conv = Conversation()
        with self._lock:
            self._conversations[conv.id] = conv
        return conv

    def get(self, chat_id: str) -> Conversation | None:
        with self._lock:
            return self._conversations.get(chat_id)

    def get_messages_since(self, chat_id: str, since: int) -> dict | None:
        with self._lock:
            conv = self._conversations.get(chat_id)
            if not conv:
                return None
            return {
                "id": conv.id,
                "messages": conv.get_messages_since(since),
                "total_messages": len(conv.messages),
                "is_processing": conv.is_processing,
            }


_store = ChatStore()


# ── Background processor ──────────────────────────────────────────────────

def _process_chat(chat_id: str):
    """Process the latest user message in a background thread."""
    conv = _store.get(chat_id)
    if not conv:
        return
    try:
        process_message(conv)
    finally:
        conv.is_processing = False


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    static_dir = Path(__file__).parent / "static"
    js_ver = int((static_dir / "app.js").stat().st_mtime)
    css_ver = int((static_dir / "style.css").stat().st_mtime)
    return _templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "asset_version": max(js_ver, css_ver),
        },
    )


@router.post("/api/chat")
async def send_message(request: Request):
    """Send a message to a chat. Creates a new chat if no id provided."""
    body = await request.json()
    message = body.get("message", "").strip()
    chat_id = body.get("chat_id")

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Get or create conversation
    if chat_id:
        conv = _store.get(chat_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Chat not found")
        if conv.is_processing:
            raise HTTPException(status_code=409, detail="Chat is still processing")
    else:
        conv = _store.create()

    # Add user message
    conv.add_user_message(message)
    conv.is_processing = True

    # Process in background thread
    thread = threading.Thread(target=_process_chat, args=(conv.id,), daemon=True)
    thread.start()

    return {"chat_id": conv.id}


@router.get("/api/chat/{chat_id}")
async def get_chat(chat_id: str, since: int = 0):
    """Poll for new messages. Returns messages since the given index."""
    data = _store.get_messages_since(chat_id, since)
    if data is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return data


@router.get("/api/config/prompts")
async def get_prompts():
    """Return prebuilt prompts for the sidebar."""
    cfg = get_config()
    return [
        {
            "id": p.id,
            "label": p.label,
            "message": p.message,
            "prefill": p.prefill,
        }
        for p in cfg.prebuilt_prompts
    ]


@router.get("/api/config/system")
async def get_system_config():
    """Return full system transparency: prompt, tools, agent config."""
    cfg = get_config()
    return {
        "system_prompt": build_system_prompt(),
        "tools": TOOLS,
        "agent": {
            "model": cfg.agent.model,
            "max_tool_calls": cfg.agent.max_tool_calls,
            "temperature": cfg.agent.temperature,
        },
        "prebuilt_prompts": [
            {
                "id": p.id,
                "label": p.label,
                "message": p.message,
                "prefill": p.prefill,
            }
            for p in cfg.prebuilt_prompts
        ],
    }


@router.get("/api/files/download")
async def download_file(path: str):
    """Serve a downloaded file.

    Accepts basename links (preferred) and normalizes legacy absolute/relative
    paths emitted by the model in older responses.
    """
    dl_dir = Path(get_config().download.base_dir).resolve()
    raw_path = (path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="File path is required")

    normalized = unquote(raw_path).replace("\\", "/").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="File path is required")

    provided = Path(normalized)
    candidate_paths: list[Path] = []

    # 1) Direct absolute path if it still points inside downloads.
    if provided.is_absolute():
        candidate_paths.append(provided.resolve())
    else:
        # 2) Relative path under downloads (handles nested paths if present).
        candidate_paths.append((dl_dir / provided).resolve())

    # 3) Basename fallback for links that include absolute/nested prefixes.
    basename = provided.name
    if basename:
        candidate_paths.append((dl_dir / basename).resolve())

    filepath: Path | None = None
    for candidate in candidate_paths:
        if str(candidate).startswith(str(dl_dir)) and candidate.exists():
            filepath = candidate
            break

    if filepath is None:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath, filename=filepath.name)
