"""Normalize PagerDuty REST v2 incidents into RawEvent."""

from __future__ import annotations

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.services.ingestion.connectors._common import parse_ts


def normalize_incident(incident: dict) -> RawEvent:
    inc_id = incident.get("id", "")
    service = (incident.get("service") or {}).get("summary")
    assignments = incident.get("assignments", []) or []
    assignee = None
    if assignments:
        assignee = (assignments[0].get("assignee") or {}).get("summary")
    return RawEvent(
        source=Source.PAGERDUTY,
        kind="incident",
        external_id=f"pagerduty:{inc_id}",
        occurred_at=parse_ts(incident.get("last_status_change_at")
                             or incident.get("updated_at") or incident.get("created_at")),
        actor=assignee,
        title=incident.get("title") or incident.get("summary"),
        body=(incident.get("description") or None),
        attributes={
            "id": inc_id,
            "incident_number": incident.get("incident_number"),
            "status": incident.get("status"),
            "urgency": incident.get("urgency"),
            "priority": (incident.get("priority") or {}).get("summary"),
            "service": service,
            "escalation_policy": (incident.get("escalation_policy") or {}).get("summary"),
            "created_at": incident.get("created_at"),
            "html_url": incident.get("html_url"),
        },
    )
