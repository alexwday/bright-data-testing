from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.infra.llm import get_openai_client
from src.infra.oauth import OFFICIAL_OPENAI_BASE_URL, fetch_oauth_access_token, resolve_llm_auth


class LLMAuthTests(unittest.TestCase):
    def test_resolve_llm_auth_prefers_api_key_and_official_endpoint(self):
        settings = SimpleNamespace(
            OPENAI_API_KEY="sk-test",
            OAUTH_URL="https://oauth.example/token",
            CLIENT_ID="client-id",
            CLIENT_SECRET="client-secret",
            AZURE_BASE_URL="https://custom-llm.example/v1",
        )

        with patch("src.infra.oauth.fetch_oauth_access_token") as fetch_mock:
            token, base_url, mode = resolve_llm_auth(settings)

        self.assertEqual(token, "sk-test")
        self.assertEqual(base_url, OFFICIAL_OPENAI_BASE_URL)
        self.assertEqual(mode, "api_key_local")
        fetch_mock.assert_not_called()

    def test_resolve_llm_auth_uses_oauth_when_api_key_is_absent(self):
        settings = SimpleNamespace(
            OPENAI_API_KEY="",
            OAUTH_URL="https://oauth.example/token",
            CLIENT_ID="client-id",
            CLIENT_SECRET="client-secret",
            AZURE_BASE_URL="https://custom-llm.example/v1",
        )

        with patch(
            "src.infra.oauth.fetch_oauth_access_token", return_value="oauth-token"
        ) as fetch_mock:
            token, base_url, mode = resolve_llm_auth(settings)

        self.assertEqual(token, "oauth-token")
        self.assertEqual(base_url, "https://custom-llm.example/v1")
        self.assertEqual(mode, "oauth")
        fetch_mock.assert_called_once_with(
            oauth_url="https://oauth.example/token",
            client_id="client-id",
            client_secret="client-secret",
        )

    def test_resolve_llm_auth_rejects_incomplete_oauth_config(self):
        settings = SimpleNamespace(
            OPENAI_API_KEY="",
            OAUTH_URL="https://oauth.example/token",
            CLIENT_ID="client-id",
            CLIENT_SECRET="client-secret",
            AZURE_BASE_URL="",
        )

        with self.assertRaises(ValueError) as context:
            resolve_llm_auth(settings)

        self.assertIn("AZURE_BASE_URL", str(context.exception))

    def test_fetch_oauth_access_token_parses_access_token(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"access_token": "oauth-token"}

        session = MagicMock()
        session.post.return_value = response

        with patch("src.infra.oauth.requests.Session") as session_cls:
            session_cls.return_value.__enter__.return_value = session
            token = fetch_oauth_access_token(
                oauth_url="https://oauth.example/token",
                client_id="client-id",
                client_secret="client-secret",
                attempts=1,
            )

        self.assertEqual(token, "oauth-token")
        session.post.assert_called_once()

    @patch("src.infra.llm.OpenAI")
    @patch("src.infra.llm.resolve_llm_auth", return_value=("token", "https://base/v1", "oauth"))
    @patch("src.infra.llm.configure_rbc_security_certs")
    def test_get_openai_client_applies_security_and_builds_client(
        self,
        certs_mock,
        resolve_mock,
        openai_mock,
    ):
        sentinel_client = object()
        openai_mock.return_value = sentinel_client
        settings = SimpleNamespace()

        client = get_openai_client(settings)

        self.assertIs(client, sentinel_client)
        certs_mock.assert_called_once()
        resolve_mock.assert_called_once_with(settings)
        openai_mock.assert_called_once_with(api_key="token", base_url="https://base/v1")


if __name__ == "__main__":
    unittest.main()

