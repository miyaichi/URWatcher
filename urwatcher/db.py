"""SQLite-backed persistence helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

from .models import DiffResult, Listing, ListingRecord, Room, RoomRecord


SQLITE_PREFIX = "sqlite://"


def resolve_sqlite_path(database_url: str) -> Path:
    """Translate a DATABASE_URL into a filesystem path."""
    if not database_url:
        raise ValueError("DATABASE_URL must not be empty")

    if database_url.startswith(SQLITE_PREFIX):
        raw_path = database_url[len(SQLITE_PREFIX) :]
        # Allow sqlite:///path/to/file and sqlite://path/to/file styles.
        if raw_path.startswith("/"):
            raw_path = raw_path[1:]
        path = Path(raw_path)
    else:
        path = Path(database_url)

    if not path.is_absolute():
        path = Path.cwd() / path

    return path.expanduser().resolve()


@dataclass
class Database:
    """Thin wrapper around sqlite3 for storing run history and listings."""

    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    executed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    property_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS listing_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY(property_id) REFERENCES listings(property_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    property_name TEXT NOT NULL,
                    property_url TEXT NOT NULL,
                    building_name TEXT NOT NULL,
                    room_number TEXT NOT NULL,
                    rent TEXT,
                    common_fee TEXT,
                    layout TEXT,
                    floor_area TEXT,
                    floor TEXT,
                    room_url TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(property_id) REFERENCES listings(property_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS room_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    property_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY(room_id) REFERENCES rooms(room_id)
                )
                """
            )
            conn.commit()

    def add_run(self, executed_at: str, status: str, notes: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runs (executed_at, status, notes) VALUES (?, ?, ?)",
                (executed_at, status, notes),
            )
            conn.commit()

    def recent_runs(self, limit: int = 10) -> Iterable[Tuple[str, str, str | None]]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT executed_at, status, notes FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            yield from cursor.fetchall()

    def fetch_listings(self, active_only: bool = False) -> Dict[str, ListingRecord]:
        """Return listings keyed by property_id."""
        query = """
            SELECT property_id, name, url, first_seen, last_seen, active
            FROM listings
        """
        if active_only:
            query += " WHERE active = 1"

        with self.connect() as conn:
            cursor = conn.execute(query)
            records = {}
            for row in cursor.fetchall():
                record = ListingRecord(
                    property_id=row[0],
                    name=row[1],
                    url=row[2],
                    first_seen=row[3],
                    last_seen=row[4],
                    active=bool(row[5]),
                )
                records[record.property_id] = record
            return records

    def apply_listing_changes(
        self,
        executed_at: str,
        diff: DiffResult[Listing, ListingRecord],
        all_records: Dict[str, ListingRecord] | None = None,
    ) -> None:
        """Persist diff results to the listings tables."""
        if all_records is None:
            all_records = self.fetch_listings(active_only=False)

        with self.connect() as conn:
            for listing in diff.added:
                existing = all_records.get(listing.property_id)
                if existing:
                    first_seen = existing.first_seen
                    event_type = "relisted" if not existing.active else "updated"
                    conn.execute(
                        """
                        UPDATE listings
                        SET name = ?, url = ?, last_seen = ?, active = 1
                        WHERE property_id = ?
                        """,
                        (listing.name, listing.url, executed_at, listing.property_id),
                    )
                else:
                    first_seen = executed_at
                    event_type = "added"
                    conn.execute(
                        """
                        INSERT INTO listings (property_id, name, url, first_seen, last_seen, active)
                        VALUES (?, ?, ?, ?, ?, 1)
                        """,
                        (
                            listing.property_id,
                            listing.name,
                            listing.url,
                            first_seen,
                            executed_at,
                        ),
                    )

                conn.execute(
                    """
                    INSERT INTO listing_events (property_id, event_type, occurred_at, details)
                    VALUES (?, ?, ?, ?)
                    """,
                    (listing.property_id, event_type, executed_at, listing.name),
                )

            for record in diff.removed:
                conn.execute(
                    """
                    UPDATE listings
                    SET active = 0, last_seen = ?
                    WHERE property_id = ?
                    """,
                    (executed_at, record.property_id),
                )
                conn.execute(
                    """
                    INSERT INTO listing_events (property_id, event_type, occurred_at, details)
                    VALUES (?, ?, ?, ?)
                    """,
                    (record.property_id, "removed", executed_at, record.name),
                )

            for listing in diff.unchanged:
                conn.execute(
                    """
                    UPDATE listings
                    SET name = ?, url = ?, last_seen = ?, active = 1
                    WHERE property_id = ?
                    """,
                    (listing.name, listing.url, executed_at, listing.property_id),
                )

            conn.commit()

    def fetch_rooms(
        self,
        property_id: str | None = None,
        active_only: bool = False,
    ) -> Dict[str, RoomRecord]:
        """Return rooms keyed by room_id."""
        query = """
            SELECT room_id, property_id, property_name, property_url, building_name,
                   room_number, rent, common_fee, layout, floor_area, floor, room_url,
                   first_seen, last_seen, active
            FROM rooms
        """
        params: tuple = ()
        conditions = []
        if property_id:
            conditions.append("property_id = ?")
            params += (property_id,)
        if active_only:
            conditions.append("active = 1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        with self.connect() as conn:
            cursor = conn.execute(query, params)
            records = {}
            for row in cursor.fetchall():
                record = RoomRecord(
                    room_id=row[0],
                    property_id=row[1],
                    property_name=row[2],
                    property_url=row[3],
                    building_name=row[4],
                    room_number=row[5],
                    rent=row[6],
                    common_fee=row[7],
                    layout=row[8],
                    floor_area=row[9],
                    floor=row[10],
                    room_url=row[11],
                    first_seen=row[12],
                    last_seen=row[13],
                    active=bool(row[14]),
                )
                records[record.room_id] = record
            return records

    def apply_room_changes(
        self,
        executed_at: str,
        property_id: str,
        diff: DiffResult[Room, RoomRecord],
        all_records: Dict[str, RoomRecord] | None = None,
    ) -> None:
        """Persist room diff results for a specific property."""
        if all_records is None:
            all_records = self.fetch_rooms(property_id=property_id, active_only=False)

        with self.connect() as conn:
            for room in diff.added:
                existing = all_records.get(room.room_id)
                if existing:
                    first_seen = existing.first_seen
                    event_type = "relisted" if not existing.active else "updated"
                    conn.execute(
                        """
                        UPDATE rooms
                        SET property_name = ?, property_url = ?, building_name = ?, room_number = ?,
                            rent = ?, common_fee = ?, layout = ?, floor_area = ?, floor = ?,
                            room_url = ?, last_seen = ?, active = 1
                        WHERE room_id = ?
                        """,
                        (
                            room.property_name,
                            room.property_url,
                            room.building_name,
                            room.room_number,
                            room.rent,
                            room.common_fee,
                            room.layout,
                            room.floor_area,
                            room.floor,
                            room.room_url,
                            executed_at,
                            room.room_id,
                        ),
                    )
                else:
                    first_seen = executed_at
                    event_type = "added"
                    conn.execute(
                        """
                        INSERT INTO rooms (
                            room_id, property_id, property_name, property_url, building_name,
                            room_number, rent, common_fee, layout, floor_area, floor, room_url,
                            first_seen, last_seen, active
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            room.room_id,
                            room.property_id,
                            room.property_name,
                            room.property_url,
                            room.building_name,
                            room.room_number,
                            room.rent,
                            room.common_fee,
                            room.layout,
                            room.floor_area,
                            room.floor,
                            room.room_url,
                            first_seen,
                            executed_at,
                        ),
                    )

                conn.execute(
                    """
                    INSERT INTO room_events (room_id, property_id, event_type, occurred_at, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        room.room_id,
                        room.property_id,
                        event_type,
                        executed_at,
                        f"{room.building_name} {room.room_number}",
                    ),
                )

            for record in diff.removed:
                conn.execute(
                    """
                    UPDATE rooms
                    SET active = 0, last_seen = ?
                    WHERE room_id = ?
                    """,
                    (executed_at, record.room_id),
                )
                conn.execute(
                    """
                    INSERT INTO room_events (room_id, property_id, event_type, occurred_at, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.room_id,
                        record.property_id,
                        "removed",
                        executed_at,
                        f"{record.building_name} {record.room_number}",
                    ),
                )

            for room in diff.unchanged:
                conn.execute(
                    """
                    UPDATE rooms
                    SET property_name = ?, property_url = ?, building_name = ?, room_number = ?,
                        rent = ?, common_fee = ?, layout = ?, floor_area = ?, floor = ?,
                        room_url = ?, last_seen = ?, active = 1
                    WHERE room_id = ?
                    """,
                    (
                        room.property_name,
                        room.property_url,
                        room.building_name,
                        room.room_number,
                        room.rent,
                        room.common_fee,
                        room.layout,
                        room.floor_area,
                        room.floor,
                        room.room_url,
                        executed_at,
                        room.room_id,
                    ),
                )

            conn.commit()
