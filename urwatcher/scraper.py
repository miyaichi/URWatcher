"""API-backed scraper for UR property and room data."""

from __future__ import annotations

import hashlib
import html
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .db import Database
from .models import Listing, PropertySnapshot, Room

logger = logging.getLogger(__name__)

UR_BASE = "https://www.ur-net.go.jp"
API_BASE = "https://chintai.r6.ur-net.go.jp/chintai/api/"
DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True)
class AreaContext:
    """Parameters required to hit the UR search API."""

    block: str
    prefecture_code: str
    prefecture_slug: str
    page_mode: str
    area_codes: Sequence[str]
    referer: str


class URApiClient:
    """Lightweight wrapper around the UR search API."""

    def __init__(self,
                 context: AreaContext,
                 session: requests.Session | None = None):
        self.context = context
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent":
            "URWatcher/1.0 (+https://github.com/miyaichi/URWatcher)",
            "Origin": UR_BASE,
            "Referer": context.referer,
            "Accept": "application/json",
        })

    def post(self, endpoint: str, data: List[tuple[str, str]]) -> list[dict]:
        response = self.session.post(
            urljoin(API_BASE, endpoint),
            data=data,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected response payload: {payload!r}")
        return payload

    def base_payload(self) -> List[tuple[str, str]]:
        payload: List[tuple[str, str]] = [("mode", self.context.page_mode)]
        for code in self.context.area_codes:
            payload.append(("skcs", code))
        payload.extend([
            ("block", self.context.block),
            ("tdfk", self.context.prefecture_code),
            ("rireki_tdfk", self.context.prefecture_code),
        ])
        return payload

    def property_payload(self, page_index: int,
                         page_size: int) -> List[tuple[str, str]]:
        payload = self.base_payload()
        payload.extend([
            ("orderByField", "0"),
            ("pageSize", str(page_size)),
            ("pageIndex", str(page_index)),
            ("shisya", ""),
            ("danchi", ""),
            ("shikibetu", ""),
            ("pageIndexRoom", "0"),
            ("sp", ""),
        ])
        return payload

    def room_payload(
        self,
        property_data: dict,
        page_index_room: int,
    ) -> List[tuple[str, str]]:
        payload = self.base_payload()
        payload.extend([
            ("orderByField", "0"),
            ("pageSize", "10"),
            ("pageIndex", "0"),
            ("shisya", property_data["shisya"]),
            ("danchi", property_data["danchi"]),
            ("shikibetu", property_data["shikibetu"]),
            ("pageIndexRoom", str(page_index_room)),
            ("sp", ""),
        ])
        return payload


def scrape_properties(
    database: Database,
    target_url: str,
    timeout: int = 20,
    visited: Set[str] | None = None,
) -> Tuple[List[PropertySnapshot], bool]:
    """Scrape property snapshots (including room inventories) for the given area page."""
    if visited is None:
        visited = set()
    if target_url in visited:
        logger.debug("Skipping already-visited URL %s to avoid loops",
                     target_url)
        return [], True
    visited.add(target_url)

    logger.debug("Fetching area page %s", target_url)
    response = requests.get(target_url, timeout=timeout)
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    content_hash = _hash_text(response.text)
    etag = response.headers.get("ETag")
    last_modified = response.headers.get("Last-Modified")
    snapshot = database.get_area_snapshot(target_url)
    area_changed = not snapshot or snapshot.content_hash != content_hash

    try:
        context = _parse_area_context(response.text, target_url)
    except ValueError:
        area_links = _extract_area_links(response.text, target_url)
        if not area_links:
            logger.info(
                "No initSearch parameters found for %s; treating as zero-availability page",
                target_url,
            )
            database.upsert_area_snapshot(target_url, content_hash, etag,
                                          last_modified)
            return [], True
        logger.info(
            "List page detected; scanning %d area pages beneath %s",
            len(area_links),
            target_url,
        )
        snapshots: List[PropertySnapshot] = []
        authoritative = False
        for idx, area_url in enumerate(sorted(area_links), start=1):
            logger.info(
                "Scanning area %d/%d: %s",
                idx,
                len(area_links),
                area_url,
            )
            child_snapshots, child_authoritative = scrape_properties(
                database,
                area_url,
                timeout=timeout,
                visited=visited,
            )
            snapshots.extend(child_snapshots)
            authoritative = authoritative or child_authoritative
        return snapshots, authoritative
    client = URApiClient(context=context)

    if snapshot and not area_changed:
        logger.info(
            "Area page %s unchanged since %s; performing lightweight property probe",
            target_url,
            snapshot.fetched_at,
        )
        _quick_property_probe(client)
        database.upsert_area_snapshot(target_url, content_hash, etag,
                                      last_modified)
        return [], False

    snapshots: List[PropertySnapshot] = []
    page_index = 0
    total_properties = 0

    while True:
        payload = client.property_payload(page_index=page_index,
                                          page_size=DEFAULT_PAGE_SIZE)
        try:
            property_rows = client.post("bukken/result/bukken_result/",
                                        payload)
        except requests.HTTPError as exc:  # type: ignore[attr-defined]
            logger.warning(
                "Property fetch failed for %s (page %d): %s",
                target_url,
                page_index,
                exc,
            )
            break
        if not property_rows:
            break

        logger.debug("Fetched %d property rows for page %d",
                     len(property_rows), page_index)
        for row in property_rows:
            try:
                room_count = int(row.get("roomCount") or 0)
            except ValueError:
                room_count = 0

            listing = _build_listing(row, room_count)
            rooms: List[Room] = []
            if room_count > 0:
                rooms = list(
                    _fetch_rooms(client,
                                 row,
                                 listing,
                                 expected_total=room_count))
                total_properties += 1
            else:
                logger.debug(
                    "Property %s has zero advertised availability; tracking for count changes",
                    listing.property_id,
                )
            snapshots.append(PropertySnapshot(listing=listing, rooms=rooms))

        page_max = _safe_int(property_rows[0].get("pageMax"),
                             default=page_index + 1)
        page_index += 1
        if page_index >= page_max:
            break

    logger.info(
        "Collected %d properties with available rooms (pages processed: %d)",
        total_properties,
        page_index,
    )
    database.upsert_area_snapshot(target_url, content_hash, etag,
                                  last_modified)
    return snapshots, True


def _parse_area_context(html_text: str, referer: str) -> AreaContext:
    pattern = re.compile(
        r"""
        initSearch\s*\(\s*
        (?P<quote1>['"])(?P<block>[^'"]+)(?P=quote1)\s*,\s*
        (?P<quote2>['"])(?P<tdfk_cd>[^'"]+)(?P=quote2)\s*,\s*
        (?P<quote3>['"])(?P<tdfk>[^'"]+)(?P=quote3)\s*,\s*
        (?P<quote4>['"])(?P<mode>[^'"]+)(?P=quote4)\s*,\s*
        \{(?P<params>[^}]*)\}
        """,
        re.MULTILINE | re.DOTALL | re.VERBOSE,
    )
    match = pattern.search(html_text)
    if not match:
        raise ValueError(
            "Could not locate initSearch parameters in area page.")

    params = match.group("params")
    area_codes = re.findall(r"'?skcs'?\s*:\s*'([^']+)'", params)
    if not area_codes:
        area_codes = re.findall(r'"?skcs"?\s*:\s*"([^"]+)"', params)
    if not area_codes:
        raise ValueError("Area codes (skcs) could not be identified.")

    return AreaContext(
        block=match.group("block"),
        prefecture_code=match.group("tdfk_cd"),
        prefecture_slug=match.group("tdfk"),
        page_mode=match.group("mode"),
        area_codes=area_codes,
        referer=referer,
    )


def _extract_area_links(html_text: str, base_url: str) -> Set[str]:
    """Extract unique area detail links from a list page."""
    soup = BeautifulSoup(html_text, "html.parser")
    links: Set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/area/" not in href or not href.endswith(".html"):
            continue
        absolute = urljoin(base_url, href)
        links.add(absolute)
    links.discard(base_url)
    return links


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _quick_property_probe(client: URApiClient) -> None:
    payload = client.property_payload(page_index=0, page_size=10)
    rows = client.post("bukken/result/bukken_result/", payload)
    logger.info(
        "Lightweight probe fetched %d property rows (page 0)",
        len(rows),
    )


def _resolve_listing_url(row: dict) -> str:
    """Extract the property listing URL path from an API row."""
    candidate_keys = ("allRoomUrl", "allroomUrl", "allroomurl", "roomLinkPc")
    for key in candidate_keys:
        url = row.get(key)
        if url:
            return url

    for nested_key in ("room", "kiboRoom"):
        nested_items = row.get(nested_key) or []
        if not isinstance(nested_items, list):
            continue
        for item in nested_items:
            if not isinstance(item, dict):
                continue
            for key in candidate_keys:
                url = item.get(key)
                if url:
                    return url
    return ""


def _build_listing(row: dict, room_count: int) -> Listing:
    property_id = f"{row['shisya']}_{row['danchi']}_{row['shikibetu']}"
    name = row.get("danchiNm") or property_id
    url_path = _resolve_listing_url(row)
    url = urljoin(UR_BASE, url_path)
    address = _extract_listing_address(row)
    return Listing(
        property_id=property_id,
        name=name,
        url=url,
        address=address,
        available_room_count=max(room_count, 0),
    )


def _extract_listing_address(row: dict) -> str:
    """Best-effort extraction of the listing's address from API payloads."""
    candidate_keys = (
        "place",
        "address",
        "address1",
        "address2",
        "danchiAddress",
    )
    for key in candidate_keys:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _fetch_rooms(
    client: URApiClient,
    property_data: dict,
    listing: Listing,
    expected_total: int,
) -> Iterable[Room]:
    seen: set[str] = set()
    page_index_room = 0

    while len(seen) < expected_total:
        payload = client.room_payload(property_data,
                                      page_index_room=page_index_room)
        room_rows = client.post("bukken/result/bukken_result_room/", payload)
        if not room_rows:
            break

        for room in room_rows:
            room_id = room.get("id")
            if not room_id or room_id in seen:
                continue
            seen.add(room_id)
            yield _build_room(room, listing)

        page_index_room += 1

        if len(room_rows) == 0:
            break


def _build_room(row: dict, listing: Listing) -> Room:
    rent = row.get("rent") or row.get("rent_normal") or ""
    rent = rent.strip()
    common_fee = (row.get("commonfee") or "").strip()
    floor_area = html.unescape(row.get("floorspace") or "").strip()
    return Room(
        room_id=row.get("id", ""),
        property_id=listing.property_id,
        property_name=listing.name,
        property_url=listing.url,
        building_name=(row.get("roomNmMain") or "").strip(),
        room_number=(row.get("roomNmSub") or "").strip(),
        rent=rent,
        common_fee=common_fee,
        layout=(row.get("type") or "").strip(),
        floor_area=floor_area,
        floor=(row.get("floor") or "").strip(),
        room_url=urljoin(UR_BASE,
                         row.get("roomLinkPc") or ""),
    )


def _safe_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default
