from types import SimpleNamespace

from urwatcher.models import AvailabilityChange, DiffResult, Listing, ListingRecord, Room, RoomRecord, RunSummary
from urwatcher.notifications import (
    CompositeNotifier,
    LineNotifier,
    SlackNotifier,
    build_notifier_from_env,
    format_notifications,
)


class DummyResponse:

    def raise_for_status(self):
        pass


def test_slack_notifier_posts(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(SimpleNamespace(url=url, json=json, timeout=timeout))
        return DummyResponse()

    monkeypatch.setattr("urwatcher.notifications.requests.post", fake_post)

    notifier = SlackNotifier(
        webhook_url="https://hooks.slack.com/services/test")
    notifier.send("hello slack")

    assert len(calls) == 1
    assert calls[0].url == "https://hooks.slack.com/services/test"
    assert calls[0].json == {"text": "hello slack"}


def test_line_notifier_posts(monkeypatch):
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(
            SimpleNamespace(url=url,
                            headers=headers,
                            data=data,
                            timeout=timeout))
        return DummyResponse()

    monkeypatch.setattr("urwatcher.notifications.requests.post", fake_post)

    notifier = LineNotifier(access_token="token123")
    notifier.send("hello line")

    assert len(calls) == 1
    assert calls[0].url.endswith("/api/notify")
    assert calls[0].headers["Authorization"] == "Bearer token123"
    assert calls[0].data == {"message": "hello line"}


def test_composite_notifier_logs_and_continues(monkeypatch, caplog):
    success = []

    class SuccessNotifier:

        def send(self, message: str) -> None:
            success.append(message)

    class FailingNotifier:

        def send(self, message: str) -> None:
            raise RuntimeError("boom")

    composite = CompositeNotifier(
        notifiers=[FailingNotifier(), SuccessNotifier()])
    with caplog.at_level("ERROR"):
        composite.send("payload")

    assert success == ["payload"]
    assert "Failed to deliver notification" in caplog.text


def test_format_notifications_covers_all_paths():
    added_listing = Listing(
        property_id="P1",
        name="New Property",
        url="https://example.com/p1",
        address="新宿区北新宿3-27-3",
        available_room_count=1,
    )
    removed_listing = ListingRecord(
        property_id="P2",
        name="Removed Property",
        url="https://example.com/p2",
        address="新宿区旧住所1-2-3",
        available_room_count=0,
        first_seen="2025-01-01",
        last_seen="2025-02-01",
        active=False,
    )

    new_property_room = Room(
        room_id="R1",
        property_id="P1",
        property_name="New Property",
        property_url="https://example.com/p1",
        building_name="A棟",
        room_number="101",
        rent="80,000円",
        common_fee="3,000円",
        layout="2DK",
        floor_area="45㎡",
        floor="5階",
        room_url="https://example.com/p1/rooms/101",
    )

    existing_room_added = Room(
        room_id="R2",
        property_id="P3",
        property_name="Existing Property",
        property_url="https://example.com/p3",
        building_name="B棟",
        room_number="202",
        rent="90,000円",
        common_fee="4,000円",
        layout="3DK",
        floor_area="60㎡",
        floor="6階",
        room_url="https://example.com/p3/rooms/202",
    )

    existing_room_removed = RoomRecord(
        room_id="R3",
        property_id="P3",
        property_name="Existing Property",
        property_url="https://example.com/p3",
        building_name="B棟",
        room_number="203",
        rent="92,000円",
        common_fee="4,000円",
        layout="3DK",
        floor_area="60㎡",
        floor="6階",
        room_url="https://example.com/p3/rooms/203",
        first_seen="2025-01-01",
        last_seen="2025-02-01",
        active=False,
    )

    removed_property_room = RoomRecord(
        room_id="R4",
        property_id="P2",
        property_name="Removed Property",
        property_url="https://example.com/p2",
        building_name="C棟",
        room_number="301",
        rent="100,000円",
        common_fee="5,000円",
        layout="2LDK",
        floor_area="70㎡",
        floor="10階",
        room_url="https://example.com/p2/rooms/301",
        first_seen="2024-12-01",
        last_seen="2025-02-01",
        active=False,
    )

    summary = RunSummary(
        executed_at="2025-03-01T00:00:00",
        property_diff=DiffResult(
            added=[added_listing],
            removed=[removed_listing],
            unchanged=[],
        ),
        room_diffs={
            "P1":
            DiffResult(
                added=[new_property_room],
                removed=[],
                unchanged=[],
            ),
            "P2":
            DiffResult(
                added=[],
                removed=[removed_property_room],
                unchanged=[],
            ),
            "P3":
            DiffResult(
                added=[existing_room_added],
                removed=[existing_room_removed],
                unchanged=[],
            ),
        },
        availability_changes={},
    )

    messages = format_notifications(summary)
    assert len(messages) == 4
    assert any("新しい物件が追加されました" in message for message in messages)
    assert any("掲載終了" in message for message in messages)
    assert any("空室が追加されました" in message for message in messages)
    assert any("空室がなくなりました" in message for message in messages)
    assert any("住所: 新宿区北新宿3-27-3" in message for message in messages)
    assert any("空室データ: 1件が満室になりました" in message for message in messages)


def test_format_notifications_includes_availability_change():
    change = AvailabilityChange(
        property_id="P4",
        property_name="Existing Property",
        property_url="https://example.com/p4",
        previous_count=0,
        current_count=3,
    )

    summary = RunSummary(
        executed_at="2025-03-02T00:00:00",
        property_diff=DiffResult(added=[], removed=[], unchanged=[]),
        room_diffs={},
        availability_changes={"P4": change},
    )

    messages = format_notifications(summary)
    assert len(messages) == 1
    assert "対象空室数が変動しました" in messages[0]
    assert "0 -> 3" in messages[0]
    assert "Existing Property" in messages[0]


def test_format_notifications_returns_empty_when_no_changes():
    summary = RunSummary(
        executed_at="2025-03-01T00:00:00",
        property_diff=DiffResult(added=[], removed=[], unchanged=[]),
        room_diffs={},
        availability_changes={},
    )
    assert format_notifications(summary) == []


def test_build_notifier_from_env(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK", raising=False)
    monkeypatch.delenv("LINE_NOTIFY_TOKEN", raising=False)

    assert build_notifier_from_env() is None

    monkeypatch.setenv("SLACK_WEBHOOK",
                       "https://hooks.slack.com/services/test")
    monkeypatch.setenv("LINE_NOTIFY_TOKEN", "token123")

    composite = build_notifier_from_env()
    assert composite is not None
    assert len(composite.notifiers) == 2
