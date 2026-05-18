"""Configuration loading: env > ~/.ernie/config.yaml > defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


_CONFIG_PATH = Path.home() / ".ernie" / "config.yaml"
_DEFAULT_MODEL = "ernie-5.1"
_DEFAULT_BASE_URL = "https://aistudio.baidu.com/llm/lmapi/v3"
_DEFAULT_WORKER_MODEL    = "deepseek-v4-flash"
_DEFAULT_WORKER_BASE_URL = "https://api.deepseek.com/v1"


@dataclass
class Config:
    api_key: str = ""
    base_url: str = _DEFAULT_BASE_URL
    model: str = _DEFAULT_MODEL
    max_tokens: int = 8192
    temperature: float = 0.7
    search_enabled: bool = False
    history_path: Path = field(default_factory=lambda: Path.home() / ".ernie" / "history.json")
    timeout: int = 120
    # MCP server list — each entry: {type, url/command/args, server_label}
    mcp_servers: list = field(default_factory=list)
    # Boss mode — worker model config
    boss_mode: bool = False
    worker_model: str = _DEFAULT_WORKER_MODEL
    worker_api_key: str = ""       # falls back to api_key if empty
    worker_base_url: str = _DEFAULT_WORKER_BASE_URL
    # Harness — 论语风格输出约束
    harness_enabled: bool = False

    def validate(self) -> None:
        if not self.api_key:
            raise SystemExit(
                "[red]错误：未找到 ERNIE_API_KEY。\n"
                "请设置环境变量：export ERNIE_API_KEY=<your_token>[/red]"
            )


def load_config(config_path: Optional[Path] = None) -> Config:
    cfg = Config()

    path = config_path or _CONFIG_PATH
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        _apply_yaml(cfg, data)

    # env vars always win
    if key := os.environ.get("ERNIE_API_KEY"):
        cfg.api_key = key
    if url := os.environ.get("ERNIE_BASE_URL"):
        cfg.base_url = url
    if model := os.environ.get("ERNIE_MODEL"):
        cfg.model = model

    cfg.validate()
    return cfg


def _apply_yaml(cfg: Config, data: dict) -> None:
    mapping = {
        "api_key":          "api_key",
        "base_url":         "base_url",
        "model":            "model",
        "max_tokens":       "max_tokens",
        "temperature":      "temperature",
        "search":           "search_enabled",
        "history_path":     None,
        "timeout":          "timeout",
        "mcp_servers":      None,
        "boss_mode":        "boss_mode",
        "worker_model":     "worker_model",
        "worker_api_key":   "worker_api_key",
        "worker_base_url":  "worker_base_url",
        "harness_enabled":  "harness_enabled",
    }
    for yaml_key, attr in mapping.items():
        if yaml_key in data and attr:
            setattr(cfg, attr, data[yaml_key])
    if "history_path" in data:
        cfg.history_path = Path(data["history_path"]).expanduser()
    if "mcp_servers" in data and isinstance(data["mcp_servers"], list):
        cfg.mcp_servers = data["mcp_servers"]
