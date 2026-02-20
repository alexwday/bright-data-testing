from __future__ import annotations

import json
import os
import time
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "tool_calls.jsonl"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(exist_ok=True)


def log_tool_call(
    conversation_id: str,
    tool_name: str,
    tool_args: dict,
    tool_result: dict,
    duration_ms: int,
    token_usage: dict | None = None,
) -> None:
    """Append a structured tool-call record to the JSONL log."""
    _ensure_log_dir()
    record = {
        "timestamp": time.time(),
        "conversation_id": conversation_id,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_result": tool_result,
        "duration_ms": duration_ms,
    }
    if token_usage:
        record["token_usage"] = token_usage
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def log_llm_call(
    conversation_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: int,
    tool_calls_count: int = 0,
) -> None:
    """Append a structured LLM-call record to the JSONL log."""
    _ensure_log_dir()
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
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
