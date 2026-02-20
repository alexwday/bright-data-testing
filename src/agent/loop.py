"""Multi-turn chat agent loop."""

from __future__ import annotations

import json
import logging
import time

from src.config.settings import get_config
from src.infra.llm import get_openai_client, resolve_chat_runtime
from src.tools import bright_data
from src.tools.definitions import TOOLS

from .logger import log_agent_event, log_llm_call, log_tool_call
from .models import Conversation
from .prompts import build_system_prompt

logger = logging.getLogger(__name__)

TOOL_DISPATCH = {
    "search": bright_data.search,
    "scrape_page": bright_data.scrape_page,
    "download_file": bright_data.download_file,
}

# Size thresholds for verification warnings
_MIN_SIZES = {".pdf": 20_000, ".xlsx": 5_000, ".xls": 5_000}


def process_message(conversation: Conversation) -> None:
    """Process the latest user message in a conversation.

    Runs the LLM loop: call model, handle tool calls, repeat until the model
    produces a final text response or we hit the tool call limit.
    Appends all messages (assistant, tool_activity, file, system) to the
    conversation as it goes.
    """
    cfg = get_config()
    client = get_openai_client()
    model_name, max_tokens, auth_mode = resolve_chat_runtime(cfg)
    log_agent_event(
        conversation.id,
        "conversation_started",
        {
            "model": model_name,
            "auth_mode": auth_mode,
            "request_max_tokens": max_tokens,
            "max_tool_calls": cfg.agent.max_tool_calls,
            "temperature": cfg.agent.temperature,
        },
    )

    # Ensure system prompt is first message in openai context
    if not conversation.openai_messages or conversation.openai_messages[0].get("role") != "system":
        system_prompt = build_system_prompt()
        conversation.openai_messages.insert(0, {"role": "system", "content": system_prompt})

    tool_call_count = 0
    max_calls = cfg.agent.max_tool_calls
    download_cache: dict[tuple[str, str], dict] = {}
    emitted_file_names: set[str] = set()

    try:
        while tool_call_count < max_calls:
            # Call LLM
            llm_start = time.time()
            request_kwargs = {
                "model": model_name,
                "messages": conversation.openai_messages,
                "tools": TOOLS,
                "temperature": cfg.agent.temperature,
            }
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens
            response = client.chat.completions.create(**request_kwargs)
            llm_duration = int((time.time() - llm_start) * 1000)

            choice = response.choices[0]
            assistant_msg = choice.message
            usage = response.usage
            finish_reason = getattr(choice, "finish_reason", None)
            tool_names = [tc.function.name for tc in (assistant_msg.tool_calls or [])]

            log_llm_call(
                conversation_id=conversation.id,
                model=model_name,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                duration_ms=llm_duration,
                tool_calls_count=len(assistant_msg.tool_calls or []),
                finish_reason=str(finish_reason) if finish_reason is not None else None,
                response_preview=(assistant_msg.content or ""),
                request_max_tokens=max_tokens,
                auth_mode=auth_mode,
                tool_names=tool_names,
            )

            # No tool calls — final text response
            if not assistant_msg.tool_calls:
                text = assistant_msg.content or ""
                log_agent_event(
                    conversation.id,
                    "loop_stopped_no_tool_calls",
                    {
                        "finish_reason": str(finish_reason) if finish_reason is not None else None,
                        "tool_call_count_total": tool_call_count,
                        "response_preview": text,
                    },
                )
                conversation.add_assistant_message(text)
                conversation.openai_messages.append({"role": "assistant", "content": text})
                break

            # Has tool calls — add assistant message to openai context
            log_agent_event(
                conversation.id,
                "llm_requested_tools",
                {"tool_names": tool_names, "count": len(tool_names)},
            )
            conversation.openai_messages.append(assistant_msg.model_dump())

            # If the assistant also included text, show it
            if assistant_msg.content:
                conversation.add_assistant_message(assistant_msg.content)

            # Execute each tool call
            for tc in assistant_msg.tool_calls:
                tool_call_count += 1
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                fn = TOOL_DISPATCH.get(fn_name)
                if fn is None:
                    result = {"error": f"Unknown tool: {fn_name}"}
                    duration_ms = 0
                else:
                    download_key: tuple[str, str] | None = None
                    if fn_name == "download_file":
                        download_key = (
                            str(fn_args.get("url", "")),
                            str(fn_args.get("filename", "")).casefold(),
                        )
                        cached = download_cache.get(download_key)
                        if cached:
                            result = {
                                **cached,
                                "deduplicated": True,
                                "deduplicated_reason": "Skipped duplicate download_file call for identical url+filename.",
                            }
                            duration_ms = 0
                        else:
                            t0 = time.time()
                            result = fn(**fn_args)
                            duration_ms = int((time.time() - t0) * 1000)
                            if result.get("success"):
                                download_cache[download_key] = result
                    else:
                        t0 = time.time()
                        result = fn(**fn_args)
                        duration_ms = int((time.time() - t0) * 1000)

                # Log tool call
                log_tool_call(
                    conversation_id=conversation.id,
                    tool_name=fn_name,
                    tool_args=fn_args,
                    tool_result=result,
                    duration_ms=duration_ms,
                )

                # Add tool activity to conversation (for UI)
                conversation.add_tool_activity(fn_name, fn_args, result, duration_ms)

                # Handle successful downloads
                if (
                    fn_name == "download_file"
                    and result.get("success")
                    and not result.get("deduplicated")
                ):
                    warning = _verify_download(result)
                    if warning:
                        conversation.add_system_message(warning)
                    else:
                        file_key = str(result.get("filename", "")).casefold()
                        if file_key not in emitted_file_names:
                            emitted_file_names.add(file_key)
                            conversation.add_file_message(
                                filename=result["filename"],
                                file_path=result["path"],
                                file_size=result["size_bytes"],
                            )

                # Add tool result to openai context
                result_str = json.dumps(result, default=str)
                # Truncate very large results for context window
                if len(result_str) > 15000:
                    result_str = result_str[:15000] + "... [truncated]"
                conversation.openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        else:
            # Hit max tool calls
            log_agent_event(
                conversation.id,
                "loop_stopped_max_tool_calls",
                {"max_tool_calls": max_calls, "tool_call_count_total": tool_call_count},
            )
            conversation.add_system_message(
                f"Reached maximum of {max_calls} tool calls. Stopping."
            )

    except Exception as exc:
        log_agent_event(
            conversation.id,
            "loop_exception",
            {"error": str(exc), "tool_call_count_total": tool_call_count},
        )
        logger.exception("Agent error in conversation %s", conversation.id)
        conversation.add_system_message(f"Error: {exc}")


def _verify_download(result: dict) -> str | None:
    """Check a download result for suspicious signals. Returns warning or None."""
    warnings = []
    filename = result.get("filename", "")
    size = result.get("size_bytes", 0)

    # Check file size
    ext = ""
    for e in _MIN_SIZES:
        if filename.lower().endswith(e):
            ext = e
            break
    if ext and size < _MIN_SIZES[ext]:
        warnings.append(
            f"File size ({size:,} bytes) is suspiciously small for a {ext.upper()} file. "
            f"Expected at least {_MIN_SIZES[ext]:,} bytes. The URL may have returned an error page."
        )

    # Check file content inspection results
    if result.get("warning"):
        warnings.append(result["warning"])

    if warnings:
        return "DOWNLOAD VERIFICATION WARNING:\n" + "\n".join(f"- {w}" for w in warnings)
    return None
