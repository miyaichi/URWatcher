"""Diff utilities for comparing listing snapshots."""

from __future__ import annotations

from typing import Dict, Iterable

from .models import DiffResult, Listing, ListingRecord


def diff_listings(
    new_listings: Iterable[Listing],
    previous_listings: Dict[str, ListingRecord],
) -> DiffResult:
    """Compute added, removed, and unchanged listings."""
    new_map = {listing.property_id: listing for listing in new_listings}

    added = []
    unchanged = []
    for property_id, listing in new_map.items():
        if property_id not in previous_listings:
            added.append(listing)
        else:
            unchanged.append(listing)

    removed = [
        record
        for property_id, record in previous_listings.items()
        if property_id not in new_map
    ]

    return DiffResult(added=added, removed=removed, unchanged=unchanged)
