"""Slack connector: Web API message ingestion (conversations.list + history)."""

from cortex.services.ingestion.connectors.slack.config import SlackSettings, build_slack_connector
from cortex.services.ingestion.connectors.slack.connector import SlackConnector, SlackError
from cortex.services.ingestion.connectors.slack.normalize import normalize_message

__all__ = [
    "SlackConnector",
    "SlackError",
    "SlackSettings",
    "build_slack_connector",
    "normalize_message",
]
