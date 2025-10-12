from urwatcher.diff import diff_listings
from urwatcher.models import Listing, ListingRecord


def test_diff_identifies_added_and_removed():
    new_listings = [
        Listing(property_id="1", name="One", url="https://example.com/1.html"),
        Listing(property_id="2", name="Two", url="https://example.com/2.html"),
    ]
    previous = {
        "2": ListingRecord(
            property_id="2",
            name="Two",
            url="https://example.com/2.html",
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            active=True,
        ),
        "3": ListingRecord(
            property_id="3",
            name="Three",
            url="https://example.com/3.html",
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            active=True,
        ),
    }

    diff = diff_listings(new_listings, previous)

    assert {listing.property_id for listing in diff.added} == {"1"}
    assert {record.property_id for record in diff.removed} == {"3"}
    assert {listing.property_id for listing in diff.unchanged} == {"2"}
