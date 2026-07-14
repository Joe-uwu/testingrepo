"""Jira Cloud connector: pull issues via the JQL search endpoint.

initial_sync runs a project-scoped JQL query paged by ``startAt``/``maxResults`` until the
reported ``total`` is reached; incremental_sync appends ``updated >= "<cursor>"`` to the JQL so
only recently-changed issues return. Jira push delivery is a webhook (separate endpoint), so
stream() is empty.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.platform.logging import get_logger
from cortex.services.ingestion.base import BaseConnector
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.jira.normalize import normalize_issue

log = get_logger("cortex.ingestion.jira")

_FIELDS = "summary,description,status,priority,issuetype,project,assignee,reporter,labels,updated,created"


class JiraConnector(BaseConnector):
    def __init__(
        self,
        client: RestClient,
        *,
        project: str | None = None,
        jql: str | None = None,
        page_size: int = 100,
        page_limit: int | None = None,
    ) -> None:
        super().__init__(Source.JIRA.value, rate_per_sec=10.0, capacity=20)
        self._client = client
        self._project = project
        self._base_jql = jql
        self._page_size = page_size
        self._page_limit = page_limit

    def initial_sync(self) -> Sequence[RawEvent]:
        return self._collect(since=None)

    def incremental_sync(self, since: str | None) -> Sequence[RawEvent]:
        return self._collect(since=since)

    def stream(self) -> Iterator[RawEvent]:
        return iter(())

    # --- internals ---------------------------------------------------------------

    def _jql(self, since: str | None) -> str:
        clauses: list[str] = []
        if self._base_jql:
            clauses.append(f"({self._base_jql})")
        elif self._project:
            clauses.append(f"project = {self._project}")
        if since:
            clauses.append(f'updated >= "{since}"')
        query = " AND ".join(clauses) if clauses else "order by updated desc"
        if "order by" not in query.lower():
            query += " ORDER BY updated DESC"
        return query

    def _collect(self, *, since: str | None) -> list[RawEvent]:
        jql = self._jql(since)
        events: list[RawEvent] = []
        start = 0
        while True:
            payload = self._client.get_json(
                "/rest/api/3/search",
                params={
                    "jql": jql, "startAt": start, "maxResults": self._page_size,
                    "fields": _FIELDS,
                },
            )
            issues = payload.get("issues", [])
            for issue in issues:
                events.append(normalize_issue(issue))
                if self._page_limit is not None and len(events) >= self._page_limit:
                    issues = []
                    break
            total = payload.get("total", 0)
            start += len(issues)
            if not issues or start >= total or self._page_limit is not None:
                break
        deduped = [e for e in events if self.dedup(e.external_id)]
        log.info("jira sync", extra={"extra_fields": {"since": since, "events": len(deduped)}})
        return deduped
