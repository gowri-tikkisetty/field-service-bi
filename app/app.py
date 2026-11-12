"""Flask app: JSON API over the star schema + the dashboard page.

Run:  python -m flask --app app.app run     (from the project root)
Open: http://127.0.0.1:5000
"""
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "field_service.db"

# One place that defines every metric. The /metrics page and the tests read this,
# so the documentation cannot drift from the code.
METRICS = {
    "revenue": {
        "label": "Revenue",
        "definition": "Sum of revenue on completed visits. Cancelled / no-access visits count as $0.",
        "formula": "SUM(revenue)",
        "format": "currency",
        "good": "up",
    },
    "completed_visits": {
        "label": "Completed visits",
        "definition": "Visits where the technician completed the service.",
        "formula": "SUM(is_completed)",
        "format": "number",
        "good": "up",
    },
    "callback_rate": {
        "label": "Callback rate",
        "definition": "Completed visits that needed a re-service, divided by completed visits.",
        "formula": "SUM(callbacks) / SUM(completed_visits)",
        "format": "percent",
        "good": "down",
    },
    "avg_csat": {
        "label": "Avg CSAT",
        "definition": "Average 1-5 survey score. Only about 3 in 10 visits return a survey, so this is "
                      "a sample, not every customer.",
        "formula": "SUM(csat_sum) / SUM(csat_n)",
        "format": "score",
        "good": "up",
    },
    "revenue_per_visit": {
        "label": "Revenue per completed visit",
        "definition": "Revenue divided by completed visits.",
        "formula": "SUM(revenue) / SUM(completed_visits)",
        "format": "currency2",
        "good": "up",
    },
}

