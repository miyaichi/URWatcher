from pathlib import Path

from urwatcher.db import Database, resolve_sqlite_path
from urwatcher.models import DiffResult, Listing


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


def test_apply_changes_adds_and_removes_listings(tmp_path):
    db = Database(path=tmp_path / "urwatcher.db")
    db.initialize()

    listing = Listing(property_id="123", name="Sample", url="https://example.com/123.html")
    diff_add = DiffResult(added=[listing], removed=[], unchanged=[])

    db.apply_changes(executed_at="2025-01-01T00:00:00", diff=diff_add)

    records = db.fetch_listings(active_only=False)
    assert "123" in records
    assert records["123"].active is True

    diff_remove = DiffResult(added=[], removed=[records["123"]], unchanged=[])
    db.apply_changes(executed_at="2025-01-02T00:00:00", diff=diff_remove)

    updated = db.fetch_listings(active_only=False)["123"]
    assert updated.active is False


def test_unicode_listing_names_are_preserved(tmp_path):
    db = Database(path=tmp_path / "unicode.db")
    db.initialize()

    name = "千代田区"
    listing = Listing(property_id="jp-101", name=name, url="https://example.com/jp-101.html")
    diff = DiffResult(added=[listing], removed=[], unchanged=[])

    db.apply_changes(executed_at="2025-02-01T00:00:00", diff=diff)

    stored = db.fetch_listings(active_only=True)["jp-101"]
    assert stored.name == name
