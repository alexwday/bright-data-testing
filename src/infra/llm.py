"""OpenAI client factory with local API-key and corporate OAuth modes."""

from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from src.config.settings import Settings, get_settings
from src.config.types import Config
from src.infra.oauth import detect_auth_mode, resolve_llm_auth
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


def resolve_chat_runtime(
    config: Config,
    settings: Settings | None = None,
) -> tuple[str, Optional[int], str]:
    """Resolve model + max_tokens from env, with auth-mode-aware model overrides."""
    settings = settings or get_settings()
    mode = detect_auth_mode(settings)

    env_model = settings.AGENT_MODEL.strip()
    env_oauth_model = settings.AGENT_MODEL_OAUTH.strip()
    model = config.agent.model
    if mode == "oauth":
        model = env_oauth_model or env_model or model
    else:
        model = env_model or model

    max_tokens: Optional[int]
    if mode == "oauth":
        max_tokens = settings.AGENT_MAX_TOKENS_OAUTH
        if max_tokens is None:
            max_tokens = settings.AGENT_MAX_TOKENS
    else:
        max_tokens = settings.AGENT_MAX_TOKENS

    if max_tokens is not None and max_tokens <= 0:
        raise ValueError("AGENT_MAX_TOKENS values must be positive integers")

    return model, max_tokens, mode
