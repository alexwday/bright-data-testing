"""OpenAI client factory with local API-key and corporate OAuth modes."""

from __future__ import annotations

import logging

from openai import OpenAI

from src.config.settings import Settings, get_settings
from src.infra.oauth import resolve_llm_auth
from src.infra.security import configure_rbc_security_certs

logger = logging.getLogger(__name__)


def get_openai_client(settings: Settings | None = None) -> OpenAI:
    """Create an OpenAI client using resolved env-based auth configuration."""
    settings = settings or get_settings()

    # Optional in local environments, required in RBC environments where installed.
    configure_rbc_security_certs()

    token, base_url, mode = resolve_llm_auth(settings)
    logger.info("Initializing OpenAI client (mode=%s, base_url=%s)", mode, base_url)
    return OpenAI(api_key=token, base_url=base_url)

