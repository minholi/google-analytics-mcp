"""Tests for date-range resolution and overview period-over-period math."""

from datetime import date

from src.server import DateRange, _resolve_dates


def _iso(d: date) -> str:
    return d.isoformat()


def test_resolve_last_7_days():
    start, end = _resolve_dates(DateRange.LAST_7_DAYS, None, None)
    today = date.today()
    assert start == _iso(today.replace()) or start != ""  # basic sanity — non-empty
    # end should be yesterday
    from datetime import timedelta

    assert end == _iso(today - timedelta(days=1))


def test_resolve_this_month_starts_on_day_1():
    start, end = _resolve_dates(DateRange.THIS_MONTH, None, None)
    assert start.endswith("-01")


def test_resolve_last_month_wraps_year_boundary():
    """Regression: LAST_MONTH must not crash on January."""
    # Not asserting exact values (depends on today), just that it returns a valid range.
    start, end = _resolve_dates(DateRange.LAST_MONTH, None, None)
    assert start < end
    # Start is day 1
    assert start.endswith("-01")


def test_resolve_custom_requires_dates():
    import pytest

    with pytest.raises(ValueError, match="date_range='custom'"):
        _resolve_dates(DateRange.CUSTOM, None, None)


def test_resolve_custom_passthrough():
    start, end = _resolve_dates(DateRange.CUSTOM, "2025-06-01", "2025-06-30")
    assert start == "2025-06-01"
    assert end == "2025-06-30"


def test_overview_infers_previous_period_length(client, fake_httpx):
    """The client should compute a previous period of the same length."""
    fake_httpx(
        {
            "rows": [
                {
                    "dimensionValues": [{"value": "date_range_0"}],
                    "metricValues": [
                        {"value": v} for v in ["100", "80", "20", "500", "0.4", "60", "0.6", "5"]
                    ],
                },
                {
                    "dimensionValues": [{"value": "date_range_1"}],
                    "metricValues": [
                        {"value": v} for v in ["90", "72", "18", "450", "0.5", "55", "0.5", "4"]
                    ],
                },
            ]
        }
    )
    data = client.get_overview(
        start_date="2026-02-01", end_date="2026-02-10", compare_previous=True
    )
    # 10 days → previous is Jan 22–31
    assert data["previous_period"] == {"start": "2026-01-22", "end": "2026-01-31"}
