"""Normalize Notion API objects (pages/databases) into RawEvent."""

from __future__ import annotations

from typing import Any

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.services.ingestion.connectors._common import parse_ts


def _title_from_properties(props: dict) -> str | None:
    """Notion page titles live in whichever property has type 'title'."""
    for prop in props.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            parts = [t.get("plain_text", "") for t in prop.get("title", [])]
            text = "".join(parts).strip()
            return text or None
    return None


def _plain_title(obj: dict) -> str | None:
    """Databases carry a top-level 'title' rich-text array."""
    parts = [t.get("plain_text", "") for t in obj.get("title", []) if isinstance(t, dict)]
    text = "".join(parts).strip()
    return text or None


def normalize_object(obj: dict) -> RawEvent:
    kind = obj.get("object", "page")  # "page" or "database"
    obj_id = obj.get("id", "")
    props = obj.get("properties", {}) if isinstance(obj.get("properties"), dict) else {}
    title = _title_from_properties(props) or _plain_title(obj)
    edited_by = (obj.get("last_edited_by") or {}).get("id")
    return RawEvent(
        source=Source.NOTION,
        kind=kind,
        external_id=f"notion:{obj_id}",
        occurred_at=parse_ts(obj.get("last_edited_time") or obj.get("created_time")),
        actor=edited_by,
        title=title,
        body=None,
        attributes={
            "id": obj_id,
            "url": obj.get("url"),
            "archived": obj.get("archived"),
            "created_time": obj.get("created_time"),
            "last_edited_time": obj.get("last_edited_time"),
            "parent": _parent_ref(obj.get("parent")),
        },
    )


def _parent_ref(parent: Any) -> str | None:
    if not isinstance(parent, dict):
        return None
    for key in ("database_id", "page_id", "workspace"):
        if key in parent:
            return f"{key}:{parent[key]}"
    return None
