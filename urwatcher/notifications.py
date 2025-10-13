"""Notification helpers for delivering diff results to external channels."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable, List, Protocol

import requests

from .models import (
    DiffResult,
    Listing,
    ListingRecord,
    Room,
    RoomRecord,
    RunSummary,
)

logger = logging.getLogger(__name__)

LINE_NOTIFY_ENDPOINT = "https://notify-api.line.me/api/notify"
MAX_ROOMS_PER_MESSAGE = 5


class Notifier(Protocol):
    """Protocol defining the notifier contract."""

    def send(self, message: str) -> None:
        ...


@dataclass
class SlackNotifier:
    """Send messages to Slack via Incoming Webhook."""

    webhook_url: str
    timeout: int = 10

    def send(self, message: str) -> None:
        payload = {"text": message}
        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()


@dataclass
class LineNotifier:
    """Send messages via LINE Notify."""

    access_token: str
    timeout: int = 10

    def send(self, message: str) -> None:
        response = requests.post(
            LINE_NOTIFY_ENDPOINT,
            headers={"Authorization": f"Bearer {self.access_token}"},
            data={"message": message},
            timeout=self.timeout,
        )
        response.raise_for_status()


@dataclass
class CompositeNotifier:
    """Fan-out notifier that forwards messages to multiple channels."""

    notifiers: List[Notifier]

    def send(self, message: str) -> None:
        for notifier in self.notifiers:
            try:
                notifier.send(message)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to deliver notification via %s", type(notifier).__name__)


def build_notifier_from_env() -> CompositeNotifier | None:
    """Construct a notifier from environment configuration."""
    notifiers: list[Notifier] = []

    slack_webhook = (os.getenv("SLACK_WEBHOOK") or "").strip()
    if slack_webhook:
        notifiers.append(SlackNotifier(webhook_url=slack_webhook))

    line_token = (os.getenv("LINE_NOTIFY_TOKEN") or "").strip()
    if line_token:
        notifiers.append(LineNotifier(access_token=line_token))

    if not notifiers:
        return None
    return CompositeNotifier(notifiers=notifiers)


def format_notifications(summary: RunSummary) -> List[str]:
    """Render diff results into human-friendly notification payloads."""
    messages: List[str] = []
    added_ids = {listing.property_id for listing in summary.property_diff.added}
    removed_ids = {record.property_id for record in summary.property_diff.removed}

    for listing in summary.property_diff.added:
        room_lines = _format_room_additions(summary.room_diffs.get(listing.property_id))
        message_lines = [
            ":new: 新しい物件が追加されました",
            f"物件名: {listing.name}",
        ]
        address_line = _format_address_line(listing.address)
        if address_line:
            message_lines.append(address_line)
        message_lines.append(f"URL: {listing.url}")
        message_lines.extend(room_lines)
        messages.append("\n".join(message_lines))

    for record in summary.property_diff.removed:
        room_diff = summary.room_diffs.get(record.property_id)
        removed_count = len(room_diff.removed) if room_diff else 0
        message_lines = [
            ":x: 掲載終了",
            f"物件名: {record.name}",
        ]
        address_line = _format_address_line(record.address)
        if address_line:
            message_lines.append(address_line)
        message_lines.append(f"URL: {record.url}")
        if removed_count:
            message_lines.append(f"空室データ: {removed_count}件が満室になりました")
        messages.append("\n".join(message_lines))

    for property_id, room_diff in summary.room_diffs.items():
        if property_id in added_ids or property_id in removed_ids:
            continue
        if room_diff.added:
            message = _build_room_message(room_diff.added, added=True)
            if message:
                messages.append(message)
        if room_diff.removed:
            message = _build_room_message(room_diff.removed, added=False)
            if message:
                messages.append(message)

    return messages


def _format_room_additions(
    room_diff: DiffResult[Room, RoomRecord] | None,
) -> List[str]:
    if not room_diff or not room_diff.added:
        return []
    lines = ["空室情報:"]
    lines.extend(_summarize_room_entries(room_diff.added))
    if len(room_diff.added) > MAX_ROOMS_PER_MESSAGE:
        remaining = len(room_diff.added) - MAX_ROOMS_PER_MESSAGE
        lines.append(f"...ほか {remaining} 件")
    return lines


def _build_room_message(
    rooms: Iterable[Room] | Iterable[RoomRecord],
    *,
    added: bool,
) -> str:
    rooms_list = list(rooms)
    if not rooms_list:
        return ""
    first = rooms_list[0]
    property_name = first.property_name
    property_url = first.property_url
    header = ":door: 空室が追加されました" if added else ":no_entry: 空室がなくなりました"
    lines = [
        header,
        f"物件名: {property_name}",
        f"URL: {property_url}",
    ]
    lines.extend(_summarize_room_entries(rooms_list))
    if len(rooms_list) > MAX_ROOMS_PER_MESSAGE:
        remaining = len(rooms_list) - MAX_ROOMS_PER_MESSAGE
        lines.append(f"...ほか {remaining} 件")
    return "\n".join(lines)


def _summarize_room_entries(
    rooms: Iterable[Room] | Iterable[RoomRecord],
) -> List[str]:
    summaries: List[str] = []
    for idx, room in enumerate(rooms):
        if idx >= MAX_ROOMS_PER_MESSAGE:
            break
        rent = getattr(room, "rent", "") or "N/A"
        common_fee = getattr(room, "common_fee", "") or "N/A"
        layout = getattr(room, "layout", "") or "N/A"
        floor_area = getattr(room, "floor_area", "") or "N/A"
        floor = getattr(room, "floor", "") or "N/A"
        building = getattr(room, "building_name", "") or ""
        room_number = getattr(room, "room_number", "") or ""
        parts = [value for value in [building, room_number] if value]
        location = " ".join(parts) if parts else "部屋情報"
        summaries.append(
            f"- {location} | {layout} / {floor_area} / {floor} | 家賃: {rent} (共益費: {common_fee})"
        )
    return summaries


def _format_address_line(address: str | None) -> str | None:
    if not address:
        return None
    address = address.strip()
    if not address:
        return None
    return f"住所: {address}"


__all__ = [
    "CompositeNotifier",
    "LineNotifier",
    "Notifier",
    "SlackNotifier",
    "build_notifier_from_env",
    "format_notifications",
]
