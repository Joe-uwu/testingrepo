"""Connector implementations: one mock twin plus a real connector per source.

Each real source lives in its own subpackage mirroring github/: auth, a rate-limited/retrying
REST client (shared _common.RestClient for the five non-GitHub sources), sync (initial +
incremental), normalization to RawEvent, and a config factory that returns None when the
source has no credentials so the service stays up on the mock twin.
"""

from cortex.services.ingestion.connectors.calendar import (
    CalendarConnector,
    CalendarSettings,
    build_calendar_connector,
)
from cortex.services.ingestion.connectors.github import GitHubConnector
from cortex.services.ingestion.connectors.jira import (
    JiraConnector,
    JiraSettings,
    build_jira_connector,
)
from cortex.services.ingestion.connectors.mock import MockConnector
from cortex.services.ingestion.connectors.notion import (
    NotionConnector,
    NotionSettings,
    build_notion_connector,
)
from cortex.services.ingestion.connectors.pagerduty import (
    PagerDutyConnector,
    PagerDutySettings,
    build_pagerduty_connector,
)
from cortex.services.ingestion.connectors.slack import (
    SlackConnector,
    SlackSettings,
    build_slack_connector,
)

__all__ = [
    "MockConnector",
    "GitHubConnector",
    "SlackConnector", "SlackSettings", "build_slack_connector",
    "JiraConnector", "JiraSettings", "build_jira_connector",
    "NotionConnector", "NotionSettings", "build_notion_connector",
    "CalendarConnector", "CalendarSettings", "build_calendar_connector",
    "PagerDutyConnector", "PagerDutySettings", "build_pagerduty_connector",
]
