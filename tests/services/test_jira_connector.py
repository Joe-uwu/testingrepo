"""Jira connector tests: offset pagination, ADF flattening, JQL cursor, factory."""

from __future__ import annotations

import base64

import httpx

from cortex.contracts.enums import Source
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.jira import JiraConnector, JiraSettings, build_jira_connector


def _client(handler) -> RestClient:
    return RestClient(StaticAuth(base64.b64encode(b"e:t").decode(), scheme="Basic"),
                      base_url="https://acme.atlassian.net", source="jira",
                      http=httpx.Client(transport=httpx.MockTransport(handler)))


def _issue(key: str, updated: str) -> dict:
    return {
        "key": key,
        "self": f"https://acme.atlassian.net/rest/api/3/issue/{key}",
        "fields": {
            "summary": f"Summary {key}",
            "description": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "hello world"}]}
            ]},
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "issuetype": {"name": "Bug"},
            "project": {"key": "ENG"},
            "assignee": {"displayName": "Dana"},
            "reporter": {"displayName": "Sam"},
            "labels": ["backend"],
            "updated": updated,
        },
    }


def test_initial_sync_pages_by_offset():
    def handler(request):
        start = int(dict(request.url.params).get("startAt", 0))
        if start == 0:
            return httpx.Response(200, json={"startAt": 0, "maxResults": 2, "total": 3,
                                             "issues": [_issue("ENG-1", "2026-01-02T00:00:00.000+0000"),
                                                        _issue("ENG-2", "2026-01-02T00:00:00.000+0000")]})
        return httpx.Response(200, json={"startAt": 2, "maxResults": 2, "total": 3,
                                         "issues": [_issue("ENG-3", "2026-01-02T00:00:00.000+0000")]})

    conn = JiraConnector(_client(handler), project="ENG", page_size=2)
    events = list(conn.initial_sync())
    assert [e.external_id for e in events] == ["jira:ENG-1", "jira:ENG-2", "jira:ENG-3"]
    assert all(e.source == Source.JIRA for e in events)
    e = events[0]
    assert e.title == "Summary ENG-1"
    assert e.body == "hello world"  # ADF flattened to plain text
    assert e.actor == "Dana"
    assert e.attributes["status"] == "In Progress"
    assert e.attributes["priority"] == "High"


def test_incremental_adds_updated_clause():
    seen = {}

    def handler(request):
        seen["jql"] = dict(request.url.params).get("jql", "")
        return httpx.Response(200, json={"startAt": 0, "maxResults": 100, "total": 0, "issues": []})

    conn = JiraConnector(_client(handler), project="ENG")
    list(conn.incremental_sync("2026-06-01 00:00"))
    assert "project = ENG" in seen["jql"]
    assert 'updated >= "2026-06-01 00:00"' in seen["jql"]


def test_factory_requires_full_creds():
    assert build_jira_connector(JiraSettings(base_url="https://acme.atlassian.net")) is None
    ok = build_jira_connector(JiraSettings(
        base_url="https://acme.atlassian.net", email="e@x.com", api_token="tok", project="ENG"))
    assert isinstance(ok, JiraConnector)
