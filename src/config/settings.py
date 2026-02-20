from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings

from .types import Config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    OAUTH_URL: str = ""
    CLIENT_ID: str = ""
    CLIENT_SECRET: str = ""
    AZURE_BASE_URL: str = ""
    BRIGHT_DATA_API_TOKEN: str = ""
    BRIGHT_DATA_PROXY_PASSWORD: str = ""

    model_config = {"env_file": str(_PROJECT_ROOT / ".env"), "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_config() -> Config:
    config_path = _PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        return Config()
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}
    return Config(**raw)
