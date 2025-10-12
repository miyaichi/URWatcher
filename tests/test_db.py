import os
from pathlib import Path

from urwatcher.db import Database, resolve_sqlite_path


def test_resolve_sqlite_path_handles_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = resolve_sqlite_path("sqlite:///./relative.db")
    assert path == tmp_path / "relative.db"


def test_database_initializes_schema(tmp_path):
    db_path = tmp_path / "urwatcher.db"
    db = Database(path=db_path)
    db.initialize()

    assert db_path.exists()
    assert db_path.stat().st_size > 0
