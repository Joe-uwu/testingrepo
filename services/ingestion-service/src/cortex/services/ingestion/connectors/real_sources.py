"""Backward-compatible re-exports.

The real connectors moved into per-source subpackages (slack/, jira/, notion/, calendar/,
pagerduty/), each mirroring the github/ package: auth, RestClient wiring, sync, normalize,
config factory. This module keeps the original import path
(``cortex.services.ingestion.connectors.real_sources``) working.
"""

from __future__ import annotations

from cortex.services.ingestion.connectors.calendar import CalendarConnector
from cortex.services.ingestion.connectors.jira import JiraConnector
from cortex.services.ingestion.connectors.notion import NotionConnector
from cortex.services.ingestion.connectors.pagerduty import PagerDutyConnector
from cortex.services.ingestion.connectors.slack import SlackConnector

__all__ = [
    "SlackConnector",
    "JiraConnector",
    "NotionConnector",
    "CalendarConnector",
    "PagerDutyConnector",
]
