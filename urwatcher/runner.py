"""Core execution workflow for URWatcher."""

from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from .db import Database
from .diff import diff_listings, diff_rooms
from .models import (
    DiffResult,
    Listing,
    ListingRecord,
    PropertySnapshot,
    Room,
    RoomRecord,
    RunSummary,
)
from .scraper import scrape_properties

logger = logging.getLogger(__name__)


@dataclass
class URWatcherRunner:
    """Coordinates scrape, diff, and persistence steps."""

    database: Database
    target_url: str
    scraper: Callable[[str], List[PropertySnapshot]] = field(
        default_factory=lambda: scrape_properties
    )

    def init(self) -> None:
        """Initialize required persistence structures."""
        logger.info("Initializing database at %s", self.database.path)
        self.database.initialize()

    def run(self, dry_run: bool = False) -> RunSummary:
        """Execute a single monitoring cycle."""
        logger.info("Starting monitor cycle for %s", self.target_url)
        executed_at = dt.datetime.utcnow().isoformat()

        try:
            snapshots = self.scraper(self.target_url)
            logger.info(
                "Scraped %d properties from %s", len(snapshots), self.target_url
            )
        except Exception as exc:
            logger.exception("Scraping failed: %s", exc)
            self.database.add_run(
                executed_at=executed_at,
                status="error",
                notes=f"scrape_failed: {exc}",
            )
            raise

        current_listings = [snapshot.listing for snapshot in snapshots]
        listing_records = self.database.fetch_listings(active_only=False)
        previous_active = {
            pid: record for pid, record in listing_records.items() if record.active
        }
        listing_diff = diff_listings(current_listings, previous_active)

        room_diffs: Dict[str, DiffResult[Room, RoomRecord]] = {}
        added_rooms_total: List[Room] = []
        removed_rooms_total: List[RoomRecord] = []

        for snapshot in snapshots:
            property_id = snapshot.listing.property_id
            existing_rooms = self.database.fetch_rooms(
                property_id=property_id, active_only=False
            )
            room_diff = diff_rooms(snapshot.rooms, existing_rooms)
            room_diffs[property_id] = room_diff
            added_rooms_total.extend(room_diff.added)
            removed_rooms_total.extend(room_diff.removed)

            if not dry_run:
                self.database.apply_room_changes(
                    executed_at=executed_at,
                    property_id=property_id,
                    diff=room_diff,
                    all_records=existing_rooms,
                )

        for removed_listing in listing_diff.removed:
            property_id = removed_listing.property_id
            existing_rooms = self.database.fetch_rooms(
                property_id=property_id, active_only=False
            )
            if existing_rooms:
                removal_diff = DiffResult[Room, RoomRecord](
                    added=[],
                    removed=list(existing_rooms.values()),
                    unchanged=[],
                )
                room_diffs[property_id] = removal_diff
                removed_rooms_total.extend(removal_diff.removed)
                if not dry_run:
                    self.database.apply_room_changes(
                        executed_at=executed_at,
                        property_id=property_id,
                        diff=removal_diff,
                        all_records=existing_rooms,
                    )

        if dry_run:
            logger.info(
                "Dry run detected %d property additions, %d property removals, %d unchanged",
                len(listing_diff.added),
                len(listing_diff.removed),
                len(listing_diff.unchanged),
            )
            note = _format_note(listing_diff, room_diffs, prefix="dry-run ")
            status = "dry_run"
        else:
            self.database.apply_listing_changes(
                executed_at=executed_at,
                diff=listing_diff,
                all_records=listing_records,
            )
            logger.info(
                "Persisted changes: %d property additions, %d property removals, %d unchanged",
                len(listing_diff.added),
                len(listing_diff.removed),
                len(listing_diff.unchanged),
            )
            note = _format_note(listing_diff, room_diffs)
            status = "success"

        self.database.add_run(executed_at=executed_at, status=status, notes=note)
        logger.info("Run recorded at %s", executed_at)
        return RunSummary(
            executed_at=executed_at,
            property_diff=listing_diff,
            room_diffs=room_diffs,
        )


def _format_note(
    listing_diff: DiffResult[Listing, ListingRecord],
    room_diffs: Dict[str, DiffResult[Room, RoomRecord]],
    prefix: str = "",
) -> str:
    """Render a concise run note summarizing the diff outcome."""
    rooms_added = sum(len(diff.added) for diff in room_diffs.values())
    rooms_removed = sum(len(diff.removed) for diff in room_diffs.values())
    rooms_unchanged = sum(len(diff.unchanged) for diff in room_diffs.values())
    return (
        f"{prefix}"
        f"properties(+{len(listing_diff.added)} / -{len(listing_diff.removed)} / ={len(listing_diff.unchanged)}) "
        f"rooms(+{rooms_added} / -{rooms_removed} / ={rooms_unchanged})"
    )
