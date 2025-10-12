from typing import Optional

from urwatcher.db import Database
from urwatcher.scraper import _extract_area_links, scrape_properties


class DummyResponse:
    def __init__(self, text: str, headers: Optional[dict] = None):
        self.text = text
        self.status_code = 200
        self.encoding = "utf-8"
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    @property
    def apparent_encoding(self):
        return "utf-8"


def test_extract_area_links_finds_unique_urls():
    html = """
    <html>
      <body>
        <a href="/chintai/kanto/tokyo/area/119.html">Itabashi</a>
        <a href="https://www.ur-net.go.jp/chintai/kanto/tokyo/area/120.html">Shinjuku</a>
        <a href="/other/page.html">Other</a>
      </body>
    </html>
    """
    links = _extract_area_links(html, "https://www.ur-net.go.jp/chintai/kanto/tokyo/list/")
    assert links == {
        "https://www.ur-net.go.jp/chintai/kanto/tokyo/area/119.html",
        "https://www.ur-net.go.jp/chintai/kanto/tokyo/area/120.html",
    }


def test_scrape_properties_handles_list_page(monkeypatch, tmp_path):
    list_url = "https://www.ur-net.go.jp/chintai/kanto/tokyo/list/"
    area_url = "https://www.ur-net.go.jp/chintai/kanto/tokyo/area/119.html"

    html_list = """
    <html><body>
        <a href="/chintai/kanto/tokyo/area/119.html">Area</a>
    </body></html>
    """
    html_area = """
    <html>
      <head>
        <script>
          ur.api.bukken.result.initSearch('kanto','13','tokyo','area',{skcs':'119'});
        </script>
      </head>
      <body></body>
    </html>
    """

    responses = {
        list_url: DummyResponse(html_list),
        area_url: DummyResponse(html_area),
    }

    def fake_get(url, timeout):
        return responses[url]

    def fake_post(self, endpoint, data):
        if endpoint.endswith("bukken_result/"):
            return [
                {
                    "roomCount": "1",
                    "shisya": "20",
                    "danchi": "225",
                    "shikibetu": "0",
                    "danchiNm": "Test Danchi",
                    "allRoomUrl": "/chintai/kanto/tokyo/20_2250.html",
                    "pageMax": "1",
                }
            ]
        return [
            {
                "id": "0001",
                "roomNmMain": "1号棟",
                "roomNmSub": "101号室",
                "rent": "60,000円",
                "commonfee": "3,000円",
                "type": "2DK",
                "floorspace": "45㎡",
                "floor": "5階",
                "roomLinkPc": "/chintai/kanto/tokyo/20_2250_room.html?JKSS=0001",
            }
        ]

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("urwatcher.scraper.URApiClient.post", fake_post)

    database = Database(path=tmp_path / "test.db")
    database.initialize()

    snapshots = scrape_properties(database, list_url)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.listing.name == "Test Danchi"
    assert len(snapshot.rooms) == 1
    room = snapshot.rooms[0]
    assert room.room_id == "0001"
    assert room.property_id == snapshot.listing.property_id


def test_scrape_properties_skips_when_area_unchanged(monkeypatch, tmp_path):
    area_url = "https://www.ur-net.go.jp/chintai/kanto/tokyo/area/119.html"

    html_area = """
    <html>
      <head>
        <script>
          ur.api.bukken.result.initSearch('kanto','13','tokyo','area',{skcs':'119'});
        </script>
      </head>
      <body></body>
    </html>
    """

    responses = {area_url: DummyResponse(html_area)}
    monkeypatch.setattr("requests.get", lambda url, timeout: responses[url])

    call_count = {"property": 0, "room": 0}

    def fake_post(self, endpoint, data):
        if endpoint.endswith("bukken_result/"):
            call_count["property"] += 1
            return [
                {
                    "roomCount": "1",
                    "shisya": "20",
                    "danchi": "225",
                    "shikibetu": "0",
                    "danchiNm": "Test Danchi",
                    "allRoomUrl": "/chintai/kanto/tokyo/20_2250.html",
                    "pageMax": "1",
                }
            ]
        call_count["room"] += 1
        return [
            {
                "id": "0001",
                "roomNmMain": "1号棟",
                "roomNmSub": "101号室",
                "rent": "60,000円",
                "commonfee": "3,000円",
                "type": "2DK",
                "floorspace": "45㎡",
                "floor": "5階",
                "roomLinkPc": "/chintai/kanto/tokyo/20_2250_room.html?JKSS=0001",
            }
        ]

    monkeypatch.setattr("urwatcher.scraper.URApiClient.post", fake_post)

    database = Database(path=tmp_path / "skip.db")
    database.initialize()

    # First crawl populates snapshot and fetches rooms
    first = scrape_properties(database, area_url)
    assert len(first) == 1
    assert call_count == {"property": 1, "room": 1}

    # Second crawl should perform only quick probe (no room fetch)
    second = scrape_properties(database, area_url)
    assert second == []
    assert call_count["property"] == 2
    assert call_count["room"] == 1
