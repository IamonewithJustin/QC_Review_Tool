"""Persist API configuration (key, URL, model names) to a local JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from core.app_paths import get_data_dir

CONFIG_PATH = get_data_dir() / "config.json"


@dataclass
class AppConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    # Model selections live here for persistence but are edited on the main screen
    model1: str = ""
    model2: str = ""
    model3: str = ""

    def api_is_complete(self) -> bool:
        """True when enough info exists to attempt a connection."""
        return bool(self.api_key.strip() and self.base_url.strip())

    # kept for backward-compat with test_connection
    def is_complete(self) -> bool:
        return self.api_is_complete()


def load_config() -> AppConfig:
    """Load config from disk, returning defaults if the file does not exist."""
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return AppConfig(
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", "https://api.openai.com/v1"),
            model1=data.get("model1", ""),
            model2=data.get("model2", ""),
            model3=data.get("model3", ""),
        )
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def test_connection(cfg: AppConfig) -> Optional[str]:
    """
    Attempt a lightweight server check (list models).
    Returns None on success, or an error string on failure.
    """
    if not cfg.is_complete():
        return "API settings are incomplete."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        client.models.list()
        return None
    except Exception as exc:
        return str(exc)


def fetch_models(cfg: AppConfig) -> Tuple[List[str], Optional[str]]:
    """
    Fetch the list of available model IDs from the server.

    Returns:
        (model_ids, None)      on success — model_ids is sorted alphabetically
        ([], error_string)     on failure
    """
    if not cfg.api_is_complete():
        return [], "API settings are incomplete."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        response = client.models.list()
        ids = sorted(m.id for m in response.data)
        return ids, None
    except Exception as exc:
        return [], str(exc)
