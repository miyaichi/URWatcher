from urwatcher.db import Database
from urwatcher.runner import URWatcherRunner


def build_runner(tmp_path) -> URWatcherRunner:
    db_path = tmp_path / "runs.db"
    database = Database(path=db_path)
    runner = URWatcherRunner(database=database, target_url="https://example.com")
    runner.init()
    return runner


def test_runner_initializes_schema(tmp_path):
    runner = build_runner(tmp_path)
    assert runner.database.path.exists()


def test_runner_records_dry_run(tmp_path):
    runner = build_runner(tmp_path)
    runner.run(dry_run=True)

    entries = list(runner.database.recent_runs())
    assert len(entries) == 1
    executed_at, status, notes = entries[0]

    assert executed_at  # timestamp recorded
    assert status == "dry_run"
    assert notes and "dry-run" in notes
