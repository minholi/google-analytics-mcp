# Google Analytics MCP — Usage Guide

A practical guide for analysts and marketers using this MCP server through an AI agent (Claude Desktop, Cursor, etc.).

## Table of contents

1. [Overview](#overview)
2. [Cross-cutting concepts](#cross-cutting-concepts)
3. [Analysis scenarios](#analysis-scenarios)
4. [Ready-to-use prompt library](#ready-to-use-prompt-library)
5. [Full tool reference](#full-tool-reference)
6. [Appendix](#appendix)

---

## Overview

**Audience.** Web/product analysts, growth marketers, and content owners who want to interrogate GA4 through natural language instead of clicking around the Google Analytics UI.

**Scope.** The server exposes 8 read-only tools that map to the most common GA4 Data API reports. Everything is real-time from the API — no caching, no aggregation layer of our own.

**What it is *not*.** It does not modify GA4 configuration, does not create audiences or conversion events, does not touch Google Ads, and does not export historical data in bulk. Read-only, report-focused.

---

## Cross-cutting concepts

- **`property_id`** — Numeric GA4 property ID (e.g. `123456789`), no `properties/` prefix. Every tool accepts it; if omitted, falls back to `GOOGLE_ANALYTICS_PROPERTY_ID` in the environment.
- **`date_range`** — One of `last_7_days`, `last_14_days`, `last_30_days`, `this_month`, `last_month`, or `custom` (requires `start_date` and `end_date` in `YYYY-MM-DD`). Ranges use the property's timezone as configured in GA4.
- **`response_format`** — `markdown` (default, human-readable table) or `json` (structured, good for pipelines).
- **Severity emojis.** Bounce rate: 🟢 ≤40%, 🟡 ≤60%, 🔴 >60%. Engagement rate: 🟢 ≥60%, 🟡 ≥40%, 🔴 <40%.
- **Realtime is different.** `get_realtime` never accepts a date range — it always reports the last 30 minutes.
- **Conversions.** Only events flagged as conversions in your GA4 property show up in `get_conversions`. If your list is empty, mark the events in GA4 first.

---

## Analysis scenarios

Each scenario shows the business question, the tool flow, a copy-pasteable prompt, and what to do with the output.

### 1. Weekly performance pulse

**Question.** "How did we do this week vs last week?"

**Flow.** `get_overview` with `date_range=last_7_days`, `compare_previous=true`.

**Prompt.**
> Give me the last 7 days overview compared to the previous 7 days.

**Reading the output.** Sessions/users deltas tell you the volume trend; bounce and engagement deltas tell you the quality trend. Both moving in the same direction is unusual — divergence is the interesting signal.

### 2. Traffic drop diagnosis

**Question.** "Sessions are down — where?"

**Flow.**
1. `get_overview` with `compare_previous=true` — confirm and quantify the drop.
2. `get_traffic_sources` with `group_by=channel` for the same period — find which channels lost.
3. Drill into the worst channel with `group_by=source_medium` or `group_by=campaign`.

**Prompt.**
> Sessions dropped last week. Show me the overview compared to the previous week, then break it down by channel, and drill into whichever channel lost the most sessions by source/medium.

### 3. Top-page performance & content audit

**Question.** "Which pages are working, and which need attention?"

**Flow.** `get_top_pages` with a `limit` of 25 and — for a section audit — `page_path_filter` like `/blog` or `/products`.

**Prompt.**
> Show me the top 25 blog pages in the last 30 days. Highlight anything with bounce rate above 70% or session duration under 30 seconds.

**Reading the output.** High pageviews + high bounce = the page ranks/attracts but doesn't hold. Low pageviews + low bounce = niche but valuable — worth promoting internally.

### 4. Geographic performance

**Question.** "Where are our users, and where do they convert?"

**Flow.** `get_geographic_performance` with `granularity=country` for a wide view; switch to `region` or `city` for local businesses. The tool automatically highlights the top-converting location and the location with the most no-conversion sessions.

**Prompt.**
> Break down the last 30 days by country. Which country has the most sessions with zero conversions?

### 5. Audience by device / browser

**Question.** "Is mobile hurting us?"

**Flow.** `get_audience` with `breakdown=deviceCategory` first; if desktop/mobile diverge on bounce, follow up with `browser` and `operatingSystem` to isolate.

**Prompt.**
> Compare bounce and engagement between mobile and desktop over the last 14 days. If mobile is meaningfully worse, break it down by operating system.

### 6. Event optimization

**Question.** "Which micro-conversions are firing?"

**Flow.** `get_events` without a filter for a wide sweep; then with `event_names=["scroll_75", "video_start", ...]` to track a curated set week over week.

**Prompt.**
> Show me the top 20 events in the last 30 days by count.

### 7. Conversion & revenue attribution

**Question.** "What's driving conversions and revenue?"

**Flow.** `get_conversions` — grouped by channel and event automatically. Only conversion-flagged events appear.

**Prompt.**
> List conversions and revenue for the last 30 days grouped by channel. Which channel drives the most revenue per session?

**Reading the output.** Look at revenue per session (revenue ÷ sessions) instead of raw revenue — the biggest channel by volume isn't always the most efficient.

### 8. Live monitoring during a campaign launch

**Question.** "Is the campaign live and pulling traffic?"

**Flow.** `get_realtime` — total active users plus breakdowns by page, source, country, device.

**Prompt.**
> How many users are on the site right now, and which pages are they on?

---

## Ready-to-use prompt library

### Overview & trends
- "Show me the last 7 days overview compared to the previous 7 days."
- "How did sessions and conversions change month over month?"
- "Give me a KPI summary for last month vs the month before."

### Traffic sources
- "Break down last 30 days traffic by channel."
- "Which source/medium is bringing the most engaged users this week?"
- "Show me the top 10 campaigns by sessions in the last 14 days."

### Pages & content
- "Top 25 pages by pageviews in the last 30 days."
- "Which `/blog` pages have the worst bounce rate this month?"
- "Compare average session duration for `/products` vs `/blog` in the last 14 days."

### Geography
- "Show performance by country for the last 30 days."
- "Break down last month by state within the US."
- "Which city has the most no-conversion sessions?"

### Audience
- "Compare mobile vs desktop over the last 14 days."
- "Which browser has the worst engagement rate?"
- "Break down last month by operating system."

### Events
- "Top 20 events by count in the last 30 days."
- "Track `sign_up`, `add_to_cart`, and `purchase` events this month."

### Conversions
- "Show conversions and revenue by channel for the last 30 days."
- "Which event is driving the most revenue this month?"

### Realtime
- "How many users are on the site right now?"
- "Which pages have live users at this moment?"

---

## Full tool reference

Each tool returns a markdown table (default) or a JSON dict (`response_format="json"`). Every tool accepts an optional `property_id` — omit it to use the server's default from `GOOGLE_ANALYTICS_PROPERTY_ID`.

### `google_analytics_get_overview`

**Purpose.** Property-wide KPIs for a date range, optionally with period-over-period comparison.

**Parameters.**
- `property_id?`, `date_range` (default `last_7_days`), `start_date?`, `end_date?` (required if `date_range=custom`)
- `compare_previous` (default `false`) — when `true`, adds a same-length previous period and per-metric deltas
- `response_format` — `markdown` (default) or `json`

**Returns.** Sessions, active users, new users, pageviews, bounce rate, average session duration, engagement rate, conversions. With `compare_previous=true`, each metric has a `▲/▼ x.y%` delta.

**Sample prompt.** *"Give me the last 30 days overview compared to the previous 30 days."*

### `google_analytics_get_traffic_sources`

**Purpose.** Acquisition grouped by channel, source/medium, or campaign.

**Parameters.**
- Standard date range + `property_id`
- `group_by` — `channel` (default), `source_medium`, or `campaign`
- `limit` — 1–100, default 25
- `response_format`

**Returns.** For each source: sessions, active users, new users, bounce rate, engagement rate, conversions.

**Caveat.** GA4's `sessionDefaultChannelGroup` is Google's opinion; if your team relies on custom channel groupings, use `source_medium` for less lossy attribution.

### `google_analytics_get_top_pages`

**Purpose.** Most-visited pages.

**Parameters.**
- Standard date range + `property_id`
- `limit` — 1–100, default 25
- `page_path_filter` — optional prefix filter (e.g. `/blog`, `/products/`)
- `response_format`

**Returns.** Path, title, pageviews, sessions, active users, average session duration, bounce rate, engagement rate.

**Caveat.** `pagePath` in GA4 excludes the host and query string. Two URLs with different query params are folded together.

### `google_analytics_get_geographic_performance`

**Purpose.** Sessions/conversions by location.

**Parameters.**
- Standard date range + `property_id` (defaults to `last_30_days`)
- `granularity` — `country` (default), `region`, or `city`
- `limit` — 1–100, default 25
- `response_format`

**Returns.** Rows with location, sessions, active users, new users, conversions, bounce rate. Two highlight lines below the table: top converter, and worst no-conversion location.

### `google_analytics_get_audience`

**Purpose.** Audience breakdown by device, browser, or OS.

**Parameters.**
- Standard date range + `property_id`
- `breakdown` — `deviceCategory` (default), `browser`, or `operatingSystem`
- `limit` — 1–100, default 25
- `response_format`

**Returns.** For each segment: sessions, active users, pageviews, bounce rate, engagement rate.

### `google_analytics_get_events`

**Purpose.** Event popularity.

**Parameters.**
- Standard date range + `property_id`
- `event_names?` — optional list to filter to specific event names
- `limit` — 1–200, default 50
- `response_format`

**Returns.** Event name, total count, count per user, total users.

**Caveat.** GA4 fires many auto-events (`session_start`, `first_visit`, `user_engagement`) that may dominate the list. Use `event_names` to focus.

### `google_analytics_get_conversions`

**Purpose.** Conversion events with revenue, grouped by channel + event.

**Parameters.**
- Standard date range + `property_id` (defaults to `last_30_days`)
- `limit` — 1–200, default 50
- `response_format`

**Returns.** Per (channel, event): conversions, revenue, sessions. Plus overall totals for conversions and revenue.

**Caveat.** Only events flagged as conversions in GA4 appear. If empty, mark the events in **Admin → Events → Mark as key event**. Revenue is reported in the property's configured currency — no symbol is prepended.

### `google_analytics_get_realtime`

**Purpose.** Active users right now (last 30 minutes).

**Parameters.**
- `property_id?`
- `response_format`

**Returns.** Total active users plus top 10 by page, source, country, and device.

**Caveat.** No date range. Realtime metrics have their own sampling and can differ slightly from the standard report totals.

---

## Appendix

### Glossary

- **Active users.** GA4's headline user metric — distinct users with any engagement in the range.
- **New users.** First-time users in the range.
- **Session.** A group of user interactions within a 30-min inactivity window (configurable in GA4).
- **Engagement rate.** Fraction of sessions that qualify as "engaged" (≥10s, ≥2 pageviews, or a conversion).
- **Bounce rate.** `1 - engagement_rate`. Not the classic UA definition.
- **Conversion.** An event marked as a conversion in GA4 admin (also known as "key event" in newer GA4 UI).

### Known limitations

- Read-only. No write endpoints against the Data API in this server.
- No custom-report builder. If you need dimensions/metrics we don't expose, run a report in GA4 or extend `src/client.py`.
- Historical data older than 14 months may be unavailable in standard GA4 properties.
- API quotas apply. GA4 Data API caps concurrent requests per property; rate limit hits return a friendly `❌ Rate limit reached` message.
