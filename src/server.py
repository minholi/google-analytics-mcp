"""
Google Analytics MCP Server
MCP server for integrating with the Google Analytics 4 Data API.
Supports stdio (local) and HTTP (remote/team) transports.
"""

import json
import logging
import os
import sys
from datetime import date, timedelta
from enum import StrEnum

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from pydantic import BaseModel, ConfigDict, Field

from .auth import GoogleAnalyticsAuth
from .client import GoogleAnalyticsClient
from .formatters import (
    format_audience,
    format_conversions,
    format_events,
    format_geographic_performance,
    format_overview,
    format_realtime,
    format_top_pages,
    format_traffic_sources,
)

# ---------------------------------------------------------------------------
# Logging — use stderr to avoid polluting the MCP stdio channel
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("google_analytics_mcp")

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
INSTRUCTIONS = (
    "MCP server for Google Analytics 4. "
    "Use the tools to analyze traffic, acquisition sources, top pages, "
    "geographic performance, audience by device/browser, events, conversions and "
    "realtime data. "
    "All data comes directly from the GA4 Data API in real time. "
    "Dates must be in YYYY-MM-DD format. "
    "Default property_id is read from GOOGLE_ANALYTICS_PROPERTY_ID "
    "(can be overridden per tool call)."
)

# Google scopes required to authenticate the user and call the GA4 Data API.
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/analytics.readonly",
]


def _build_fastmcp() -> FastMCP:
    """Builds FastMCP with (or without) `GoogleProvider` depending on the environment.

    If `MCP_PUBLIC_URL` is set, we enable fastmcp's `GoogleProvider`, which acts
    as Authorization Server + Resource Server: performs DCR (RFC 7591), proxies
    OAuth 2.1 with PKCE to Google, persists the encrypted Google refresh_token,
    handles transparent refresh and exposes the Google access_token via
    `get_access_token().token` for the tools to call the GA4 Data API.

    In stdio (without MCP_PUBLIC_URL) there is no MCP auth and we use env vars as usual.
    """
    public_url = os.environ.get("MCP_PUBLIC_URL", "").rstrip("/")
    if not public_url:
        return FastMCP("google_analytics_mcp", instructions=INSTRUCTIONS)

    from fastmcp.server.auth.providers.google import GoogleProvider

    client_id = os.environ.get("GOOGLE_OAUTH_WEB_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_OAUTH_WEB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_OAUTH_WEB_CLIENT_ID and GOOGLE_OAUTH_WEB_CLIENT_SECRET are "
            "required in HTTP mode (create a 'Web application' OAuth Client "
            "in GCP with redirect_uri = MCP_PUBLIC_URL/auth/callback)."
        )

    auth = GoogleProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=public_url,
        required_scopes=GOOGLE_OAUTH_SCOPES,
        # Can be provided to reproduce the signing key across processes/replicas;
        # if absent, GoogleProvider derives a key from the client_secret.
        jwt_signing_key=os.environ.get("OAUTH_JWT_SIGNING_KEY") or None,
    )
    return FastMCP("google_analytics_mcp", instructions=INSTRUCTIONS, auth=auth)


mcp = _build_fastmcp()


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------


class ResponseFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


class DateRange(StrEnum):
    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


class TrafficGroupBy(StrEnum):
    CHANNEL = "channel"
    SOURCE_MEDIUM = "source_medium"
    CAMPAIGN = "campaign"


class GeoGranularity(StrEnum):
    COUNTRY = "country"
    REGION = "region"
    CITY = "city"


class AudienceBreakdown(StrEnum):
    DEVICE = "deviceCategory"
    BROWSER = "browser"
    OS = "operatingSystem"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client(property_id: str | None = None) -> GoogleAnalyticsClient:
    """Creates an authenticated client.

    Priority:
      1. OAuth user from context (multi-tenant HTTP flow) — uses the Google
         access_token delivered by fastmcp's `GoogleProvider`, which already
         handles transparent upstream refresh.
      2. Fallback via `GOOGLE_ANALYTICS_*` env vars (stdio / admin / dev mode).
    """
    token = get_access_token()
    if token is not None:
        auth = GoogleAnalyticsAuth.for_access_token(access_token=token.token)
    else:
        auth = GoogleAnalyticsAuth.from_env()
    pid = property_id or os.environ.get("GOOGLE_ANALYTICS_PROPERTY_ID", "")
    if not pid:
        raise ValueError(
            "property_id not provided and GOOGLE_ANALYTICS_PROPERTY_ID is not set. "
            "Pass property_id as a parameter or set the environment variable."
        )
    return GoogleAnalyticsClient(auth=auth, property_id=pid)


