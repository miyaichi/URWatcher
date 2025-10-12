"""SQLite-backed persistence helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple


SQLITE_PREFIX = "sqlite://"


def resolve_sqlite_path(database_url: str) -> Path:
    """Translate a DATABASE_URL into a filesystem path."""
    if not database_url:
        raise ValueError("DATABASE_URL must not be empty")

    if database_url.startswith(SQLITE_PREFIX):
        raw_path = database_url[len(SQLITE_PREFIX) :]
        # Allow sqlite:///path/to/file and sqlite://path/to/file styles.
        if raw_path.startswith("/"):
            raw_path = raw_path[1:]
        path = Path(raw_path)
    else:
        path = Path(database_url)

    if not path.is_absolute():
        path = Path.cwd() / path

    return path.expanduser().resolve()


@dataclass
class Database:
    """Thin wrapper around sqlite3 for storing run history."""

    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    executed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT
                )
                """
            )
            conn.commit()

    def add_run(self, executed_at: str, status: str, notes: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runs (executed_at, status, notes) VALUES (?, ?, ?)",
                (executed_at, status, notes),
            )
            conn.commit()

    def recent_runs(self, limit: int = 10) -> Iterable[Tuple[str, str, str | None]]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT executed_at, status, notes FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            yield from cursor.fetchall()
