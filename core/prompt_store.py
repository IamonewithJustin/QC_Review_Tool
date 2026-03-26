"""SQLite-backed storage for saved additional-prompting snippets."""

import sqlite3
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from core.app_paths import get_data_dir

DB_PATH = get_data_dir() / "prompts.db"


@dataclass
class SavedPrompt:
    id: int
    name: str
    description: str
    content: str
    created_at: str


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                content     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            )
            """
        )
        conn.commit()


def save_prompt(name: str, description: str, content: str) -> int:
    """Insert a new prompt and return its id."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO prompts (name, description, content, created_at) VALUES (?, ?, ?, ?)",
            (name, description, content, now),
        )
        conn.commit()
        return cur.lastrowid


def list_prompts() -> List[SavedPrompt]:
    """Return all saved prompts ordered newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, description, content, created_at FROM prompts ORDER BY id DESC"
        ).fetchall()
    return [SavedPrompt(**dict(row)) for row in rows]


def get_prompt(prompt_id: int) -> Optional[SavedPrompt]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, content, created_at FROM prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
    return SavedPrompt(**dict(row)) if row else None


def delete_prompt(prompt_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        conn.commit()
