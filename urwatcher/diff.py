"""Diff utilities for comparing scraped snapshots."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, TypeVar

from .models import DiffResult, Listing, ListingRecord, Room, RoomRecord

TNew = TypeVar("TNew")
TStored = TypeVar("TStored")
KeyFunc = Callable[[TNew], str]


def _diff_items(
    new_items: Iterable[TNew],
    previous_items: Dict[str, TStored],
    key_fn: KeyFunc,
) -> DiffResult[TNew, TStored]:
    new_map = {key_fn(item): item for item in new_items}

    added = []
    unchanged = []
    for item_id, item in new_map.items():
        if item_id not in previous_items:
            added.append(item)
        else:
            unchanged.append(item)

    removed = [
        record for item_id, record in previous_items.items()
        if item_id not in new_map
    ]

    return DiffResult(added=added, removed=removed, unchanged=unchanged)


def diff_listings(
    new_listings: Iterable[Listing],
    previous_listings: Dict[str, ListingRecord],
) -> DiffResult[Listing, ListingRecord]:
    """Compute added, removed, and unchanged listings."""
    return _diff_items(new_listings,
                       previous_listings,
                       key_fn=lambda item: item.property_id)


def diff_rooms(
    new_rooms: Iterable[Room],
    previous_rooms: Dict[str, RoomRecord],
) -> DiffResult[Room, RoomRecord]:
    """Compute added, removed, and unchanged rooms."""
    return _diff_items(new_rooms,
                       previous_rooms,
                       key_fn=lambda item: item.room_id)
