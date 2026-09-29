"""Azure HTTP adapters for OMS queries and custom log ingestion."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Protocol
from urllib.request import Request, urlopen

from workspaces.data_engineering.agents.oms_agent import (
    OmsEnvironment,
    OmsJobQueryParameters,
    OmsLogRecord,
    OmsQuery,
    OmsQueryResult,
    OmsRegion,
    OmsWorkspace,
    build_oms_job_query,
    resolve_workspace,
)

LOG_ANALYTICS_SCOPE = "https://api.loganalytics.io"
HTTP_OK = 200
HTTP_ACCEPTED = 202


class OmsAdapterError(RuntimeError):
    """Raised when Azure authentication or OMS responses are invalid."""

    @classmethod
    def empty_token(cls) -> OmsAdapterError:
        """Return an error for missing Azure CLI token output."""
        return cls("Azure CLI returned an empty access token")

    @classmethod
    def query_http(cls, status: int) -> OmsAdapterError:
        """Return an error for a failed query response."""
        return cls(f"OMS query failed with HTTP {status}")

    @classmethod
    def invalid_query_response(cls) -> OmsAdapterError:
        """Return an error for malformed query data."""
        return cls("OMS query response has an invalid shape")

    @classmethod
    def write_http(cls, status: int) -> OmsAdapterError:
        """Return an error for a failed write response."""
        return cls(f"OMS log write failed with HTTP {status}")

    @classmethod
    def invalid_shared_key(cls) -> OmsAdapterError:
        """Return an error for a malformed workspace shared key."""
        return cls("OMS shared key must be valid base64")


class OmsHttpTransport(Protocol):
    """Small injectable boundary for authenticated OMS HTTP calls."""

    def request(self, request: Request) -> tuple[int, bytes]:
        """Execute one HTTP request and return status plus body."""
        ...


class UrllibOmsTransport:
    """Execute OMS HTTP requests with the standard library."""

    def request(self, request: Request) -> tuple[int, bytes]:
        """Execute one request with a bounded timeout."""
        with urlopen(request, timeout=30) as response:
            return response.status, response.read()


class AzureCliTokenSource:
    """Acquire a Log Analytics bearer token from the active Azure CLI session."""

    def access_token(self, subscription_id: str) -> str:
        """Return a token scoped to Log Analytics for one subscription."""
        result = subprocess.run(
            (
                "az",
                "account",
                "get-access-token",
                "--subscription",
                subscription_id,
                "--resource",
                LOG_ANALYTICS_SCOPE,
                "--query",
                "accessToken",
                "--output",
                "tsv",
            ),
            check=True,
            capture_output=True,
            text=True,
        )
        token = result.stdout.strip()
        if not token:
            raise OmsAdapterError.empty_token()
        return token


@dataclass(frozen=True, slots=True)
class AzureLogAnalyticsSource:
    """Query Azure Log Analytics through an injected token and HTTP boundary."""

    token_source: AzureCliTokenSource
    transport: OmsHttpTransport

    @classmethod
    def create(cls) -> AzureLogAnalyticsSource:
        """Create the production adapter using Azure CLI authentication."""
        return cls(AzureCliTokenSource(), UrllibOmsTransport())

    async def query(
        self,
        workspace: OmsWorkspace,
        query: OmsQuery,
    ) -> OmsQueryResult:
        """Execute one bounded Log Analytics query."""
        return await asyncio.to_thread(self._query, workspace, query)

    def _query(self, workspace: OmsWorkspace, query: OmsQuery) -> OmsQueryResult:
        token = self.token_source.access_token(workspace.subscription_id)
        body = json.dumps({"query": query.kql, "timespan": query.timespan}).encode()
        request = Request(
            f"https://api.loganalytics.io/v1/workspaces/{workspace.workspace_id}/query",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        status, payload = self.transport.request(request)
        if status != HTTP_OK:
            raise OmsAdapterError.query_http(status)
        try:
            response = json.loads(payload)
            table = response["tables"][0]
            columns = tuple(column["name"] for column in table["columns"])
            rows = tuple(tuple(row) for row in table["rows"])
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise OmsAdapterError.invalid_query_response() from error
        return OmsQueryResult(columns=columns, rows=rows)


@dataclass(frozen=True, slots=True)
class AzureOmsJobEvidenceSource:
    """Render exact production job evidence from bounded OMS query results."""

    source: AzureLogAnalyticsSource

    @classmethod
    def create(cls) -> AzureOmsJobEvidenceSource:
        """Create the production job-evidence adapter."""
        return cls(AzureLogAnalyticsSource.create())

    async def query_job(self, parameters: OmsJobQueryParameters) -> str:
        """Return deterministic JSON lines for one exact workload attempt."""
        job_query = build_oms_job_query(parameters)
        region = parameters.region
        if not isinstance(region, OmsRegion):
            message = f"unsupported normalized OMS region: {region!r}"
            raise OmsAdapterError(message)
        workspace = resolve_workspace(OmsEnvironment.PRODUCTION, region)
        result = await self.source.query(
            workspace,
            OmsQuery(
                kql=job_query.kql,
                timespan=(
                    f"{job_query.window_start.isoformat()}/"
                    f"{job_query.window_end.isoformat()}"
                ),
            ),
        )
        return _render_rows(result)


@dataclass(frozen=True, slots=True)
class OmsDataCollectorSink:
    """Append custom logs using an explicitly injected workspace shared key."""

    shared_key: str
    transport: OmsHttpTransport

    async def write(
        self,
        workspace: OmsWorkspace,
        record: OmsLogRecord,
    ) -> None:
        """Append one signed custom log record."""
        await asyncio.to_thread(self._write, workspace, record)

    def _write(self, workspace: OmsWorkspace, record: OmsLogRecord) -> None:
        body = json.dumps([dict(record.fields)], sort_keys=True).encode()
        date = format_datetime(datetime.now(UTC), usegmt=True)
        signature = _signature(workspace.workspace_id, self.shared_key, date, body)
        request = Request(
            (
                f"https://{workspace.workspace_id}.ods.opinsights.azure.com"
                "/api/logs?api-version=2016-04-01"
            ),
            data=body,
            headers={
                "Authorization": signature,
                "Content-Type": "application/json",
                "Log-Type": record.log_type,
                "x-ms-date": date,
            },
            method="POST",
        )
        status, _ = self.transport.request(request)
        if status not in {HTTP_OK, HTTP_ACCEPTED}:
            raise OmsAdapterError.write_http(status)


def _signature(
    workspace_id: str,
    shared_key: str,
    date: str,
    body: bytes,
) -> str:
    """Build the OMS Data Collector API authorization header."""
    content_hash = f"POST\n{len(body)}\napplication/json\nx-ms-date:{date}\n/api/logs"
    try:
        key = base64.b64decode(shared_key, validate=True)
    except ValueError as error:
        raise OmsAdapterError.invalid_shared_key() from error
    digest = hmac.new(key, content_hash.encode(), hashlib.sha256).digest()
    encoded = base64.b64encode(digest).decode()
    return f"SharedKey {workspace_id}:{encoded}"


def _render_rows(result: OmsQueryResult) -> str:
    """Render tabular OMS evidence without dropping diagnostic columns."""
    return "\n".join(
        json.dumps(
            dict(zip(result.columns, row, strict=True)),
            sort_keys=True,
            default=str,
        )
        for row in result.rows
    )
