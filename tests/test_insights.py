"""Tests for the /api/insights endpoint: shape, thresholds, and agreement with raw SQL."""


def test_insights_shape(client):
    r = client.get("/api/insights")
    assert r.status_code == 200
    d = r.get_json()
    for k in ("hotspots", "technicians", "seasonality", "plans", "company_callback_rate", "thresholds"):
        assert k in d
    assert 0 < d["company_callback_rate"] < 0.3


def test_company_rate_matches_raw_sql(client, db):
    raw = db.execute("""SELECT 1.0*SUM(CASE WHEN is_completed=1 THEN is_callback END)/SUM(is_completed)
                        FROM fact_service_visit""").fetchone()[0]
    assert abs(client.get("/api/insights").get_json()["company_callback_rate"] - raw) < 1e-9


def test_hotspots_respect_minimum_visits_and_sort(client):
    d = client.get("/api/insights").get_json()
    mins = d["thresholds"]["hotspot_min_visits"]
    assert all(h["completed_visits"] >= mins for h in d["hotspots"])
    ratios = [h["vs_company"] for h in d["hotspots"]]
    assert ratios == sorted(ratios, reverse=True)


def test_technicians_respect_minimum_visits(client):
    d = client.get("/api/insights").get_json()
    assert all(t["completed_visits"] >= d["thresholds"]["tech_min_visits"] for t in d["technicians"])


def test_seasonality_index_averages_to_one_per_service(client):
    d = client.get("/api/insights").get_json()
    by = {}
    for r in d["seasonality"]:
        by.setdefault(r["service"], []).append(r["index_vs_avg"])
    for s, vals in by.items():
        assert abs(sum(vals) / len(vals) - 1.0) < 1e-9, s


def test_plan_visits_add_up_to_completed(client, db):
    d = client.get("/api/insights").get_json()
    total = db.execute("SELECT SUM(is_completed) FROM fact_service_visit").fetchone()[0]
    assert sum(p["completed_visits"] for p in d["plans"]) == total


def test_pages_render(client):
    assert client.get("/insights").status_code == 200
    assert b"Insights" in client.get("/").data
