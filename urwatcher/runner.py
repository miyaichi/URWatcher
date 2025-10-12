"""Core execution workflow for URWatcher."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from .db import Database

logger = logging.getLogger(__name__)


@dataclass
class URWatcherRunner:
    """Coordinates scrape, diff, and persistence steps."""

    database: Database
    target_url: str

    def init(self) -> None:
        """Initialize required persistence structures."""
        logger.info("Initializing database at %s", self.database.path)
        self.database.initialize()

    def run(self, dry_run: bool = False) -> None:
        """Execute a single monitoring cycle."""
        logger.info("Starting monitor cycle for %s", self.target_url)
        executed_at = dt.datetime.utcnow().isoformat()

        if dry_run:
            note = "dry-run: no network requests performed"
            status = "dry_run"
            logger.info("Dry run complete; skipping scrape and notifications")
        else:
            # Real scraping and diff logic will be implemented later.
            note = "placeholder run - scraper not yet implemented"
            status = "success"
            logger.info("Placeholder execution complete (no network activity)")

        self.database.add_run(executed_at=executed_at, status=status, notes=note)
        logger.info("Run recorded at %s", executed_at)
