from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # user, assistant, tool_activity, file, system
    content: str
    timestamp: float = field(default_factory=time.time)
    # tool_activity metadata
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    tool_duration_ms: int | None = None
    # file metadata
    filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_name:
            d["tool_name"] = self.tool_name
            d["tool_args"] = self.tool_args
            d["tool_result"] = self.tool_result
            d["tool_duration_ms"] = self.tool_duration_ms
        if self.filename:
            d["filename"] = self.filename
            d["file_path"] = self.file_path
            d["file_size"] = self.file_size
        return d


@dataclass
class Conversation:
    """Multi-turn conversation state."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[ChatMessage] = field(default_factory=list)
    openai_messages: list[dict] = field(default_factory=list)
    is_processing: bool = False

    def add_user_message(self, content: str) -> ChatMessage:
        msg = ChatMessage(role="user", content=content)
        self.messages.append(msg)
        self.openai_messages.append({"role": "user", "content": content})
        return msg

    def add_assistant_message(self, content: str) -> ChatMessage:
        msg = ChatMessage(role="assistant", content=content)
        self.messages.append(msg)
        # openai_messages managed by the loop (includes tool_calls etc.)
        return msg

    def add_tool_activity(
        self,
        tool_name: str,
        tool_args: dict,
        tool_result: dict,
        duration_ms: int,
    ) -> ChatMessage:
        content = f"Called {tool_name}"
        msg = ChatMessage(
            role="tool_activity",
            content=content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            tool_duration_ms=duration_ms,
        )
        self.messages.append(msg)
        return msg

    def add_file_message(
        self, filename: str, file_path: str, file_size: int
    ) -> ChatMessage:
        content = f"Downloaded {filename}"
        msg = ChatMessage(
            role="file",
            content=content,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
        )
        self.messages.append(msg)
        return msg

    def add_system_message(self, content: str) -> ChatMessage:
        msg = ChatMessage(role="system", content=content)
        self.messages.append(msg)
        # System verification messages get injected into openai context too
        self.openai_messages.append({"role": "user", "content": f"[SYSTEM CHECK] {content}"})
        return msg

    def get_messages_since(self, index: int) -> list[dict]:
        return [m.to_dict() for m in self.messages[index:]]
