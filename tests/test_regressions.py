from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.agent.loop import process_message
from src.agent.models import Conversation
from src.tools import bright_data
from src.web.app import create_app
from src.web.routes import _store


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, args: dict):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=json.dumps(args))


class _FakeAssistantMessage:
    def __init__(self, content: str | None, tool_calls: list[_FakeToolCall] | None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self) -> dict:
        serialized_calls = []
        for tc in self.tool_calls or []:
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
            )
        return {"role": "assistant", "content": self.content, "tool_calls": serialized_calls}


class _FakeCompletions:
    def __init__(self, responses: list[_FakeAssistantMessage]):
        self._responses = responses

    def create(self, **_: dict) -> SimpleNamespace:
        msg = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )


class _FakeOpenAIClient:
    def __init__(self, responses: list[_FakeAssistantMessage]):
        self.chat = SimpleNamespace(completions=_FakeCompletions(responses))


class RegressionTests(unittest.TestCase):
    def test_send_message_sets_processing_before_worker_thread_starts(self):
        app = create_app()

        class _FakeThread:
            def __init__(self, *args, **kwargs):
                self.started = False

            def start(self):
                self.started = True

        with patch("src.web.routes.threading.Thread", _FakeThread):
            with TestClient(app) as client:
                resp = client.post("/api/chat", json={"message": "test"})
                self.assertEqual(resp.status_code, 200)
                chat_id = resp.json()["chat_id"]

        conv = _store.get(chat_id)
        self.assertIsNotNone(conv)
        self.assertTrue(conv.is_processing)

    def test_process_message_skips_duplicate_downloads_for_same_url_and_filename(self):
        conv = Conversation()
        conv.add_user_message("download files")

        first_msg = _FakeAssistantMessage(
            content=None,
            tool_calls=[
                _FakeToolCall(
                    "call_1",
                    "download_file",
                    {"url": "https://example.com/Suppq425.pdf", "filename": "Suppq425.pdf"},
                ),
                _FakeToolCall(
                    "call_2",
                    "download_file",
                    {"url": "https://example.com/Suppq425.pdf", "filename": "Suppq425.pdf"},
                ),
            ],
        )
        final_msg = _FakeAssistantMessage(content="done", tool_calls=None)
        fake_client = _FakeOpenAIClient([first_msg, final_msg])

        calls: list[tuple[str, str]] = []

        def _fake_download(url: str, filename: str) -> dict:
            calls.append((url, filename))
            return {
                "url": url,
                "filename": filename,
                "path": f"downloads/{filename}",
                "size_bytes": 120_000,
                "content_type": "application/pdf",
                "success": True,
            }

        fake_cfg = SimpleNamespace(
            agent=SimpleNamespace(model="fake-model", max_tool_calls=5, temperature=0.0)
        )

        with patch("src.agent.loop.get_config", return_value=fake_cfg), patch(
            "src.agent.loop.get_openai_client", return_value=fake_client
        ), patch(
            "src.agent.loop.log_llm_call"
        ), patch(
            "src.agent.loop.log_tool_call"
        ), patch.dict(
            "src.agent.loop.TOOL_DISPATCH", {"download_file": _fake_download}
        ):
            process_message(conv)

        self.assertEqual(calls, [("https://example.com/Suppq425.pdf", "Suppq425.pdf")])

        file_messages = [m for m in conv.messages if m.role == "file"]
        self.assertEqual(len(file_messages), 1)

        tool_messages = [m for m in conv.messages if m.role == "tool_activity"]
        self.assertEqual(len(tool_messages), 2)
        self.assertTrue(tool_messages[1].tool_result.get("deduplicated"))

    def test_process_message_emits_single_file_message_per_filename(self):
        conv = Conversation()
        conv.add_user_message("download files")

        first_msg = _FakeAssistantMessage(
            content=None,
            tool_calls=[
                _FakeToolCall(
                    "call_1",
                    "download_file",
                    {"url": "https://example.com/a/Suppq425.pdf", "filename": "Suppq425.pdf"},
                ),
                _FakeToolCall(
                    "call_2",
                    "download_file",
                    {"url": "https://example.com/b/Suppq425.pdf", "filename": "Suppq425.pdf"},
                ),
            ],
        )
        final_msg = _FakeAssistantMessage(content="done", tool_calls=None)
        fake_client = _FakeOpenAIClient([first_msg, final_msg])

        calls: list[tuple[str, str]] = []

        def _fake_download(url: str, filename: str) -> dict:
            calls.append((url, filename))
            return {
                "url": url,
                "filename": filename,
                "path": f"downloads/{filename}",
                "size_bytes": 120_000,
                "content_type": "application/pdf",
                "success": True,
            }

        fake_cfg = SimpleNamespace(
            agent=SimpleNamespace(model="fake-model", max_tool_calls=5, temperature=0.0)
        )

        with patch("src.agent.loop.get_config", return_value=fake_cfg), patch(
            "src.agent.loop.get_openai_client", return_value=fake_client
        ), patch(
            "src.agent.loop.log_llm_call"
        ), patch(
            "src.agent.loop.log_tool_call"
        ), patch.dict(
            "src.agent.loop.TOOL_DISPATCH", {"download_file": _fake_download}
        ):
            process_message(conv)

        self.assertEqual(
            calls,
            [
                ("https://example.com/a/Suppq425.pdf", "Suppq425.pdf"),
                ("https://example.com/b/Suppq425.pdf", "Suppq425.pdf"),
            ],
        )

        file_messages = [m for m in conv.messages if m.role == "file"]
        self.assertEqual(len(file_messages), 1)

    def test_download_file_rejects_path_like_filenames(self):
        fake_cfg = SimpleNamespace(
            bright_data=SimpleNamespace(web_unlocker_zone="test-zone"),
            download=SimpleNamespace(base_dir="downloads"),
        )

        with patch("src.tools.bright_data.get_config", return_value=fake_cfg), patch(
            "src.tools.bright_data.requests.post"
        ) as post_mock:
            result = bright_data.download_file(
                url="https://example.com/Suppq425.pdf",
                filename="../../etc/passwd",
            )

        self.assertFalse(result["success"])
        self.assertIn("Invalid filename", result["error"])
        post_mock.assert_not_called()

    def test_process_message_does_not_emit_file_link_when_verification_warns(self):
        conv = Conversation()
        conv.add_user_message("download files")

        first_msg = _FakeAssistantMessage(
            content=None,
            tool_calls=[
                _FakeToolCall(
                    "call_1",
                    "download_file",
                    {"url": "https://example.com/small.pdf", "filename": "small.pdf"},
                ),
            ],
        )
        final_msg = _FakeAssistantMessage(content="done", tool_calls=None)
        fake_client = _FakeOpenAIClient([first_msg, final_msg])

        def _fake_download(url: str, filename: str) -> dict:
            return {
                "url": url,
                "filename": filename,
                "path": f"downloads/{filename}",
                "size_bytes": 50,
                "content_type": "application/pdf",
                "success": True,
            }

        fake_cfg = SimpleNamespace(
            agent=SimpleNamespace(model="fake-model", max_tool_calls=5, temperature=0.0)
        )

        with patch("src.agent.loop.get_config", return_value=fake_cfg), patch(
            "src.agent.loop.get_openai_client", return_value=fake_client
        ), patch(
            "src.agent.loop.log_llm_call"
        ), patch(
            "src.agent.loop.log_tool_call"
        ), patch.dict(
            "src.agent.loop.TOOL_DISPATCH", {"download_file": _fake_download}
        ):
            process_message(conv)

        file_messages = [m for m in conv.messages if m.role == "file"]
        self.assertEqual(len(file_messages), 0)

        system_messages = [m for m in conv.messages if m.role == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertIn("DOWNLOAD VERIFICATION WARNING", system_messages[0].content)


if __name__ == "__main__":
    unittest.main()
