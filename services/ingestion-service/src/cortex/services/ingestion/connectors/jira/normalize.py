"""Normalize Jira Cloud REST v3 issues into RawEvent."""

from __future__ import annotations

from typing import Any

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.services.ingestion.connectors._common import parse_ts


def _plain_text(value: Any) -> str | None:
    """Flatten an Atlassian Document Format body (or plain string) to text."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and node.get("text"):
                out.append(node["text"])
            for child in node.get("content", []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    text = " ".join(out).strip()
    return text or None


def normalize_issue(issue: dict) -> RawEvent:
    key = issue.get("key", "")
    fields = issue.get("fields", {}) or {}
    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    status = (fields.get("status") or {}).get("name")
    priority = (fields.get("priority") or {}).get("name")
    issuetype = (fields.get("issuetype") or {}).get("name")
    return RawEvent(
        source=Source.JIRA,
        kind="issue",
        external_id=f"jira:{key}",
        occurred_at=parse_ts(fields.get("updated") or fields.get("created")),
        actor=assignee.get("displayName") or assignee.get("emailAddress")
        or reporter.get("displayName"),
        title=fields.get("summary"),
        body=_plain_text(fields.get("description")),
        attributes={
            "key": key,
            "status": status,
            "priority": priority,
            "issue_type": issuetype,
            "project": (fields.get("project") or {}).get("key"),
            "reporter": reporter.get("displayName"),
            "labels": fields.get("labels", []),
            "url": issue.get("self"),
        },
    )
