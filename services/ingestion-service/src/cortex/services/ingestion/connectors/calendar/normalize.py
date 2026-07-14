"""Normalize Google Calendar v3 events into RawEvent."""

from __future__ import annotations

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.services.ingestion.connectors._common import parse_ts


def _when(slot: dict | None) -> str | None:
    if not slot:
        return None
    return slot.get("dateTime") or slot.get("date")


def normalize_event(calendar_id: str, event: dict) -> RawEvent:
    event_id = event.get("id", "")
    organizer = event.get("organizer") or {}
    attendees = [a.get("email") for a in event.get("attendees", []) if a.get("email")]
    return RawEvent(
        source=Source.CALENDAR,
        kind="event",
        external_id=f"calendar:{calendar_id}:{event_id}",
        occurred_at=parse_ts(event.get("updated") or _when(event.get("start"))),
        actor=organizer.get("email"),
        title=event.get("summary"),
        body=event.get("description"),
        attributes={
            "calendar_id": calendar_id,
            "event_id": event_id,
            "status": event.get("status"),
            "start": _when(event.get("start")),
            "end": _when(event.get("end")),
            "location": event.get("location"),
            "attendees": attendees,
            "recurring_event_id": event.get("recurringEventId"),
            "html_link": event.get("htmlLink"),
        },
    )
