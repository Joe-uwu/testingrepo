"""Normalize Slack Web API objects into RawEvent."""

from __future__ import annotations

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.services.ingestion.connectors._common import first_line, parse_ts


def normalize_message(channel: dict, msg: dict) -> RawEvent:
    channel_id = channel.get("id", "")
    channel_name = channel.get("name") or channel_id
    ts = str(msg.get("ts", ""))
    text = msg.get("text")
    return RawEvent(
        source=Source.SLACK,
        kind="message",
        external_id=f"slack:{channel_id}:{ts}",
        occurred_at=parse_ts(ts),
        actor=msg.get("user") or msg.get("bot_id"),
        title=first_line(text),
        body=text,
        attributes={
            "channel_id": channel_id,
            "channel": channel_name,
            "ts": ts,
            "thread_ts": msg.get("thread_ts"),
            "reply_count": msg.get("reply_count"),
            "subtype": msg.get("subtype"),
            "reactions": [r.get("name") for r in msg.get("reactions", []) if r.get("name")],
            "permalink": msg.get("permalink"),
        },
    )
