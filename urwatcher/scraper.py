"""HTML scraper for UR listing pages."""

from __future__ import annotations

import logging
from typing import Iterable, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import Listing

logger = logging.getLogger(__name__)


def scrape_listings(target_url: str, timeout: int = 20) -> List[Listing]:
    """Fetch the target URL and return parsed listings."""
    logger.debug("Fetching listings from %s", target_url)
    response = requests.get(target_url, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    anchors = soup.find_all("a")

    listings: dict[str, Listing] = {}
    for anchor in anchors:
        href = anchor.get("href")
        if not href:
            continue
        if ".html" not in href:
            continue
        if "/chintai/" not in href:
            continue

        full_url = urljoin(target_url, href)
        property_id = _extract_property_id(full_url)
        name = anchor.get_text(strip=True) or property_id

        if not property_id:
            continue

        # Keep the first occurrence for the property id.
        listings.setdefault(
            property_id,
            Listing(property_id=property_id, name=name, url=full_url),
        )

    logger.debug("Parsed %d listings from %s", len(listings), target_url)
    return list(listings.values())


def _extract_property_id(url: str) -> str:
    """Extract property identifier from the listing URL."""
    fragment = url.split("/")[-1]
    fragment = fragment.split("?")[0]
    if fragment.endswith(".html"):
        fragment = fragment[:-5]
    return fragment
