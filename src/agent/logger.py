from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "tool_calls.jsonl"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(exist_ok=True)


def _truncate_text(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"


def _sanitize_for_log(value: Any) -> Any:
    """Keep logs informative while avoiding massive payloads."""
    if isinstance(value, str):
        return _truncate_text(value)

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, str) and key in {"content", "first_pages_text", "first_pages_preview"}:
                out[f"{key}_full_length"] = len(item)
                out[key] = _truncate_text(item)
            else:
                out[key] = _sanitize_for_log(item)
        return out

    if isinstance(value, list):
        limit = 50
        if len(value) <= limit:
            return [_sanitize_for_log(v) for v in value]
        return [_sanitize_for_log(v) for v in value[:limit]] + [
            f"... [truncated {len(value) - limit} items]"
        ]

    return value


def _append_record(record: dict[str, Any]) -> None:
    _ensure_log_dir()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def log_tool_call(
    conversation_id: str,
    tool_name: str,
    tool_args: dict,
    tool_result: dict,
    duration_ms: int,
    token_usage: dict | None = None,
) -> None:
    """Append a structured tool-call record to the JSONL log."""
    record = {
        "timestamp": time.time(),
        "conversation_id": conversation_id,
        "type": "tool_call",
        "tool_name": tool_name,
        "tool_args": _sanitize_for_log(tool_args),
        "tool_result": _sanitize_for_log(tool_result),
        "duration_ms": duration_ms,
    }
    if token_usage:
        record["token_usage"] = _sanitize_for_log(token_usage)
    _append_record(record)


def log_llm_call(
    conversation_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: int,
    tool_calls_count: int = 0,
    finish_reason: str | None = None,
    response_preview: str | None = None,
    request_max_tokens: int | None = None,
    auth_mode: str | None = None,
    tool_names: list[str] | None = None,
) -> None:
    """Append a structured LLM-call record to the JSONL log."""
    record = {
        "timestamp": time.time(),
        "conversation_id": conversation_id,
        "type": "llm_call",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "duration_ms": duration_ms,
        "tool_calls_count": tool_calls_count,
    }
    if finish_reason is not None:
        record["finish_reason"] = finish_reason
    if response_preview is not None:
        record["response_preview"] = _truncate_text(response_preview, limit=800)
    if request_max_tokens is not None:
        record["request_max_tokens"] = request_max_tokens
    if auth_mode is not None:
        record["auth_mode"] = auth_mode
    if tool_names is not None:
        record["tool_names"] = _sanitize_for_log(tool_names)
    _append_record(record)


def log_agent_event(
    conversation_id: str,
    event: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a lifecycle/debug event record for a conversation."""
    record = {
        "timestamp": time.time(),
        "conversation_id": conversation_id,
        "type": "agent_event",
        "event": event,
    }
    if details:
        record["details"] = _sanitize_for_log(details)
    _append_record(record)
