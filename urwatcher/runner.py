"""Core execution workflow for URWatcher."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Callable, List

from .db import Database
from .diff import diff_listings
from .models import DiffResult, Listing
from .scraper import scrape_listings

logger = logging.getLogger(__name__)


@dataclass
class URWatcherRunner:
    """Coordinates scrape, diff, and persistence steps."""

    database: Database
    target_url: str
    scraper: Callable[[str], List[Listing]] = field(default_factory=lambda: scrape_listings)

    def init(self) -> None:
        """Initialize required persistence structures."""
        logger.info("Initializing database at %s", self.database.path)
        self.database.initialize()

    def run(self, dry_run: bool = False) -> None:
        """Execute a single monitoring cycle."""
        logger.info("Starting monitor cycle for %s", self.target_url)
        executed_at = dt.datetime.utcnow().isoformat()

        try:
            listings = self.scraper(self.target_url)
            logger.info("Scraped %d listings from %s", len(listings), self.target_url)
        except Exception as exc:
            logger.exception("Scraping failed: %s", exc)
            self.database.add_run(
                executed_at=executed_at,
                status="error",
                notes=f"scrape_failed: {exc}",
            )
            raise

        all_records = self.database.fetch_listings(active_only=False)
        previous_active = {pid: record for pid, record in all_records.items() if record.active}
        diff = diff_listings(listings, previous_active)

        if dry_run:
            logger.info(
                "Dry run detected %d additions, %d removals, %d unchanged entries",
                len(diff.added),
                len(diff.removed),
                len(diff.unchanged),
            )
            note = _format_note(diff, prefix="dry-run ")
            status = "dry_run"
        else:
            self.database.apply_changes(
                executed_at=executed_at,
                diff=diff,
                all_records=all_records,
            )
            logger.info(
                "Persisted changes: %d additions, %d removals, %d unchanged",
                len(diff.added),
                len(diff.removed),
                len(diff.unchanged),
            )
            note = _format_note(diff)
            status = "success"

        self.database.add_run(executed_at=executed_at, status=status, notes=note)
        logger.info("Run recorded at %s", executed_at)


def _format_note(diff: DiffResult, prefix: str = "") -> str:
    """Render a concise run note summarizing the diff outcome."""
    return (
        f"{prefix}added={len(diff.added)} "
        f"removed={len(diff.removed)} "
        f"unchanged={len(diff.unchanged)}"
    )
