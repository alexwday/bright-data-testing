"""LLM authentication resolution: API key mode or OAuth2 client credentials."""

from __future__ import annotations

import logging
import time

import requests

from src.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


def fetch_oauth_access_token(
    oauth_url: str,
    client_id: str,
    client_secret: str,
    *,
    attempts: int = 3,
    timeout_seconds: int = 180,
) -> str:
    """Fetch an OAuth2 access token using the client credentials flow."""
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    with requests.Session() as session:
        for attempt_num in range(1, attempts + 1):
            try:
                response = session.post(oauth_url, data=payload, timeout=timeout_seconds)
                response.raise_for_status()
                token = response.json().get("access_token")
                if not token:
                    raise ValueError("OAuth response missing access_token")
                logger.info("OAuth token acquired successfully (client_id=%s)", client_id)
                return str(token)
            except (requests.exceptions.RequestException, ValueError) as exc:
                logger.warning("OAuth attempt %d/%d failed: %s", attempt_num, attempts, exc)
                if attempt_num == attempts:
                    raise RuntimeError("OAuth token fetch failed") from exc
                time.sleep(2)


def resolve_llm_auth(settings: Settings | None = None) -> tuple[str, str, str]:
    """Resolve LLM auth as (api_key_or_token, base_url, mode)."""
    settings = settings or get_settings()

    api_key = settings.OPENAI_API_KEY.strip()
    if api_key:
        if any(
            [
                settings.OAUTH_URL.strip(),
                settings.CLIENT_ID.strip(),
                settings.CLIENT_SECRET.strip(),
                settings.AZURE_BASE_URL.strip(),
            ]
        ):
            logger.info(
                "Both OPENAI_API_KEY and OAuth settings found; using OPENAI_API_KEY with official OpenAI endpoint"
            )
        else:
            logger.info("Using OPENAI_API_KEY with official OpenAI endpoint")
        return api_key, OFFICIAL_OPENAI_BASE_URL, "api_key_local"

    oauth_url = settings.OAUTH_URL.strip()
    client_id = settings.CLIENT_ID.strip()
    client_secret = settings.CLIENT_SECRET.strip()
    base_url = settings.AZURE_BASE_URL.strip()

    if any([oauth_url, client_id, client_secret, base_url]):
        missing = []
        if not oauth_url:
            missing.append("OAUTH_URL")
        if not client_id:
            missing.append("CLIENT_ID")
        if not client_secret:
            missing.append("CLIENT_SECRET")
        if not base_url:
            missing.append("AZURE_BASE_URL")
        if missing:
            raise ValueError(
                "Incomplete OAuth configuration. Missing: " + ", ".join(missing)
            )

        token = fetch_oauth_access_token(
            oauth_url=oauth_url,
            client_id=client_id,
            client_secret=client_secret,
        )
        logger.info("Using OAuth token with custom base URL")
        return token, base_url, "oauth"

    raise ValueError(
        "No LLM auth configured. Set OPENAI_API_KEY, or set OAUTH_URL, CLIENT_ID, CLIENT_SECRET, and AZURE_BASE_URL."
    )

