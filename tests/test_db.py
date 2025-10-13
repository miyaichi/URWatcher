from pathlib import Path

from urwatcher.db import Database, resolve_sqlite_path
from urwatcher.models import DiffResult, Listing, Room


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

    listing = Listing(
        property_id="123",
        name="Sample",
        url="https://example.com/123.html",
        address="Sample Address",
    )
    diff_add = DiffResult(added=[listing], removed=[], unchanged=[])

    db.apply_listing_changes(executed_at="2025-01-01T00:00:00", diff=diff_add)

    records = db.fetch_listings(active_only=False)
    assert "123" in records
    assert records["123"].active is True
    assert records["123"].address == "Sample Address"

    diff_remove = DiffResult(added=[], removed=[records["123"]], unchanged=[])
    db.apply_listing_changes(executed_at="2025-01-02T00:00:00", diff=diff_remove)

    updated = db.fetch_listings(active_only=False)["123"]
    assert updated.active is False


def test_unicode_listing_names_are_preserved(tmp_path):
    db = Database(path=tmp_path / "unicode.db")
    db.initialize()

    name = "千代田区"
    listing = Listing(
        property_id="jp-101",
        name=name,
        url="https://example.com/jp-101.html",
        address="千代田区千代田1-1",
    )
    diff = DiffResult(added=[listing], removed=[], unchanged=[])

    db.apply_listing_changes(executed_at="2025-02-01T00:00:00", diff=diff)

    stored = db.fetch_listings(active_only=True)["jp-101"]
    assert stored.name == name
    assert stored.address == "千代田区千代田1-1"


def test_apply_room_changes_adds_and_removes_rooms(tmp_path):
    db = Database(path=tmp_path / "rooms.db")
    db.initialize()

    # Seed listing for FK constraint.
    listing = Listing(
        property_id="P-1",
        name="Sample",
        url="https://example.com/property",
        address="1 Property Way",
    )
    db.apply_listing_changes(
        executed_at="2025-03-01T00:00:00",
        diff=DiffResult(added=[listing], removed=[], unchanged=[]),
    )

    room = Room(
        room_id="R-1",
        property_id="P-1",
        property_name="Sample",
        property_url="https://example.com/property",
        building_name="Building A",
        room_number="101",
        rent="60,000円",
        common_fee="3,000円",
        layout="2DK",
        floor_area="45㎡",
        floor="5階",
        room_url="https://example.com/property/rooms/101",
    )

    db.apply_room_changes(
        executed_at="2025-03-02T00:00:00",
        property_id="P-1",
        diff=DiffResult(added=[room], removed=[], unchanged=[]),
    )

    rooms = db.fetch_rooms(property_id="P-1", active_only=False)
    assert "R-1" in rooms
    assert rooms["R-1"].active is True

    db.apply_room_changes(
        executed_at="2025-03-03T00:00:00",
        property_id="P-1",
        diff=DiffResult(added=[], removed=[rooms["R-1"]], unchanged=[]),
    )

    updated = db.fetch_rooms(property_id="P-1", active_only=False)["R-1"]
    assert updated.active is False
