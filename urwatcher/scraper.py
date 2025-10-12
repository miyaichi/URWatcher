"""API-backed scraper for UR property and room data."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

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

    def __init__(self, context: AreaContext, session: requests.Session | None = None):
        self.context = context
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "URWatcher/1.0 (+https://github.com/miyaichi/URWatcher)",
                "Origin": UR_BASE,
                "Referer": context.referer,
                "Accept": "application/json",
            }
        )

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
        payload.extend(
            [
                ("block", self.context.block),
                ("tdfk", self.context.prefecture_code),
                ("rireki_tdfk", self.context.prefecture_code),
            ]
        )
        return payload

    def property_payload(self, page_index: int, page_size: int) -> List[tuple[str, str]]:
        payload = self.base_payload()
        payload.extend(
            [
                ("orderByField", "0"),
                ("pageSize", str(page_size)),
                ("pageIndex", str(page_index)),
                ("shisya", ""),
                ("danchi", ""),
                ("shikibetu", ""),
                ("pageIndexRoom", "0"),
                ("sp", ""),
            ]
        )
        return payload

    def room_payload(
        self,
        property_data: dict,
        page_index_room: int,
    ) -> List[tuple[str, str]]:
        payload = self.base_payload()
        payload.extend(
            [
                ("orderByField", "0"),
                ("pageSize", "10"),
                ("pageIndex", "0"),
                ("shisya", property_data["shisya"]),
                ("danchi", property_data["danchi"]),
                ("shikibetu", property_data["shikibetu"]),
                ("pageIndexRoom", str(page_index_room)),
                ("sp", ""),
            ]
        )
        return payload


def scrape_properties(target_url: str, timeout: int = 20) -> List[PropertySnapshot]:
    """Scrape property snapshots (including room inventories) for the given area page."""
    logger.debug("Fetching area page %s", target_url)
    response = requests.get(target_url, timeout=timeout)
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    try:
        context = _parse_area_context(response.text, target_url)
    except ValueError:
        area_links = _extract_area_links(response.text, target_url)
        if not area_links:
            raise
        logger.debug(
            "Discovered %d area links on %s; aggregating room data from each",
            len(area_links),
            target_url,
        )
        snapshots: List[PropertySnapshot] = []
        for area_url in sorted(area_links):
            snapshots.extend(scrape_properties(area_url, timeout=timeout))
        return snapshots
    client = URApiClient(context=context)

    snapshots: List[PropertySnapshot] = []
    page_index = 0
    total_properties = 0

    while True:
        payload = client.property_payload(
            page_index=page_index, page_size=DEFAULT_PAGE_SIZE
        )
        property_rows = client.post("bukken/result/bukken_result/", payload)
        if not property_rows:
            break

        logger.debug(
            "Fetched %d property rows for page %d", len(property_rows), page_index
        )
        for row in property_rows:
            try:
                room_count = int(row.get("roomCount") or 0)
            except ValueError:
                room_count = 0

            if room_count <= 0:
                continue

            listing = _build_listing(row)
            rooms = list(_fetch_rooms(client, row, listing, expected_total=room_count))
            snapshots.append(PropertySnapshot(listing=listing, rooms=rooms))
            total_properties += 1

        page_max = _safe_int(property_rows[0].get("pageMax"), default=page_index + 1)
        page_index += 1
        if page_index >= page_max:
            break

    logger.info(
        "Collected %d properties with available rooms (pages processed: %d)",
        total_properties,
        page_index,
    )
    return snapshots


def _parse_area_context(html_text: str, referer: str) -> AreaContext:
    pattern = re.compile(
        r"initSearch\(\s*'(?P<block>[^']+)'\s*,\s*'(?P<tdfk_cd>[^']+)'\s*,\s*'(?P<tdfk>[^']+)'\s*,\s*'(?P<mode>[^']+)'\s*,\s*\{(?P<params>[^}]*)\}",
        re.MULTILINE,
    )
    match = pattern.search(html_text)
    if not match:
        raise ValueError("Could not locate initSearch parameters in area page.")

    params = match.group("params")
    area_codes = re.findall(r"skcs'\s*:\s*'([^']+)'", params)
    if not area_codes:
        # fallback for double quotes
        area_codes = re.findall(r'skcs"\s*:\s*"([^"]+)"', params)
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


def _build_listing(row: dict) -> Listing:
    property_id = f"{row['shisya']}_{row['danchi']}_{row['shikibetu']}"
    name = row.get("danchiNm") or property_id
    url_path = row.get("allRoomUrl") or row.get("roomLinkPc") or ""
    url = urljoin(UR_BASE, url_path)
    return Listing(property_id=property_id, name=name, url=url)


def _fetch_rooms(
    client: URApiClient,
    property_data: dict,
    listing: Listing,
    expected_total: int,
) -> Iterable[Room]:
    seen: set[str] = set()
    page_index_room = 0

    while len(seen) < expected_total:
        payload = client.room_payload(property_data, page_index_room=page_index_room)
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
        room_url=urljoin(UR_BASE, row.get("roomLinkPc") or ""),
    )


def _safe_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default
