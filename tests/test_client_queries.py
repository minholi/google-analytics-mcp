"""Tests that verify the request bodies sent to the GA4 Data API."""


def _row(dim_values: list[str], met_values: list[str]) -> dict:
    return {
        "dimensionValues": [{"value": v} for v in dim_values],
        "metricValues": [{"value": v} for v in met_values],
    }


def test_get_overview_single_period(client, fake_httpx):
    fake_httpx({"rows": [_row([], ["100", "80", "20", "500", "0.4", "60.0", "0.6", "5.0"])]})
    data = client.get_overview(start_date="2026-01-01", end_date="2026-01-07")

    # The client parsed the response correctly
    assert data["current"]["sessions"] == 100
    assert data["current"]["activeUsers"] == 80
    assert data["previous"] is None
    assert data["period"] == {"start": "2026-01-01", "end": "2026-01-07"}


def test_get_overview_with_comparison(client, fake_httpx):
    captor = fake_httpx(
        {
            "rows": [
                _row(["date_range_0"], ["100", "80", "20", "500", "0.4", "60.0", "0.6", "5.0"]),
                _row(["date_range_1"], ["90", "72", "18", "450", "0.5", "55.0", "0.5", "4.0"]),
            ]
        }
    )
    data = client.get_overview(
        start_date="2026-01-08", end_date="2026-01-14", compare_previous=True
    )

    # Request body has two date ranges and the implicit dateRange dimension
    assert len(captor.last_json["dateRanges"]) == 2
    assert captor.last_json["dimensions"] == [{"name": "dateRange"}]

    # The comparison period is inferred as the 7 days before start_date
    assert data["previous_period"] == {"start": "2026-01-01", "end": "2026-01-07"}
    assert data["current"]["sessions"] == 100
    assert data["previous"]["sessions"] == 90


def test_get_traffic_sources_channel(client, fake_httpx):
    captor = fake_httpx(
        {
            "rows": [
                _row(["Organic Search"], ["500", "400", "100", "0.35", "0.65", "10.0"]),
                _row(["Direct"], ["300", "250", "50", "0.45", "0.55", "5.0"]),
            ]
        }
    )
    data = client.get_traffic_sources(
        start_date="2026-01-01", end_date="2026-01-07", group_by="channel", limit=10
    )

    assert captor.last_json["dimensions"] == [{"name": "sessionDefaultChannelGroup"}]
    assert captor.last_json["limit"] == 10
    assert data["count"] == 2
    assert data["rows"][0]["label"] == "Organic Search"
    assert data["rows"][0]["sessions"] == 500


def test_get_traffic_sources_source_medium(client, fake_httpx):
    captor = fake_httpx(
        {"rows": [_row(["google", "organic"], ["500", "400", "100", "0.35", "0.65", "10.0"])]}
    )
    data = client.get_traffic_sources(
        start_date="2026-01-01", end_date="2026-01-07", group_by="source_medium"
    )

    assert captor.last_json["dimensions"] == [
        {"name": "sessionSource"},
        {"name": "sessionMedium"},
    ]
    assert data["rows"][0]["label"] == "google / organic"


def test_get_top_pages_with_filter(client, fake_httpx):
    captor = fake_httpx(
        {
            "rows": [
                _row(
                    ["/blog/post-1", "First post"],
                    ["1000", "800", "600", "45.0", "0.3", "0.7"],
                )
            ]
        }
    )
    data = client.get_top_pages(
        start_date="2026-01-01",
        end_date="2026-01-07",
        limit=10,
        page_path_filter="/blog",
    )

    assert captor.last_json["dimensionFilter"]["filter"]["stringFilter"]["value"] == "/blog"
    assert captor.last_json["dimensionFilter"]["filter"]["stringFilter"]["matchType"] == (
        "BEGINS_WITH"
    )
    assert data["pages"][0]["path"] == "/blog/post-1"
    assert data["pages"][0]["pageviews"] == 1000


def test_get_geographic_performance_country(client, fake_httpx):
    captor = fake_httpx(
        {
            "rows": [
                _row(["United States"], ["1000", "800", "300", "5.0", "0.35"]),
                _row(["Brazil"], ["500", "400", "150", "2.0", "0.40"]),
            ]
        }
    )
    data = client.get_geographic_performance(
        start_date="2026-01-01", end_date="2026-01-30", granularity="country"
    )

    assert captor.last_json["dimensions"] == [{"name": "country"}]
    assert data["granularity"] == "country"
    assert data["locations"][0]["name"] == "United States"
    assert data["locations"][0]["conversions"] == 5.0


def test_get_audience_device(client, fake_httpx):
    fake_httpx(
        {
            "rows": [
                _row(["mobile"], ["800", "600", "2400", "0.45", "0.55"]),
                _row(["desktop"], ["400", "350", "1800", "0.30", "0.70"]),
            ]
        }
    )
    data = client.get_audience(
        start_date="2026-01-01", end_date="2026-01-07", breakdown="deviceCategory"
    )

    assert data["breakdown"] == "deviceCategory"
    assert data["rows"][0]["name"] == "mobile"


def test_get_events_with_filter(client, fake_httpx):
    captor = fake_httpx(
        {
            "rows": [
                _row(["purchase"], ["50", "1.2", "42"]),
                _row(["sign_up"], ["30", "1.0", "30"]),
            ]
        }
    )
    data = client.get_events(
        start_date="2026-01-01",
        end_date="2026-01-30",
        event_names=["purchase", "sign_up"],
    )

    assert captor.last_json["dimensionFilter"]["filter"]["inListFilter"]["values"] == [
        "purchase",
        "sign_up",
    ]
    assert data["events"][0]["name"] == "purchase"
    assert data["events"][0]["count"] == 50


def test_get_conversions_filters_zero(client, fake_httpx):
    captor = fake_httpx({"rows": [_row(["Paid Search", "purchase"], ["10.0", "1500.50", "200"])]})
    data = client.get_conversions(start_date="2026-01-01", end_date="2026-01-30")

    # Confirm the metricFilter drops rows with zero conversions
    assert captor.last_json["metricFilter"]["filter"]["fieldName"] == "conversions"
    assert data["totals"]["conversions"] == 10.0
    assert data["totals"]["revenue"] == 1500.50


def test_client_normalizes_property_prefix():
    from src.auth import GoogleAnalyticsAuth
    from src.client import GoogleAnalyticsClient

    auth = GoogleAnalyticsAuth.for_access_token(access_token="tok")
    c = GoogleAnalyticsClient(auth=auth, property_id="properties/999888")
    assert c.property_id == "999888"
    assert c._property_resource == "properties/999888"
