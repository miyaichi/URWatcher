"""Core data models for URWatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Generic, List, Sequence, TypeVar


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


TAdded = TypeVar("TAdded")
TRemoved = TypeVar("TRemoved")


@dataclass
class DiffResult(Generic[TAdded, TRemoved]):
    """Holds the result of comparing two item sets."""

    added: List[TAdded]
    removed: List[TRemoved]
    unchanged: List[TAdded]


@dataclass(frozen=True)
class Room:
    """Represents an individual room discovered via the UR API."""

    room_id: str
    property_id: str
    property_name: str
    property_url: str
    building_name: str
    room_number: str
    rent: str
    common_fee: str
    layout: str
    floor_area: str
    floor: str
    room_url: str


@dataclass
class RoomRecord:
    """Persisted representation of a room."""

    room_id: str
    property_id: str
    property_name: str
    property_url: str
    building_name: str
    room_number: str
    rent: str
    common_fee: str
    layout: str
    floor_area: str
    floor: str
    room_url: str
    first_seen: str
    last_seen: str
    active: bool


@dataclass(frozen=True)
class PropertySnapshot:
    """Container pairing a listing with its current rooms."""

    listing: Listing
    rooms: Sequence[Room]


@dataclass
class RunSummary:
    """Aggregated result returned by a monitoring cycle."""

    executed_at: str
    property_diff: DiffResult[Listing, ListingRecord]
    room_diffs: Dict[str, DiffResult[Room, RoomRecord]]


@dataclass
class AreaSnapshot:
    """Cached metadata for an area page to avoid unnecessary crawls."""

    area_url: str
    content_hash: str
    etag: str | None
    last_modified: str | None
    fetched_at: str
