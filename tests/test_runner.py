from urwatcher.db import Database
from urwatcher.models import Listing, PropertySnapshot, Room
from urwatcher.runner import URWatcherRunner


def build_runner(tmp_path, scraper=None) -> URWatcherRunner:
    db_path = tmp_path / "runs.db"
    database = Database(path=db_path)
    runner = URWatcherRunner(
        database=database,
        target_url="https://example.com",
        scraper=scraper or (lambda db, url: []),
    )
    runner.init()
    return runner


def make_room(property_id: str, suffix: str) -> Room:
    return Room(
        room_id=f"{property_id}-{suffix}",
        property_id=property_id,
        property_name=f"Property {property_id}",
        property_url=f"https://example.com/{property_id}.html",
        building_name=f"{property_id}-Building",
        room_number=f"{suffix}",
        rent="50,000円",
        common_fee="3,000円",
        layout="2DK",
        floor_area="40㎡",
        floor="5階",
        room_url=f"https://example.com/{property_id}/rooms/{suffix}",
    )


def make_snapshot(property_id: str, rooms: list[Room]) -> PropertySnapshot:
    listing = Listing(
        property_id=property_id,
        name=f"Property {property_id}",
        url=f"https://example.com/{property_id}.html",
        address=f"{property_id} Address",
    )
    return PropertySnapshot(listing=listing, rooms=rooms)


def test_runner_initializes_schema(tmp_path):
    runner = build_runner(tmp_path)
    assert runner.database.path.exists()


def test_runner_records_dry_run_without_persisting(tmp_path):
    snapshots = [
        make_snapshot("A", [make_room("A", "101")]),
    ]
    runner = build_runner(tmp_path, scraper=lambda db, url: snapshots)
    summary = runner.run(dry_run=True)

    assert summary.property_diff.added == [snapshots[0].listing]
    entries = list(runner.database.recent_runs())
    assert len(entries) == 1
    executed_at, status, notes = entries[0]

    assert executed_at  # timestamp recorded
    assert status == "dry_run"
    assert "dry-run" in notes

    listings = runner.database.fetch_listings(active_only=False)
    assert listings == {}
    rooms = runner.database.fetch_rooms(property_id="A", active_only=False)
    assert rooms == {}


def test_runner_persists_added_and_removed(tmp_path):
    snapshots_round_one = [
        make_snapshot("A", [make_room("A", "101")]),
        make_snapshot("B", [make_room("B", "201")]),
    ]

    runner = build_runner(tmp_path, scraper=lambda db, url: snapshots_round_one)
    runner.run()

    stored = runner.database.fetch_listings(active_only=True)
    assert set(stored.keys()) == {"A", "B"}

    snapshots_round_two = [
        make_snapshot("B", [make_room("B", "201")]),
        make_snapshot("C", [make_room("C", "301")]),
    ]

    runner.scraper = lambda db, url: snapshots_round_two
    runner.run()

    listings = runner.database.fetch_listings(active_only=False)
    assert listings["A"].active is False
    assert listings["B"].active is True
    assert listings["C"].active is True

    rooms_a = runner.database.fetch_rooms(property_id="A", active_only=False)
    assert rooms_a["A-101"].active is False

    rooms_c = runner.database.fetch_rooms(property_id="C", active_only=True)
    assert set(rooms_c.keys()) == {"C-301"}
