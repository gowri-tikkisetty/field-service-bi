import pytest

ENDPOINTS = ["/api/filters", "/api/kpis", "/api/trend", "/api/branches", "/api/service-mix",
             "/api/heatmap", "/api/technicians", "/api/metrics", "/", "/metrics"]


@pytest.mark.parametrize("url", ENDPOINTS)
def test_endpoints_ok(client, url):
    assert client.get(url).status_code == 200


def test_bad_input_returns_400_not_500(client):
    assert client.get("/api/trend?metric=drop_table").status_code == 400
    assert client.get("/api/kpis?start=2026-05-01&end=2026-01-01").status_code == 400
    assert client.get("/api/kpis?start=not-a-date").status_code == 400
    assert client.get("/api/technicians?order=sideways").status_code == 400


def test_kpis_match_raw_fact_table(client, db):
    """Validate the dashboard against the raw fact table (the 'validate new reports' habit)."""
    js = client.get("/api/kpis?start=2026-05-01&end=2026-10-31").json
    k = {x["id"]: x["value"] for x in js["kpis"]}
    r = db.execute("""SELECT SUM(f.revenue), SUM(f.is_completed),
                             1.0*SUM(CASE WHEN f.is_completed=1 THEN f.is_callback ELSE 0 END)/SUM(f.is_completed),
                             1.0*SUM(f.csat)/COUNT(f.csat)
                      FROM fact_service_visit f WHERE f.date_key BETWEEN 20260501 AND 20261031""").fetchone()
    assert k["revenue"] == pytest.approx(r[0], abs=0.01)
    assert k["completed_visits"] == r[1]
    assert k["callback_rate"] == pytest.approx(r[2])
    assert k["avg_csat"] == pytest.approx(r[3])


def test_branch_totals_add_up_to_overall(client):
    total = {x["id"]: x["value"] for x in client.get("/api/kpis").json["kpis"]}["revenue"]
    branches = client.get("/api/branches").json["branches"]
    assert sum(b["revenue"] for b in branches) == pytest.approx(total, abs=0.05)
    assert sum(b["revenue_share"] for b in branches) == pytest.approx(1.0)


def test_filter_changes_the_numbers(client):
    all_rev = {x["id"]: x["value"] for x in client.get("/api/kpis").json["kpis"]}["revenue"]
    one_rev = {x["id"]: x["value"] for x in client.get("/api/kpis?branch=1").json["kpis"]}["revenue"]
    assert 0 < one_rev < all_rev


def test_year_over_year_only_when_prior_data_exists(client):
    js = client.get("/api/kpis?start=2025-02-01&end=2025-06-30").json   # prior year is before the data starts
    assert js["prior_period"]["available"] is False
    assert all(k["delta"] is None for k in js["kpis"])


def test_rates_are_between_zero_and_one(client):
    for c in client.get("/api/heatmap").json["cells"]:
        assert c["callback_rate"] is None or 0 <= c["callback_rate"] <= 1


def test_every_metric_has_a_definition(client):
    metrics = client.get("/api/metrics").json
    for m in metrics.values():
        assert m["definition"] and m["formula"]
    for k in client.get("/api/kpis").json["kpis"]:
        assert k["id"] in metrics