# SQL expression for each metric over the pre-aggregated table (alias a).
METRIC_SQL = {
    "revenue": "ROUND(SUM(a.revenue), 2)",
    "completed_visits": "SUM(a.completed_visits)",
    "callback_rate": "1.0 * SUM(a.callbacks) / NULLIF(SUM(a.completed_visits), 0)",
    "avg_csat": "1.0 * SUM(a.csat_sum) / NULLIF(SUM(a.csat_n), 0)",
    "revenue_per_visit": "SUM(a.revenue) / NULLIF(SUM(a.completed_visits), 0)",
}


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path or DB_PATH)
    app.json.sort_keys = False      # keep metric order as defined in METRICS

    def get_db():
        if "db" not in g:
            uri = f"file:{app.config['DB_PATH']}?mode=ro"
            g.db = sqlite3.connect(uri, uri=True)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.before_request
    def start_timer():
        g.t0 = time.perf_counter()

    @app.after_request
    def add_timing(resp):
        # Lets you (and the benchmark script) see server time per request.
        if hasattr(g, "t0"):
            resp.headers["X-Server-Time-ms"] = f"{(time.perf_counter() - g.t0) * 1000:.1f}"
        return resp

    # ------------------------------------------------------------ helpers
    def q(sql, params=()):
        return [dict(r) for r in get_db().execute(sql, params).fetchall()]

    def date_bounds():
        r = get_db().execute("SELECT MIN(full_date), MAX(full_date) FROM dim_date").fetchone()
        return r[0], r[1]

    def parse_filters():
        """Validate query-string filters (never put raw input into SQL)."""
        lo, hi = date_bounds()
        hi_d = datetime.strptime(hi, "%Y-%m-%d").date()
        # default window: last 6 full months (so a year-over-year comparison has data)
        m = hi_d.year * 12 + (hi_d.month - 1) - 5
        start_s = request.args.get("start") or date(m // 12, m % 12 + 1, 1).isoformat()
        end_s = request.args.get("end") or hi
        try:
            start_d = datetime.strptime(start_s, "%Y-%m-%d").date()
            end_d = datetime.strptime(end_s, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("start and end must look like 2026-01-31")
        if start_d > end_d:
            raise ValueError("start must be on or before end")
        branch = request.args.get("branch", "all")
        service = request.args.get("service", "all")
        branch = None if branch == "all" else int(branch)
        service = None if service == "all" else int(service)
        return {"start": start_d, "end": end_d, "branch": branch, "service": service}

    def key(d):
        return int(d.strftime("%Y%m%d"))

    def shift_year(d):
        try:
            return d.replace(year=d.year - 1)
        except ValueError:          # Feb 29 -> Feb 28
            return d.replace(year=d.year - 1, day=28)

    def where(f, start=None, end=None, alias="a"):
        clauses = [f"{alias}.date_key BETWEEN ? AND ?"]
        params = [key(start or f["start"]), key(end or f["end"])]
        if f["branch"]:
            clauses.append(f"{alias}.branch_key = ?")
            params.append(f["branch"])
        if f["service"]:
            clauses.append(f"{alias}.service_key = ?")
            params.append(f["service"])
        return " AND ".join(clauses), params

    @app.errorhandler(ValueError)
    def bad_request(err):
        return jsonify({"error": str(err)}), 400

    # ------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/insights")
    def insights_page():
        return render_template("insights.html")

    @app.get("/metrics")
    def metrics_page():
        return render_template("metrics.html", metrics=METRICS)

    # --------------------------------------------------------------- API
    @app.get("/api/filters")
    def api_filters():
        lo, hi = date_bounds()
        return jsonify({
            "min_date": lo, "max_date": hi,
            "branches": q("SELECT branch_key AS id, branch_name AS name, region FROM dim_branch ORDER BY branch_name"),
            "services": q("SELECT service_key AS id, service_name AS name FROM dim_service ORDER BY service_name"),
        })

    @app.get("/api/metrics")
    def api_metrics():
        return jsonify(METRICS)

    @app.get("/api/kpis")
    def api_kpis():
        f = parse_filters()
        # Compare with the SAME dates one year earlier (year-over-year) so seasonality
        # (mosquito season, termite season) does not distort the change.
        lo, _hi = date_bounds()
        prior_start = shift_year(f["start"])
        prior_end = shift_year(f["end"])
        have_prior = prior_start.isoformat() >= lo
        cols = ", ".join(f"{METRIC_SQL[m]} AS {m}" for m in METRICS)

        def period(s, e):
            w, p = where(f, s, e)
            return q(f"SELECT {cols} FROM agg_daily_branch_service a WHERE {w}", p)[0]

        cur = period(f["start"], f["end"])
        prev = period(prior_start, prior_end) if have_prior else {m: None for m in METRICS}
        out = {"period": {"start": f["start"].isoformat(), "end": f["end"].isoformat()},
               "prior_period": {"start": prior_start.isoformat(), "end": prior_end.isoformat(),
                                "available": have_prior, "basis": "same dates one year earlier"},
               "kpis": []}
        for m, meta in METRICS.items():
            c, p = cur[m], prev[m]
            if c is None:
                delta = None
            elif m in ("callback_rate",):
                delta = None if p is None else round((c - p) * 100, 2)      # percentage points
            else:
                delta = None if not p else round((c - p) / p * 100, 2)      # percent change
            out["kpis"].append({"id": m, "label": meta["label"], "format": meta["format"],
                                "good": meta["good"], "value": c, "prior": p, "delta": delta,
                                "delta_unit": "pts" if m == "callback_rate" else "%"})
        # sparkline: monthly series for each KPI inside the selected filters
        w, p = where(f)
        spark = q(f"""
            SELECT d.month_start AS x, {cols}
            FROM agg_daily_branch_service a JOIN dim_date d ON d.date_key = a.date_key
            WHERE {w} GROUP BY d.month_start ORDER BY d.month_start""", p)
        for k in out["kpis"]:
            k["spark"] = [{"x": r["x"], "y": r[k["id"]]} for r in spark]
        return jsonify(out)

    @app.get("/api/trend")
    def api_trend():
        f = parse_filters()
        metric = request.args.get("metric", "revenue")
        if metric not in METRIC_SQL:
            raise ValueError(f"metric must be one of {', '.join(METRIC_SQL)}")
        grain = request.args.get("grain", "month")
        if grain not in ("month", "week"):
            raise ValueError("grain must be month or week")
        col = "month_start" if grain == "month" else "week_start"
        w, p = where(f)
        # CTE for the aggregate, window function (LAG) for period-over-period change.
        rows = q(f"""
            WITH period AS (
                SELECT d.{col} AS x, {METRIC_SQL[metric]} AS y
                FROM agg_daily_branch_service a
                JOIN dim_date d ON d.date_key = a.date_key
                WHERE {w}
                GROUP BY d.{col}
            )
            SELECT x, y, LAG(y) OVER (ORDER BY x) AS prev_y FROM period ORDER BY x""", p)
        # the first and last bucket can be partial weeks / months - flag them
        for r in rows:
            r["pop_change"] = None if not r["prev_y"] or r["y"] is None else round((r["y"] - r["prev_y"]) / r["prev_y"] * 100, 2)
        if grain == "week" and rows:
            # drop a leading partial week: a rate from 1-2 days is noisy and misleading
            if datetime.strptime(rows[0]["x"], "%Y-%m-%d").date() < f["start"] and len(rows) > 1:
                rows = rows[1:]
                rows[0]["pop_change"] = None
            first_start = f["start"]
            if datetime.strptime(rows[0]["x"], "%Y-%m-%d").date() < first_start:
                rows[0]["partial"] = True
            if (datetime.strptime(rows[-1]["x"], "%Y-%m-%d").date() + timedelta(days=6)) > f["end"]:
                rows[-1]["partial"] = True
        return jsonify({"metric": metric, "grain": grain, "series": rows})

    @app.get("/api/branches")
    def api_branches():
        f = parse_filters()
        w, p = where(f)
        rows = q(f"""
            WITH by_branch AS (
                SELECT b.branch_key AS id, b.branch_name AS name, b.region,
                       SUM(a.revenue) AS revenue,
                       SUM(a.completed_visits) AS completed_visits,
                       1.0 * SUM(a.callbacks) / NULLIF(SUM(a.completed_visits), 0) AS callback_rate,
                       1.0 * SUM(a.csat_sum) / NULLIF(SUM(a.csat_n), 0) AS avg_csat
                FROM agg_daily_branch_service a JOIN dim_branch b ON b.branch_key = a.branch_key
                WHERE {w}
                GROUP BY b.branch_key, b.branch_name, b.region
            )
            SELECT *,
                   RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
                   revenue / SUM(revenue) OVER () AS revenue_share
            FROM by_branch ORDER BY revenue DESC""", p)
        return jsonify({"branches": rows})

    @app.get("/api/service-mix")
    def api_service_mix():
        f = parse_filters()
        w, p = where(f)
        rows = q(f"""
            SELECT s.service_key AS id, s.service_name AS name,
                   SUM(a.revenue) AS revenue, SUM(a.completed_visits) AS completed_visits,
                   SUM(a.revenue) / SUM(SUM(a.revenue)) OVER () AS revenue_share
            FROM agg_daily_branch_service a JOIN dim_service s ON s.service_key = a.service_key
            WHERE {w} GROUP BY s.service_key, s.service_name ORDER BY revenue DESC""", p)
        return jsonify({"services": rows})

    @app.get("/api/heatmap")
    def api_heatmap():
        """Callback rate by branch x service. Cells with < 30 completed visits are blanked."""
        f = parse_filters()
        w, p = where(f)
        rows = q(f"""
            SELECT b.branch_name AS branch, s.service_name AS service,
                   SUM(a.completed_visits) AS completed_visits,
                   1.0 * SUM(a.callbacks) / NULLIF(SUM(a.completed_visits), 0) AS callback_rate
            FROM agg_daily_branch_service a
            JOIN dim_branch b ON b.branch_key = a.branch_key
            JOIN dim_service s ON s.service_key = a.service_key
            WHERE {w} GROUP BY b.branch_name, s.service_name""", p)
        for r in rows:
            if r["completed_visits"] < 30:
                r["callback_rate"] = None
        return jsonify({"cells": rows, "min_visits": 30})

    @app.get("/api/technicians")
    def api_technicians():
        f = parse_filters()
        w, p = where(f, alias="f")
        order = request.args.get("order", "top")
        if order not in ("top", "bottom"):
            raise ValueError("order must be top or bottom")
        direction = "ASC" if order == "bottom" else "DESC"
        rows = q(f"""
            WITH tech AS (
                SELECT t.technician_key AS id, t.tech_name AS name, b.branch_name AS branch,
                       SUM(f.is_completed) AS completed_visits,
                       SUM(f.revenue) AS revenue,
                       1.0 * SUM(CASE WHEN f.is_completed = 1 THEN f.is_callback ELSE 0 END)
                           / NULLIF(SUM(f.is_completed), 0) AS callback_rate,
                       1.0 * SUM(f.csat) / NULLIF(COUNT(f.csat), 0) AS avg_csat
                FROM fact_service_visit f
                JOIN dim_technician t ON t.technician_key = f.technician_key
                JOIN dim_branch b ON b.branch_key = f.branch_key
                WHERE {w}
                GROUP BY t.technician_key, t.tech_name, b.branch_name
                HAVING SUM(f.is_completed) >= 50
            )
            SELECT *, ROW_NUMBER() OVER (PARTITION BY branch ORDER BY callback_rate) AS best_in_branch
            FROM tech ORDER BY callback_rate {direction}, revenue DESC LIMIT 10""", p)
        return jsonify({"technicians": rows, "note": "Technicians with at least 50 completed visits."})


    # ------------------------------------------------------------ insights
    MIN_HOTSPOT_VISITS = 300      # completed visits needed before we call a branch/service a hotspot
    MIN_TECH_VISITS = 200         # completed visits needed before we compare a technician

    @app.get("/api/insights")
    def api_insights():
        """Four SQL-driven findings. Thresholds are returned so the page can show them."""
        company = q("""SELECT 1.0 * SUM(CASE WHEN is_completed = 1 THEN is_callback END)
                              / SUM(is_completed) AS rate FROM fact_service_visit""")[0]["rate"]
        hotspots = q(f"""
            WITH x AS (
                SELECT b.branch_name AS branch, s.service_name AS service,
                       SUM(f.is_completed) AS completed_visits,
                       1.0 * SUM(CASE WHEN f.is_completed = 1 THEN f.is_callback END)
                           / SUM(f.is_completed) AS callback_rate
                FROM fact_service_visit f
                JOIN dim_branch b ON b.branch_key = f.branch_key
                JOIN dim_service s ON s.service_key = f.service_key
                GROUP BY b.branch_name, s.service_name
                HAVING SUM(f.is_completed) >= {MIN_HOTSPOT_VISITS}
            )
            SELECT branch, service, completed_visits, callback_rate,
                   callback_rate / :company AS vs_company
            FROM x ORDER BY vs_company DESC LIMIT 8""", {"company": company})
        techs = q(f"""
            WITH t AS (
                SELECT t.tech_name AS name, b.branch_name AS branch,
                       SUM(f.is_completed) AS completed_visits,
                       1.0 * SUM(CASE WHEN f.is_completed = 1 THEN f.is_callback END)
                           / SUM(f.is_completed) AS callback_rate
                FROM fact_service_visit f
                JOIN dim_technician t ON t.technician_key = f.technician_key
                JOIN dim_branch b ON b.branch_key = f.branch_key
                GROUP BY t.tech_name, b.branch_name
                HAVING SUM(f.is_completed) >= {MIN_TECH_VISITS}
            ), u AS (
                SELECT *, AVG(callback_rate) OVER (PARTITION BY branch) AS branch_avg FROM t
            )
            SELECT name, branch, completed_visits, callback_rate, branch_avg,
                   callback_rate / branch_avg AS vs_branch
            FROM u ORDER BY vs_branch DESC LIMIT 8""")
        season = q("""
            WITH m AS (
                SELECT s.service_name AS service, d.month AS month, SUM(f.is_completed) AS visits
                FROM fact_service_visit f
                JOIN dim_service s ON s.service_key = f.service_key
                JOIN dim_date d ON d.date_key = f.date_key
                WHERE d.year = 2025
                GROUP BY s.service_name, d.month
            )
            SELECT service, month, visits,
                   1.0 * visits / AVG(visits) OVER (PARTITION BY service) AS index_vs_avg,
                   RANK() OVER (PARTITION BY service ORDER BY visits DESC) AS peak_rank
            FROM m ORDER BY service, month""")
        plans = q("""
            SELECT c.plan_type AS plan, SUM(f.is_completed) AS completed_visits,
                   SUM(f.revenue) / SUM(f.is_completed) AS revenue_per_visit
            FROM fact_service_visit f
            JOIN dim_customer c ON c.customer_key = f.customer_key
            GROUP BY c.plan_type ORDER BY revenue_per_visit DESC""")
        return jsonify({
            "company_callback_rate": company,
            "thresholds": {"hotspot_min_visits": MIN_HOTSPOT_VISITS, "tech_min_visits": MIN_TECH_VISITS},
            "hotspots": hotspots, "technicians": techs, "seasonality": season,
            "plans": plans, "season_year": 2025,
            "note": "Synthetic demo data. Findings show the method, not a real company's results."})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
