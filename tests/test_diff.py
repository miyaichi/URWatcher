from urwatcher.diff import diff_listings, diff_rooms
from urwatcher.models import Listing, ListingRecord, Room, RoomRecord


def test_diff_identifies_added_and_removed():
    new_listings = [
        Listing(property_id="1",
                name="One",
                url="https://example.com/1.html",
                address="1 Example St",
                available_room_count=1),
        Listing(property_id="2",
                name="Two",
                url="https://example.com/2.html",
                address="2 Example St",
                available_room_count=2),
    ]
    previous = {
        "2":
        ListingRecord(
            property_id="2",
            name="Two",
            url="https://example.com/2.html",
            address="2 Example St",
            available_room_count=2,
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            active=True,
        ),
        "3":
        ListingRecord(
            property_id="3",
            name="Three",
            url="https://example.com/3.html",
            address="3 Example St",
            available_room_count=1,
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            active=True,
        ),
    }

    diff = diff_listings(new_listings, previous)

    assert {listing.property_id for listing in diff.added} == {"1"}
    assert {record.property_id for record in diff.removed} == {"3"}
    assert {listing.property_id for listing in diff.unchanged} == {"2"}


def test_diff_rooms_behaves_like_listings():
    new_rooms = [
        Room(
            room_id="r1",
            property_id="A",
            property_name="Property A",
            property_url="https://example.com/A.html",
            building_name="A",
            room_number="101",
            rent="50,000円",
            common_fee="3,000円",
            layout="2DK",
            floor_area="45㎡",
            floor="5階",
            room_url="https://example.com/A/room/101",
        ),
        Room(
            room_id="r2",
            property_id="A",
            property_name="Property A",
            property_url="https://example.com/A.html",
            building_name="A",
            room_number="102",
            rent="52,000円",
            common_fee="3,000円",
            layout="2DK",
            floor_area="45㎡",
            floor="5階",
            room_url="https://example.com/A/room/102",
        ),
    ]
    previous = {
        "r2":
        RoomRecord(
            room_id="r2",
            property_id="A",
            property_name="Property A",
            property_url="https://example.com/A.html",
            building_name="A",
            room_number="102",
            rent="52,000円",
            common_fee="3,000円",
            layout="2DK",
            floor_area="45㎡",
            floor="5階",
            room_url="https://example.com/A/room/102",
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            active=True,
        ),
        "r3":
        RoomRecord(
            room_id="r3",
            property_id="A",
            property_name="Property A",
            property_url="https://example.com/A.html",
            building_name="A",
            room_number="103",
            rent="53,000円",
            common_fee="3,000円",
            layout="2DK",
            floor_area="45㎡",
            floor="5階",
            room_url="https://example.com/A/room/103",
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            active=True,
        ),
    }

    diff = diff_rooms(new_rooms, previous)

    assert {room.room_id for room in diff.added} == {"r1"}
    assert {room.room_id for room in diff.removed} == {"r3"}
    assert {room.room_id for room in diff.unchanged} == {"r2"}
