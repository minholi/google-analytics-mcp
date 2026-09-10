"""Tests for the markdown formatters."""

from src import formatters as f

# ---------- helpers ----------


def test_fmt_pct():
    assert f._fmt_pct(0) == "0.00%"
    assert f._fmt_pct(0.1234) == "12.34%"
    assert f._fmt_pct(0.5, decimals=0) == "50%"


def test_fmt_delta_none_and_signs():
    assert f._fmt_delta(None) == "—"
    assert "▲" in f._fmt_delta(12.3)
    assert "▼" in f._fmt_delta(-4.5)
    assert "4.5" in f._fmt_delta(-4.5)


def test_engagement_emoji_thresholds():
    assert f._engagement_emoji(0.7) == "🟢"
    assert f._engagement_emoji(0.5) == "🟡"
    assert f._engagement_emoji(0.2) == "🔴"


def test_bounce_emoji_thresholds():
    assert f._bounce_emoji(0.3) == "🟢"
    assert f._bounce_emoji(0.5) == "🟡"
    assert f._bounce_emoji(0.8) == "🔴"


def test_pct_delta_zero_previous():
    assert f._pct_delta(10, 0) is None
    assert f._pct_delta(150, 100) == 50.0


def test_fmt_duration():
    assert f._fmt_duration(0) == "0m 00s"
    assert f._fmt_duration(65) == "1m 05s"
    assert f._fmt_duration(3600) == "60m 00s"


# ---------- format_overview ----------


def test_format_overview_english_labels_no_comparison():
    data = {
        "current": {
            "sessions": 100,
            "activeUsers": 80,
            "newUsers": 20,
            "screenPageViews": 500,
            "bounceRate": 0.4,
            "averageSessionDuration": 60.0,
            "engagementRate": 0.6,
            "conversions": 5.0,
        },
        "previous": None,
        "period": {"start": "2026-01-01", "end": "2026-01-07"},
    }
    out = f.format_overview(data, "2026-01-01", "2026-01-07")

    assert "Google Analytics Overview" in out
    assert "Sessions" in out
    assert "Active Users" in out
    assert "Bounce Rate" in out
    assert "Engagement" in out
    assert "vs Previous" not in out  # no comparison column


def test_format_overview_with_comparison_shows_delta_column():
    data = {
        "current": {
            "sessions": 110,
            "activeUsers": 88,
            "newUsers": 22,
            "screenPageViews": 550,
            "bounceRate": 0.35,
            "averageSessionDuration": 65.0,
            "engagementRate": 0.65,
            "conversions": 6.0,
        },
        "previous": {
            "sessions": 100,
            "activeUsers": 80,
            "newUsers": 20,
            "screenPageViews": 500,
            "bounceRate": 0.4,
            "averageSessionDuration": 60.0,
            "engagementRate": 0.6,
            "conversions": 5.0,
        },
        "previous_period": {"start": "2025-12-25", "end": "2025-12-31"},
        "period": {"start": "2026-01-01", "end": "2026-01-07"},
    }
    out = f.format_overview(data, "2026-01-01", "2026-01-07")

    assert "vs Previous" in out
    assert "▲" in out  # at least one metric improved


def test_format_overview_empty_period():
    out = f.format_overview({"current": {}}, "2026-01-01", "2026-01-07")
    assert "No data" in out


# ---------- format_traffic_sources ----------


def test_format_traffic_sources_channel_labels():
    data = {
        "rows": [
            {
                "label": "Organic Search",
                "sessions": 500,
                "active_users": 400,
                "new_users": 100,
                "bounce_rate": 0.35,
                "engagement_rate": 0.65,
                "conversions": 10.0,
            }
        ],
        "group_by": "channel",
        "count": 1,
        "period": {"start": "2026-01-01", "end": "2026-01-07"},
    }
    out = f.format_traffic_sources(data, "2026-01-01", "2026-01-07")
    assert "Traffic Sources" in out
    assert "Channel" in out
    assert "Organic Search" in out


