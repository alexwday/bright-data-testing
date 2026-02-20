from __future__ import annotations

from pydantic import BaseModel


class BrightDataConfig(BaseModel):
    serp_zone: str = "serp_api1"
    web_unlocker_zone: str = "web_unlocker1"
    proxy_host: str = "brd.superproxy.io"
    proxy_port: int = 33335


class AgentConfig(BaseModel):
    model: str = "gpt-4.1"
    max_tool_calls: int = 50
    temperature: float = 0.2


class DownloadConfig(BaseModel):
    base_dir: str = "downloads"


class DocumentTarget(BaseModel):
    id: str
    label: str
    keywords: list[str]
    extensions: list[str]


class BankConfig(BaseModel):
    code: str
    name: str
    ir_url: str
    doc_hints: dict[str, list[str]] = {}


class PrebuiltPrompt(BaseModel):
    id: str
    label: str
    message: str
    prefill: bool = False  # True = pre-fill input, False = send directly


class Config(BaseModel):
    bright_data: BrightDataConfig = BrightDataConfig()
    agent: AgentConfig = AgentConfig()
    download: DownloadConfig = DownloadConfig()
    document_targets: list[DocumentTarget] = []
    banks: list[BankConfig] = []
    prebuilt_prompts: list[PrebuiltPrompt] = []
