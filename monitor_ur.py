"""CLI entrypoint for the URWatcher agent."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from urwatcher.db import Database, resolve_sqlite_path
from urwatcher.runner import URWatcherRunner
from urwatcher.notifications import build_notifier_from_env, format_notifications

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="URWatcher monitoring agent")
    parser.add_argument("--init", action="store_true", help="initialize storage and exit")
    parser.add_argument(
        "--run",
        action="store_true",
        help="execute one monitoring cycle",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="skip persistence updates while still performing scraping and diffing",
    )
    parser.add_argument(
        "--target-url",
        default=os.getenv(
            "TARGET_URL",
            "https://www.ur-net.go.jp/chintai/kanto/tokyo/list/",
        ),
        help="URL to monitor (overrides TARGET_URL env var)",
    )
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    database_url = os.getenv("DATABASE_URL", "sqlite:///ur_monitor.db")
    db_path = resolve_sqlite_path(database_url)
    database = Database(path=db_path)
    runner = URWatcherRunner(database=database, target_url=args.target_url)
    notifier = build_notifier_from_env()

    if args.init:
        runner.init()
        return 0

    if not args.run:
        parser.print_help()
        return 1

    summary = runner.run(dry_run=args.dry_run)

    new_rooms = [
        room
        for diff in summary.room_diffs.values()
        for room in diff.added
    ]
    if new_rooms:
        logger.info("New room availability detected (%d):", len(new_rooms))
        for room in new_rooms:
            logger.info(
                "%s | %s %s | 家賃: %s (共益費: %s) | %s / %s | %s | %s",
                room.property_name,
                room.building_name,
                room.room_number,
                room.rent or "N/A",
                room.common_fee or "N/A",
                room.layout or "N/A",
                room.floor_area or "N/A",
                room.floor or "N/A",
                room.room_url,
            )
    else:
        logger.info("No new rooms detected in this run.")

    if summary.availability_changes:
        logger.info(
            "Detected availability count changes for %d property(ies)",
            len(summary.availability_changes),
        )
        for change in summary.availability_changes.values():
            previous = (
                str(change.previous_count)
                if change.previous_count is not None
                else "N/A"
            )
            logger.info(
                "%s | 対象空室数: %s -> %s | %s",
                change.property_name,
                previous,
                change.current_count,
                change.property_url,
            )

    if not args.dry_run and notifier:
        messages = format_notifications(summary)
        if messages:
            logger.info("Delivering %d notification(s)", len(messages))
            for message in messages:
                notifier.send(message)
        else:
            logger.debug("No diff notifications to deliver.")

    if not args.dry_run:
        try:
            timestamp = (
                summary.executed_at.replace(":", "-").replace(".", "-").replace("T", "_")
            )
            export_path = Path("data") / f"rooms_{timestamp}.xlsx"
            database.export_rooms_to_xlsx(export_path)
            logger.info("Exported room inventory to %s", export_path)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to export room inventory snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