def test_format_traffic_sources_source_medium_column_label():
    data = {"rows": [], "group_by": "source_medium", "count": 0, "period": {}}
    out = f.format_traffic_sources(data, "2026-01-01", "2026-01-07")
    assert "Source / Medium" in out


# ---------- format_top_pages ----------


def test_format_top_pages_shows_filter():
    data = {
        "pages": [
            {
                "path": "/blog/x",
                "title": "X",
                "pageviews": 100,
                "sessions": 80,
                "active_users": 60,
                "avg_session_duration": 45.0,
                "bounce_rate": 0.3,
                "engagement_rate": 0.7,
            }
        ],
        "count": 1,
        "filter": "/blog",
        "period": {},
    }
    out = f.format_top_pages(data, "2026-01-01", "2026-01-07")
    assert "Top Pages" in out
    assert "`/blog*`" in out
    assert "Pageviews" in out


# ---------- format_geographic_performance ----------


def test_format_geographic_highlights():
    data = {
        "locations": [
            {
                "name": "United States",
                "sessions": 1000,
                "active_users": 800,
                "new_users": 300,
                "conversions": 5.0,
                "bounce_rate": 0.35,
            },
            {
                "name": "Brazil",
                "sessions": 500,
                "active_users": 400,
                "new_users": 150,
                "conversions": 0.0,
                "bounce_rate": 0.55,
            },
        ],
        "granularity": "country",
        "count": 2,
        "period": {},
    }
    out = f.format_geographic_performance(data, "2026-01-01", "2026-01-30")
    assert "Geographic Performance" in out
    assert "Most conversions" in out
    assert "Most sessions without conversions" in out
    assert "Brazil" in out


# ---------- format_audience ----------


def test_format_audience_device_labels():
    data = {
        "rows": [
            {
                "name": "mobile",
                "sessions": 800,
                "active_users": 600,
                "pageviews": 2400,
                "bounce_rate": 0.45,
                "engagement_rate": 0.55,
            }
        ],
        "breakdown": "deviceCategory",
        "count": 1,
        "period": {},
    }
    out = f.format_audience(data, "2026-01-01", "2026-01-07")
    assert "Audience by Device" in out


# ---------- format_events ----------


def test_format_events_empty():
    out = f.format_events({"events": [], "count": 0, "filter": None}, "2026-01-01", "2026-01-07")
    assert "No events" in out


def test_format_events_with_filter_lists_names():
    data = {
        "events": [{"name": "purchase", "count": 50, "count_per_user": 1.2, "total_users": 42}],
        "count": 1,
        "filter": ["purchase"],
        "period": {},
    }
    out = f.format_events(data, "2026-01-01", "2026-01-30")
    assert "filter: `purchase`" in out
    assert "purchase" in out


# ---------- format_conversions ----------


def test_format_conversions_totals_and_no_currency_symbol():
    data = {
        "conversions": [
            {
                "channel": "Paid Search",
                "event_name": "purchase",
                "conversions": 10.0,
                "revenue": 1500.50,
                "sessions": 200,
            }
        ],
        "totals": {"conversions": 10.0, "revenue": 1500.50},
        "count": 1,
        "period": {},
    }
    out = f.format_conversions(data, "2026-01-01", "2026-01-30")
    assert "Conversions" in out
    assert "Total revenue" in out
    # Currency symbol is intentionally omitted; a hint is included instead
    assert "property's currency" in out
    assert "1,500.50" in out


# ---------- format_realtime ----------


def test_format_realtime_labels():
    data = {
        "active_users": 42,
        "by_page": [{"page": "/home", "active_users": 20}],
        "by_source": [{"source": "google", "active_users": 15}],
        "by_country": [{"country": "United States", "active_users": 30}],
        "by_device": [{"device": "mobile", "active_users": 25}],
    }
    out = f.format_realtime(data)
    assert "Realtime Data" in out
    assert "Active users right now: 42" in out
    assert "By Page" in out
    assert "By Source" in out
    assert "By Country" in out
    assert "By Device" in out
