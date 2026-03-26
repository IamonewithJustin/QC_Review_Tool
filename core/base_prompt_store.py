"""Load and save the customizable base prompt (separate from saved additional prompting)."""

from __future__ import annotations

from pathlib import Path

from core.app_paths import get_data_dir

BASE_PROMPT_PATH = get_data_dir() / "base_prompt.txt"

DEFAULT_BASE_PROMPT = (
    "Act as an expert reviewer of scientific manuscripts, documents, or datasets. "
    "Carefully analyze the content to identify:\n"
    "1. Errors in grammar, spelling, or formatting\n"
    "2. Typos and inconsistencies in terminology or style\n"
    "3. Incorrect or mismatched data and factual inaccuracies\n"
    "4. Overall story flow\n\n"
    "For each issue found, provide:\n"
    "1. A brief explanation of the problem\n"
    "2. A recommended correction or rewrite, including improved sentences or phrases where necessary"
)


def get_base_prompt() -> str:
    """Return the active base prompt (custom file if present, else built-in default)."""
    if not BASE_PROMPT_PATH.exists():
        return DEFAULT_BASE_PROMPT
    try:
        return BASE_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_BASE_PROMPT


def save_base_prompt(text: str) -> None:
    """Persist the base prompt to disk."""
    BASE_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASE_PROMPT_PATH.write_text(text, encoding="utf-8")