def _resolve_dates(
    date_range: DateRange,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    """Resolves the period to absolute YYYY-MM-DD dates."""
    today = date.today()
    match date_range:
        case DateRange.LAST_7_DAYS:
            return str(today - timedelta(days=7)), str(today - timedelta(days=1))
        case DateRange.LAST_14_DAYS:
            return str(today - timedelta(days=14)), str(today - timedelta(days=1))
        case DateRange.LAST_30_DAYS:
            return str(today - timedelta(days=30)), str(today - timedelta(days=1))
        case DateRange.THIS_MONTH:
            return str(today.replace(day=1)), str(today)
        case DateRange.LAST_MONTH:
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            return str(last_prev.replace(day=1)), str(last_prev)
        case DateRange.CUSTOM:
            if not start_date or not end_date:
                raise ValueError(
                    "For date_range='custom', provide start_date and end_date in YYYY-MM-DD format."
                )
            return start_date, end_date
    return str(today - timedelta(days=7)), str(today - timedelta(days=1))


def _safe_run(fn, *args, **kwargs) -> str:
    """Wrapper that captures exceptions and returns a user-friendly message."""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        return f"❌ Configuration error: {e}"
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            if os.environ.get("MCP_PUBLIC_URL"):
                return (
                    "❌ Authentication failed. The Google access_token was rejected — "
                    "reconnect the server in the MCP client (revoke and redo the consent)."
                )
            return (
                "❌ Authentication failed. Check GOOGLE_ANALYTICS_REFRESH_TOKEN "
                "and GOOGLE_ANALYTICS_CLIENT_SECRET."
            )
        if code == 403:
            return (
                "❌ Permission denied. Check that the account has access to the "
                "requested GA4 property."
            )
        if code == 429:
            return "❌ Rate limit reached. Wait a few moments and try again."
        return f"❌ HTTP {code} error calling the GA4 Data API: {e.response.text[:300]}"
    except httpx.TimeoutException:
        return "❌ API call timed out. Try shortening the period or reducing the metrics."
    except Exception as e:
        logger.exception("Unexpected error")
        return f"❌ Unexpected error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class OverviewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description=(
            "Numeric GA4 property ID (e.g. 123456789). "
            "If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID from the environment."
        ),
    )
    date_range: DateRange = Field(
        default=DateRange.LAST_7_DAYS,
        description=(
            "Period: last_7_days (default), last_14_days, last_30_days, "
            "this_month, last_month or custom."
        ),
    )
    start_date: str | None = Field(
        default=None,
        description="Start date for date_range='custom'. Format: YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    end_date: str | None = Field(
        default=None,
        description="End date for date_range='custom'. Format: YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    compare_previous: bool = Field(
        default=False,
        description="If True, includes a comparison against the previous same-sized period.",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' for human reading (default) or 'json' for structured data.",
    )


class TrafficSourcesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    group_by: TrafficGroupBy = Field(
        default=TrafficGroupBy.CHANNEL,
        description="Grouping: 'channel' (default), 'source_medium' or 'campaign'.",
    )
    limit: int = Field(default=25, ge=1, le=100, description="Max rows to return (1–100).")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class TopPagesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    limit: int = Field(default=25, ge=1, le=100)
    page_path_filter: str | None = Field(
        default=None,
        description=(
            "Filter pages whose path starts with this prefix (e.g. '/blog', '/products')."
        ),
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GeographicPerformanceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_30_DAYS)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    granularity: GeoGranularity = Field(
        default=GeoGranularity.COUNTRY,
        description="Geographic level: 'country' (default), 'region' or 'city'.",
    )
    limit: int = Field(default=25, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AudienceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    breakdown: AudienceBreakdown = Field(
        default=AudienceBreakdown.DEVICE,
        description="Dimension: 'deviceCategory' (default), 'browser' or 'operatingSystem'.",
    )
    limit: int = Field(default=25, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class EventsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    event_names: list[str] | None = Field(
        default=None,
        description=(
            "Filter only these events (e.g. ['purchase', 'sign_up']). If None, returns all."
        ),
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ConversionsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_30_DAYS)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class RealtimeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: str | None = Field(
        default=None,
        description="Numeric GA4 property ID. If omitted, uses GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="google_analytics_get_overview",
    annotations={
        "title": "Google Analytics Overview",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_overview(params: OverviewInput) -> str:
    """Returns the main KPIs of the GA4 property for the selected period.

    Metrics: sessions, active users, new users, pageviews, bounce rate,
    average session duration, engagement rate and conversions.
    With compare_previous=True, includes a percentage comparison against
    the previous period.

    Args:
        params (OverviewInput): property_id, period, compare_previous, format.

    Returns:
        str: KPIs as markdown (default) or structured JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_overview(
            start_date=start,
            end_date=end,
            compare_previous=params.compare_previous,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_overview(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_traffic_sources",
    annotations={
        "title": "Google Analytics Traffic Sources",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_traffic_sources(params: TrafficSourcesInput) -> str:
    """Returns traffic acquisition grouped by channel, source/medium or campaign.

    Per-source metrics: sessions, users, new users, bounce rate,
    engagement rate and conversions.

    Args:
        params (TrafficSourcesInput): property_id, period, group_by
            (channel/source_medium/campaign), limit and format.

    Returns:
        str: Traffic sources table as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_traffic_sources(
            start_date=start,
            end_date=end,
            group_by=params.group_by.value,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_traffic_sources(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_top_pages",
    annotations={
        "title": "Google Analytics Top Pages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_top_pages(params: TopPagesInput) -> str:
    """Lists the most visited pages with engagement metrics.

    Returns pageviews, sessions, active users, bounce rate and average
    session duration per page. Supports filtering by path prefix.

    Args:
        params (TopPagesInput): property_id, period, limit, page_path_filter and format.

    Returns:
        str: Pages ordered by pageviews as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_top_pages(
            start_date=start,
            end_date=end,
            limit=params.limit,
            page_path_filter=params.page_path_filter,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_top_pages(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_geographic_performance",
    annotations={
        "title": "Google Analytics Geographic Performance",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_geographic_performance(
    params: GeographicPerformanceInput,
) -> str:
    """Returns performance by geographic location (country, region or city).

    Metrics: sessions, active users, new users, conversions and bounce rate.
    Highlights the location with the most conversions and the one with
    the most sessions without conversions.

    Args:
        params (GeographicPerformanceInput): property_id, period, granularity
            (country/region/city), limit and format.

    Returns:
        str: Geographic table with metrics and highlights as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_geographic_performance(
            start_date=start,
            end_date=end,
            granularity=params.granularity.value,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_geographic_performance(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_audience",
    annotations={
        "title": "Google Analytics Audience",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_audience(params: AudienceInput) -> str:
    """Returns audience breakdown by device, browser or operating system.

    Metrics: sessions, active users, pageviews, bounce rate and engagement.

    Args:
        params (AudienceInput): property_id, period, breakdown
            (deviceCategory/browser/operatingSystem), limit and format.

    Returns:
        str: Audience table as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_audience(
            start_date=start,
            end_date=end,
            breakdown=params.breakdown.value,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_audience(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_events",
    annotations={
        "title": "Google Analytics Events",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_events(params: EventsInput) -> str:
    """Lists the most-triggered events on the GA4 property.

    Returns event name, total count, count per user and total users.
    With event_names, filters to only the specified events.

    Args:
        params (EventsInput): property_id, period, event_names (optional filter),
            limit and format.

    Returns:
        str: Events ordered by count as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_events(
            start_date=start,
            end_date=end,
            event_names=params.event_names,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_events(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_conversions",
    annotations={
        "title": "Google Analytics Conversions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_conversions(params: ConversionsInput) -> str:
    """Returns conversion and revenue data by channel and conversion event.

    Only events flagged as conversions in GA4 appear here.
    Includes conversion and revenue totals.

    Args:
        params (ConversionsInput): property_id, period, limit and format.

    Returns:
        str: Conversions table with revenue as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_conversions(
            start_date=start,
            end_date=end,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_conversions(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_realtime",
    annotations={
        "title": "Google Analytics Realtime Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def google_analytics_get_realtime(params: RealtimeInput) -> str:
    """Returns realtime data on currently active users (last 30 minutes).

    Shows total active users and breakdowns by page, source, country
    and device. Does not accept a date_range — always reflects the current state.

    Args:
        params (RealtimeInput): property_id and format.

    Returns:
        str: Active users and breakdowns as markdown or JSON.
    """

    def _run():
        client = _get_client(params.property_id)
        data = client.get_realtime()
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_realtime(data)

    return _safe_run(_run)
