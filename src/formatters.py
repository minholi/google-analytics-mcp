"""
Markdown output formatters for the Google Analytics MCP tools.
All presentation logic lives here — separated from the API client.
"""

from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fmt_pct(value: float, decimals: int = 2) -> str:
    """GA4 returns rates as 0.0–1.0; convert to percentage."""
    return f"{value * 100:.{decimals}f}%"


def _fmt_duration(seconds: float) -> str:
    """Convert seconds to a mm:ss string."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _fmt_number(value: float, decimals: int = 2) -> str:
    """Format a number with thousands separators and fixed decimals."""
    return f"{value:,.{decimals}f}"


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "—"
    arrow = "▲" if value >= 0 else "▼"
    return f"{arrow} {abs(value):.1f}%"


def _pct_delta(current: float, previous: float) -> float | None:
    """Percentage change between two values."""
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def _engagement_emoji(rate: float) -> str:
    """🟢 ≥60%, 🟡 ≥40%, 🔴 <40%"""
    pct = rate * 100
    if pct >= 60:
        return "🟢"
    if pct >= 40:
        return "🟡"
    return "🔴"


def _bounce_emoji(rate: float) -> str:
    """🟢 ≤40%, 🟡 ≤60%, 🔴 >60%"""
    pct = rate * 100
    if pct <= 40:
        return "🟢"
    if pct <= 60:
        return "🟡"
    return "🔴"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def format_overview(data: dict[str, Any], start: str, end: str) -> str:
    curr = data.get("current", {})
    prev = data.get("previous")
    prev_period = data.get("previous_period", {})

    lines = [f"## 📊 Google Analytics Overview — {start} to {end}", ""]

    if not curr:
        lines.append("_No data for the requested period._")
        return "\n".join(lines)

    if prev:
        comp_label = f"{prev_period.get('start')} to {prev_period.get('end')}"
        lines += [
            f"### Main KPIs _(vs {comp_label})_",
            "",
            "| Metric | Current | vs Previous |",
            "|--------|---------|-------------|",
        ]
        kpi_rows = [
            (
                "Sessions",
                f"{curr.get('sessions', 0):,}",
                _fmt_delta(_pct_delta(curr.get("sessions", 0), prev.get("sessions", 0))),
            ),
            (
                "Active Users",
                f"{curr.get('activeUsers', 0):,}",
                _fmt_delta(_pct_delta(curr.get("activeUsers", 0), prev.get("activeUsers", 0))),
            ),
            (
                "New Users",
                f"{curr.get('newUsers', 0):,}",
                _fmt_delta(_pct_delta(curr.get("newUsers", 0), prev.get("newUsers", 0))),
            ),
            (
                "Pageviews",
                f"{curr.get('screenPageViews', 0):,}",
                _fmt_delta(
                    _pct_delta(curr.get("screenPageViews", 0), prev.get("screenPageViews", 0))
                ),
            ),
            (
                "Bounce Rate",
                f"{_bounce_emoji(curr.get('bounceRate', 0))} {_fmt_pct(curr.get('bounceRate', 0))}",
                _fmt_delta(_pct_delta(curr.get("bounceRate", 0), prev.get("bounceRate", 0))),
            ),
            (
                "Avg. Duration",
                _fmt_duration(curr.get("averageSessionDuration", 0)),
                _fmt_delta(
                    _pct_delta(
                        curr.get("averageSessionDuration", 0),
                        prev.get("averageSessionDuration", 0),
                    )
                ),
            ),
            (
                "Engagement",
                f"{_engagement_emoji(curr.get('engagementRate', 0))} "
                f"{_fmt_pct(curr.get('engagementRate', 0))}",
                _fmt_delta(
                    _pct_delta(curr.get("engagementRate", 0), prev.get("engagementRate", 0))
                ),
            ),
            (
                "Conversions",
                f"{curr.get('conversions', 0):.1f}",
                _fmt_delta(_pct_delta(curr.get("conversions", 0), prev.get("conversions", 0))),
            ),
        ]
        for label, val, delta in kpi_rows:
            lines.append(f"| {label} | {val} | {delta} |")
    else:
        lines += [
            "### Main KPIs",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Sessions | {curr.get('sessions', 0):,} |",
            f"| Active Users | {curr.get('activeUsers', 0):,} |",
            f"| New Users | {curr.get('newUsers', 0):,} |",
            f"| Pageviews | {curr.get('screenPageViews', 0):,} |",
            f"| Bounce Rate | {_bounce_emoji(curr.get('bounceRate', 0))} "
            f"{_fmt_pct(curr.get('bounceRate', 0))} |",
            f"| Avg. Duration | {_fmt_duration(curr.get('averageSessionDuration', 0))} |",
            f"| Engagement | {_engagement_emoji(curr.get('engagementRate', 0))} "
            f"{_fmt_pct(curr.get('engagementRate', 0))} |",
            f"| Conversions | {curr.get('conversions', 0):.1f} |",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Traffic Sources
# ---------------------------------------------------------------------------


def format_traffic_sources(data: dict[str, Any], start: str, end: str) -> str:
    rows = data.get("rows", [])
    group_by = data.get("group_by", "channel")
    count = data.get("count", 0)

    group_labels = {
        "channel": "Channel",
        "source_medium": "Source / Medium",
        "campaign": "Campaign",
    }
    group_label = group_labels.get(group_by, group_by)

    lines = [
        f"## 🔀 Traffic Sources — {start} to {end}",
        f"Grouped by: **{group_label}** | **{count}** entries",
        "",
    ]

    if not rows:
        lines.append("_No data for the requested period._")
        return "\n".join(lines)

    lines += [
        f"| {group_label} | Sessions | Users | New | Bounce | Engag. | Conv. |",
        "|" + "---|" * 7,
    ]

    for row in rows:
        label = row.get("label", "")
        lines.append(
            f"| {label} "
            f"| {row['sessions']:,} "
            f"| {row['active_users']:,} "
            f"| {row['new_users']:,} "
            f"| {_bounce_emoji(row['bounce_rate'])} {_fmt_pct(row['bounce_rate'])} "
            f"| {_engagement_emoji(row['engagement_rate'])} "
            f"{_fmt_pct(row['engagement_rate'])} "
            f"| {row['conversions']:.1f} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top Pages
# ---------------------------------------------------------------------------


def format_top_pages(data: dict[str, Any], start: str, end: str) -> str:
    pages = data.get("pages", [])
    count = data.get("count", 0)
    path_filter = data.get("filter")

    header = f"## 📄 Top Pages — {start} to {end}"
    if path_filter:
        header += f" _(filter: `{path_filter}*`)_"

    lines = [header, f"**{count}** pages found", ""]

    if not pages:
        lines.append("_No pages matched the given filters._")
        return "\n".join(lines)

    lines += [
        "| # | Page | Pageviews | Sessions | Bounce | Duration |",
        "|---|------|-----------|----------|--------|----------|",
    ]

    for i, page in enumerate(pages, 1):
        title = page.get("title") or page.get("path", "")
        path = page.get("path", "")
        display = f"{title}" if title and title != path else path
        lines.append(
            f"| {i} "
            f"| {display} "
            f"| {page['pageviews']:,} "
            f"| {page['sessions']:,} "
            f"| {_bounce_emoji(page['bounce_rate'])} {_fmt_pct(page['bounce_rate'])} "
            f"| {_fmt_duration(page['avg_session_duration'])} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Geographic Performance
# ---------------------------------------------------------------------------


def format_geographic_performance(data: dict[str, Any], start: str, end: str) -> str:
    locations = data.get("locations", [])
    granularity = data.get("granularity", "country")
    count = data.get("count", 0)

    gran_labels = {"country": "Country", "region": "Region", "city": "City"}
    gran_label = gran_labels.get(granularity, granularity)

    lines = [
        f"## 🗺️ Geographic Performance — {start} to {end}",
        f"Granularity: **{gran_label}** | **{count}** locations",
        "",
    ]

    if not locations:
        lines.append("_No locations matched the given filters._")
        return "\n".join(lines)

    lines += [
        f"| {gran_label} | Sessions | Users | New | Conv. | Bounce |",
        "|" + "---|" * 6,
    ]

    for loc in locations:
        lines.append(
            f"| {loc['name']} "
            f"| {loc['sessions']:,} "
            f"| {loc['active_users']:,} "
            f"| {loc['new_users']:,} "
            f"| {loc['conversions']:.1f} "
            f"| {_bounce_emoji(loc['bounce_rate'])} {_fmt_pct(loc['bounce_rate'])} |"
        )

    # Highlights
    with_sessions = [loc for loc in locations if loc["sessions"] > 0]
    if with_sessions:
        best_conv = max(with_sessions, key=lambda x: x["conversions"])
        if best_conv["conversions"] > 0:
            lines += [
                "",
                f"**Most conversions:** {best_conv['name']} — "
                f"{best_conv['conversions']:.1f} conversions "
                f"({best_conv['sessions']:,} sessions)",
            ]

    no_conv = [loc for loc in locations if loc["conversions"] == 0 and loc["sessions"] > 0]
    if no_conv:
        worst = max(no_conv, key=lambda x: x["sessions"])
        lines.append(
            f"**Most sessions without conversions:** {worst['name']} — "
            f"{worst['sessions']:,} sessions with no return"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------


def format_audience(data: dict[str, Any], start: str, end: str) -> str:
    rows = data.get("rows", [])
    breakdown = data.get("breakdown", "deviceCategory")
    count = data.get("count", 0)

    breakdown_labels = {
        "deviceCategory": "Device",
        "browser": "Browser",
        "operatingSystem": "Operating System",
    }
    breakdown_label = breakdown_labels.get(breakdown, breakdown)

    lines = [
        f"## 👥 Audience by {breakdown_label} — {start} to {end}",
        f"**{count}** entries",
        "",
    ]

    if not rows:
        lines.append("_No data for the requested period._")
        return "\n".join(lines)

    lines += [
        f"| {breakdown_label} | Sessions | Users | Pageviews | Bounce | Engag. |",
        "|" + "---|" * 6,
    ]

    for row in rows:
        lines.append(
            f"| {row['name']} "
            f"| {row['sessions']:,} "
            f"| {row['active_users']:,} "
            f"| {row['pageviews']:,} "
            f"| {_bounce_emoji(row['bounce_rate'])} {_fmt_pct(row['bounce_rate'])} "
            f"| {_engagement_emoji(row['engagement_rate'])} "
            f"{_fmt_pct(row['engagement_rate'])} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def format_events(data: dict[str, Any], start: str, end: str) -> str:
    events = data.get("events", [])
    count = data.get("count", 0)
    event_filter = data.get("filter")

    header = f"## ⚡ Events — {start} to {end}"
    if event_filter:
        filter_str = ", ".join(f"`{e}`" for e in event_filter)
        header += f" _(filter: {filter_str})_"

    lines = [header, f"**{count}** events found", ""]

    if not events:
        lines.append("_No events matched the given filters._")
        return "\n".join(lines)

    lines += [
        "| # | Event | Total | Per User | Users |",
        "|---|-------|-------|----------|-------|",
    ]

    for i, event in enumerate(events, 1):
        lines.append(
            f"| {i} "
            f"| {event['name']} "
            f"| {event['count']:,} "
            f"| {event['count_per_user']:.2f} "
            f"| {event['total_users']:,} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def format_conversions(data: dict[str, Any], start: str, end: str) -> str:
    conversions = data.get("conversions", [])
    totals = data.get("totals", {})
    count = data.get("count", 0)

    lines = [
        f"## 🎯 Conversions — {start} to {end}",
        f"**{count}** channel/event combinations found",
        "",
        f"**Total conversions:** {totals.get('conversions', 0):.1f}",
        f"**Total revenue:** {_fmt_number(totals.get('revenue', 0))} (in the property's currency)",
        "",
    ]

    if not conversions:
        lines.append("_No conversions for the requested period._")
        return "\n".join(lines)

    lines += [
        "| Channel | Event | Conversions | Revenue | Sessions |",
        "|---------|-------|-------------|---------|----------|",
    ]

    for row in conversions:
        lines.append(
            f"| {row['channel'] or '(not set)'} "
            f"| {row['event_name']} "
            f"| {row['conversions']:.1f} "
            f"| {_fmt_number(row['revenue'])} "
            f"| {row['sessions']:,} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Realtime
# ---------------------------------------------------------------------------


def format_realtime(data: dict[str, Any]) -> str:
    active_users = data.get("active_users", 0)
    by_page = data.get("by_page", [])
    by_source = data.get("by_source", [])
    by_country = data.get("by_country", [])
    by_device = data.get("by_device", [])

    lines = [
        "## 🔴 Realtime Data",
        "_Updated now_",
        "",
        f"**Active users right now: {active_users}**",
        "",
    ]

    if by_page:
        lines += ["### By Page", "", "| Page | Active Users |", "|------|--------------|"]
        for item in by_page:
            lines.append(f"| {item['page']} | {item['active_users']} |")
        lines.append("")

    if by_source:
        lines += ["### By Source", "", "| Source | Active Users |", "|--------|--------------|"]
        for item in by_source:
            lines.append(f"| {item['source'] or '(direct)'} | {item['active_users']} |")
        lines.append("")

    if by_country:
        lines += [
            "### By Country",
            "",
            "| Country | Active Users |",
            "|---------|--------------|",
        ]
        for item in by_country:
            lines.append(f"| {item['country']} | {item['active_users']} |")
        lines.append("")

    if by_device:
        lines += [
            "### By Device",
            "",
            "| Device | Active Users |",
            "|--------|--------------|",
        ]
        for item in by_device:
            lines.append(f"| {item['device']} | {item['active_users']} |")

    return "\n".join(lines)
