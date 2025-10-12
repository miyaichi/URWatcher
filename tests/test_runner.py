from urwatcher.db import Database
from urwatcher.models import Listing
from urwatcher.runner import URWatcherRunner


def build_runner(tmp_path, scraper=None) -> URWatcherRunner:
    db_path = tmp_path / "runs.db"
    database = Database(path=db_path)
    runner = URWatcherRunner(
        database=database,
        target_url="https://example.com",
        scraper=scraper or (lambda url: []),
    )
    runner.init()
    return runner


def test_runner_initializes_schema(tmp_path):
    runner = build_runner(tmp_path)
    assert runner.database.path.exists()


def test_runner_records_dry_run_without_persisting(tmp_path):
    runner = build_runner(tmp_path)
    runner.run(dry_run=True)

    entries = list(runner.database.recent_runs())
    assert len(entries) == 1
    executed_at, status, notes = entries[0]

    assert executed_at  # timestamp recorded
    assert status == "dry_run"
    assert notes and "dry-run" in notes

    listings = runner.database.fetch_listings(active_only=False)
    assert listings == {}


def test_runner_persists_added_and_removed(tmp_path):
    listings_round_one = [
        Listing(property_id="A", name="Alpha", url="https://example.com/A.html"),
        Listing(property_id="B", name="Beta", url="https://example.com/B.html"),
    ]

    runner = build_runner(tmp_path, scraper=lambda url: listings_round_one)
    runner.run()

    stored = runner.database.fetch_listings(active_only=True)
    assert set(stored.keys()) == {"A", "B"}

    listings_round_two = [
        Listing(property_id="B", name="Beta", url="https://example.com/B.html"),
        Listing(property_id="C", name="Gamma", url="https://example.com/C.html"),
    ]

    runner.scraper = lambda url: listings_round_two
    runner.run()

    all_records = runner.database.fetch_listings(active_only=False)
    assert all_records["A"].active is False
    assert all_records["B"].active is True
    assert all_records["C"].active is True
