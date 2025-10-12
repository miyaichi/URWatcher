"""Core data models for URWatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Listing:
    """Represents a property listing scraped from the UR website."""

    property_id: str
    name: str
    url: str


@dataclass
class ListingRecord:
    """Represents a persisted listing from the database."""

    property_id: str
    name: str
    url: str
    first_seen: str
    last_seen: str
    active: bool


@dataclass
class DiffResult:
    """Holds the result of comparing two listing sets."""

    added: List[Listing]
    removed: List[ListingRecord]
    unchanged: List[Listing]
