"""
Google Analytics 4 Data API client.
Uses httpx directly (no official SDK) for full control and minimal dependencies.

API: https://analyticsdata.googleapis.com/v1beta
Docs: https://developers.google.com/analytics/devguides/reporting/data/v1
"""

from typing import Any

import httpx

from .auth import GoogleAnalyticsAuth

GA4_API_VERSION = "v1beta"
GA4_BASE_URL = f"https://analyticsdata.googleapis.com/{GA4_API_VERSION}"
DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class GoogleAnalyticsClient:
    def __init__(self, auth: GoogleAnalyticsAuth, property_id: str):
        self.auth = auth
        # Normalize: strip the "properties/" prefix if the user included it
        self.property_id = property_id.replace("properties/", "").strip()
        self._property_resource = f"properties/{self.property_id}"

    # ── Low-level calls ─────────────────────────────────────────────────────

    def _post_report(self, body: dict) -> dict:
        """POST to :runReport. Automatic retry on 401 (token refresh)."""
        url = f"{GA4_BASE_URL}/{self._property_resource}:runReport"
        for attempt in range(2):
            headers = self.auth.build_headers()
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as http:
                response = http.post(url, headers=headers, json=body)
            if response.status_code == 401 and attempt == 0:
                self.auth.invalidate_token()
                continue
            response.raise_for_status()
            return response.json()
        return {}

    def _post_realtime(self, body: dict) -> dict:
        """POST to :runRealtimeReport. Automatic retry on 401."""
        url = f"{GA4_BASE_URL}/{self._property_resource}:runRealtimeReport"
        for attempt in range(2):
            headers = self.auth.build_headers()
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as http:
                response = http.post(url, headers=headers, json=body)
            if response.status_code == 401 and attempt == 0:
                self.auth.invalidate_token()
                continue
            response.raise_for_status()
            return response.json()
        return {}

    def _parse_rows(
        self,
        raw: dict,
        dimension_names: list[str],
        metric_names: list[str],
    ) -> list[dict]:
        """Converts GA4 response rows into flat dicts.

        GA4 returns dimensions and metrics by position (not by name):
          {"dimensionValues": [{"value": "/home"}], "metricValues": [{"value": "12345"}]}

        Returns: [{"pagePath": "/home", "screenPageViews": 12345, ...}]
        """
        rows = raw.get("rows", [])
        result = []
        for row in rows:
            entry: dict[str, Any] = {}
            dim_values = row.get("dimensionValues", [])
            met_values = row.get("metricValues", [])
            for i, name in enumerate(dimension_names):
                entry[name] = dim_values[i]["value"] if i < len(dim_values) else ""
            for i, name in enumerate(metric_names):
                entry[name] = met_values[i]["value"] if i < len(met_values) else "0"
            result.append(entry)
        return result

    # ── Data methods ────────────────────────────────────────────────────────

    def get_overview(
        self,
        start_date: str,
        end_date: str,
        compare_previous: bool = False,
    ) -> dict:
        """Main KPIs for the property. Optionally compares with the previous period."""
        metrics = [
            "sessions",
            "activeUsers",
            "newUsers",
            "screenPageViews",
            "bounceRate",
            "averageSessionDuration",
            "engagementRate",
            "conversions",
        ]
        date_ranges = [{"startDate": start_date, "endDate": end_date}]

        prev_start = prev_end = None
        if compare_previous:
            from datetime import date, timedelta

            s = date.fromisoformat(start_date)
            e = date.fromisoformat(end_date)
            delta = (e - s).days + 1
            prev_end_d = s - timedelta(days=1)
            prev_start_d = prev_end_d - timedelta(days=delta - 1)
            prev_start = str(prev_start_d)
            prev_end = str(prev_end_d)
            date_ranges.append({"startDate": prev_start, "endDate": prev_end})

        body: dict[str, Any] = {
            "dateRanges": date_ranges,
            "metrics": [{"name": m} for m in metrics],
        }
        # With multiple dateRanges, GA4 adds an implicit "dateRange" dimension
        if compare_previous:
            body["dimensions"] = [{"name": "dateRange"}]

        raw = self._post_report(body)

        if compare_previous:
            current: dict[str, Any] = {}
            previous: dict[str, Any] = {}
            for row in raw.get("rows", []):
                date_range_val = row["dimensionValues"][0]["value"]
                met_values = row.get("metricValues", [])
                target = current if date_range_val == "date_range_0" else previous
                for i, m in enumerate(metrics):
                    target[m] = met_values[i]["value"] if i < len(met_values) else "0"
            return {
                "current": _cast_overview(current, metrics),
                "previous": _cast_overview(previous, metrics),
                "previous_period": {"start": prev_start, "end": prev_end},
                "period": {"start": start_date, "end": end_date},
            }
        else:
            # No period breakdown — GA4 returns totals in a single row
            rows = raw.get("rows", [])
            raw_metrics: dict[str, Any] = {}
            if rows:
                met_values = rows[0].get("metricValues", [])
                for i, m in enumerate(metrics):
                    raw_metrics[m] = met_values[i]["value"] if i < len(met_values) else "0"
            return {
                "current": _cast_overview(raw_metrics, metrics),
                "previous": None,
                "period": {"start": start_date, "end": end_date},
            }

    def get_traffic_sources(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "channel",
        limit: int = 25,
    ) -> dict:
        """Traffic acquisition grouped by channel, source/medium or campaign."""
        metrics = [
            "sessions",
            "activeUsers",
            "newUsers",
            "bounceRate",
            "engagementRate",
            "conversions",
        ]

        if group_by == "source_medium":
            dimensions = ["sessionSource", "sessionMedium"]
        elif group_by == "campaign":
            dimensions = ["sessionDefaultChannelGroup", "sessionCampaignName"]
        else:  # channel
            dimensions = ["sessionDefaultChannelGroup"]

        body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        }
        raw = self._post_report(body)
        rows = self._parse_rows(raw, dimensions, metrics)

        result = []
        for row in rows:
            entry: dict[str, Any] = {}
            if group_by == "source_medium":
                entry["source"] = row.get("sessionSource", "")
                entry["medium"] = row.get("sessionMedium", "")
                entry["label"] = f"{entry['source']} / {entry['medium']}"
            elif group_by == "campaign":
                entry["channel"] = row.get("sessionDefaultChannelGroup", "")
                entry["campaign"] = row.get("sessionCampaignName", "")
                entry["label"] = entry["campaign"] or "(not set)"
            else:
                entry["channel"] = row.get("sessionDefaultChannelGroup", "")
                entry["label"] = entry["channel"] or "(not set)"

            entry["sessions"] = _parse_int(row.get("sessions"))
            entry["active_users"] = _parse_int(row.get("activeUsers"))
            entry["new_users"] = _parse_int(row.get("newUsers"))
            entry["bounce_rate"] = _parse_float(row.get("bounceRate"))
            entry["engagement_rate"] = _parse_float(row.get("engagementRate"))
            entry["conversions"] = _parse_float(row.get("conversions"))
            result.append(entry)

        return {
            "rows": result,
            "group_by": group_by,
            "count": len(result),
            "period": {"start": start_date, "end": end_date},
        }

    def get_top_pages(
        self,
        start_date: str,
        end_date: str,
        limit: int = 25,
        page_path_filter: str | None = None,
    ) -> dict:
        """Top pages by pageviews, with bounce rate and average duration."""
        dimensions = ["pagePath", "pageTitle"]
        metrics = [
            "screenPageViews",
            "sessions",
            "activeUsers",
            "averageSessionDuration",
            "bounceRate",
            "engagementRate",
        ]

        body: dict[str, Any] = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
        }

        if page_path_filter:
            body["dimensionFilter"] = {
                "filter": {
                    "fieldName": "pagePath",
                    "stringFilter": {
                        "matchType": "BEGINS_WITH",
                        "value": page_path_filter,
                    },
                }
            }

        raw = self._post_report(body)
        rows = self._parse_rows(raw, dimensions, metrics)

        pages = []
        for row in rows:
            pages.append(
                {
                    "path": row.get("pagePath", ""),
                    "title": row.get("pageTitle", ""),
                    "pageviews": _parse_int(row.get("screenPageViews")),
                    "sessions": _parse_int(row.get("sessions")),
                    "active_users": _parse_int(row.get("activeUsers")),
                    "avg_session_duration": _parse_float(row.get("averageSessionDuration")),
                    "bounce_rate": _parse_float(row.get("bounceRate")),
                    "engagement_rate": _parse_float(row.get("engagementRate")),
                }
            )

        return {
            "pages": pages,
            "count": len(pages),
            "filter": page_path_filter,
            "period": {"start": start_date, "end": end_date},
        }

    def get_geographic_performance(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "country",
        limit: int = 25,
    ) -> dict:
        """Performance by country, region or city."""
        dim_map = {"country": "country", "region": "region", "city": "city"}
        dimension = dim_map.get(granularity, "country")
        metrics = ["sessions", "activeUsers", "newUsers", "conversions", "bounceRate"]

        body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": dimension}],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        }
        raw = self._post_report(body)
        rows = self._parse_rows(raw, [dimension], metrics)

        locations = []
        for row in rows:
            locations.append(
                {
                    "name": row.get(dimension, ""),
                    "sessions": _parse_int(row.get("sessions")),
                    "active_users": _parse_int(row.get("activeUsers")),
                    "new_users": _parse_int(row.get("newUsers")),
                    "conversions": _parse_float(row.get("conversions")),
                    "bounce_rate": _parse_float(row.get("bounceRate")),
                }
            )

        return {
            "locations": locations,
            "granularity": granularity,
            "count": len(locations),
            "period": {"start": start_date, "end": end_date},
        }

    def get_audience(
        self,
        start_date: str,
        end_date: str,
        breakdown: str = "deviceCategory",
        limit: int = 25,
    ) -> dict:
        """Audience by device, browser or operating system."""
        valid_breakdowns = {"deviceCategory", "browser", "operatingSystem"}
        dimension = breakdown if breakdown in valid_breakdowns else "deviceCategory"
        metrics = ["sessions", "activeUsers", "screenPageViews", "bounceRate", "engagementRate"]

        body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": dimension}],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        }
        raw = self._post_report(body)
        rows = self._parse_rows(raw, [dimension], metrics)

        result = []
        for row in rows:
            result.append(
                {
                    "name": row.get(dimension, ""),
                    "sessions": _parse_int(row.get("sessions")),
                    "active_users": _parse_int(row.get("activeUsers")),
                    "pageviews": _parse_int(row.get("screenPageViews")),
                    "bounce_rate": _parse_float(row.get("bounceRate")),
                    "engagement_rate": _parse_float(row.get("engagementRate")),
                }
            )

        return {
            "rows": result,
            "breakdown": dimension,
            "count": len(result),
            "period": {"start": start_date, "end": end_date},
        }

    def get_events(
        self,
        start_date: str,
        end_date: str,
        event_names: list[str] | None = None,
        limit: int = 50,
    ) -> dict:
        """Top events by count, optionally filtered to specific event names."""
        dimensions = ["eventName"]
        metrics = ["eventCount", "eventCountPerUser", "totalUsers"]

        body: dict[str, Any] = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
        }

        if event_names:
            body["dimensionFilter"] = {
                "filter": {
                    "fieldName": "eventName",
                    "inListFilter": {"values": event_names},
                }
            }

        raw = self._post_report(body)
        rows = self._parse_rows(raw, dimensions, metrics)

        events = []
        for row in rows:
            events.append(
                {
                    "name": row.get("eventName", ""),
                    "count": _parse_int(row.get("eventCount")),
                    "count_per_user": _parse_float(row.get("eventCountPerUser")),
                    "total_users": _parse_int(row.get("totalUsers")),
                }
            )

        return {
            "events": events,
            "count": len(events),
            "filter": event_names,
            "period": {"start": start_date, "end": end_date},
        }

    def get_conversions(
        self,
        start_date: str,
        end_date: str,
        limit: int = 50,
    ) -> dict:
        """Conversion events with revenue, by channel and event name."""
        dimensions = ["sessionDefaultChannelGroup", "eventName"]
        metrics = ["conversions", "totalRevenue", "sessions"]

        body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "orderBys": [{"metric": {"metricName": "conversions"}, "desc": True}],
            "metricFilter": {
                "filter": {
                    "fieldName": "conversions",
                    "numericFilter": {
                        "operation": "GREATER_THAN",
                        "value": {"int64Value": "0"},
                    },
                }
            },
        }
        raw = self._post_report(body)
        rows = self._parse_rows(raw, dimensions, metrics)

        conversions = []
        total_conv = 0.0
        total_revenue = 0.0
        for row in rows:
            conv = _parse_float(row.get("conversions"))
            rev = _parse_float(row.get("totalRevenue"))
            total_conv += conv
            total_revenue += rev
            conversions.append(
                {
                    "channel": row.get("sessionDefaultChannelGroup", ""),
                    "event_name": row.get("eventName", ""),
                    "conversions": conv,
                    "revenue": rev,
                    "sessions": _parse_int(row.get("sessions")),
                }
            )

        return {
            "conversions": conversions,
            "totals": {"conversions": total_conv, "revenue": total_revenue},
            "count": len(conversions),
            "period": {"start": start_date, "end": end_date},
        }

    def get_realtime(self) -> dict:
        """Active users right now, by page, source, country and device."""
        # 1. Total active users
        total_raw = self._post_realtime(
            {
                "metrics": [{"name": "activeUsers"}],
            }
        )
        active_users = 0
        total_rows = total_raw.get("rows", [])
        if total_rows:
            active_users = _parse_int(total_rows[0]["metricValues"][0]["value"])

        # 2. By page
        pages_raw = self._post_realtime(
            {
                "dimensions": [{"name": "unifiedPagePathScreen"}],
                "metrics": [{"name": "activeUsers"}],
                "limit": 10,
                "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}],
            }
        )
        by_page = [
            {
                "page": row["dimensionValues"][0]["value"],
                "active_users": _parse_int(row["metricValues"][0]["value"]),
            }
            for row in pages_raw.get("rows", [])
        ]

        # 3. By source
        sources_raw = self._post_realtime(
            {
                "dimensions": [{"name": "firstUserSource"}],
                "metrics": [{"name": "activeUsers"}],
                "limit": 10,
                "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}],
            }
        )
        by_source = [
            {
                "source": row["dimensionValues"][0]["value"],
                "active_users": _parse_int(row["metricValues"][0]["value"]),
            }
            for row in sources_raw.get("rows", [])
        ]

        # 4. By country
        countries_raw = self._post_realtime(
            {
                "dimensions": [{"name": "country"}],
                "metrics": [{"name": "activeUsers"}],
                "limit": 10,
                "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}],
            }
        )
        by_country = [
            {
                "country": row["dimensionValues"][0]["value"],
                "active_users": _parse_int(row["metricValues"][0]["value"]),
            }
            for row in countries_raw.get("rows", [])
        ]

        # 5. By device
        devices_raw = self._post_realtime(
            {
                "dimensions": [{"name": "deviceCategory"}],
                "metrics": [{"name": "activeUsers"}],
                "limit": 10,
                "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}],
            }
        )
        by_device = [
            {
                "device": row["dimensionValues"][0]["value"],
                "active_users": _parse_int(row["metricValues"][0]["value"]),
            }
            for row in devices_raw.get("rows", [])
        ]

        return {
            "active_users": active_users,
            "by_page": by_page,
            "by_source": by_source,
            "by_country": by_country,
            "by_device": by_device,
        }


# ---------------------------------------------------------------------------
# Internal helper for overview metric casting
# ---------------------------------------------------------------------------


def _cast_overview(raw: dict[str, Any], metrics: list[str]) -> dict[str, Any]:
    """Cast overview metric strings to numeric types."""
    int_metrics = {"sessions", "activeUsers", "newUsers", "screenPageViews"}
    float_metrics = {  # noqa: F841 (documentation of intent)
        "bounceRate",
        "averageSessionDuration",
        "engagementRate",
        "conversions",
    }
    result: dict[str, Any] = {}
    for m in metrics:
        val = raw.get(m, "0")
        if m in int_metrics:
            result[m] = _parse_int(val)
        else:
            result[m] = _parse_float(val)
    return result
