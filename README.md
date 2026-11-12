# Field Service Performance Dashboard

A small, complete analytics app: **SQL star schema -> pre-aggregated table -> Flask API -> D3 dashboard**,
with automated tests and a speed check. It uses **synthetic data** for a pest-control style business
(8 branches, about 190,000 service visits, Jan 2025 - Oct 2026). Built as a portfolio project
covering SQL, data modeling, data visualization and UI/UX.

> Note: this project was developed with the help of AI tools. I reviewed, ran and tested the code.

## What it demonstrates

| Skill | Where to see it |
|---|---|
| Good SQL (CTEs, window functions, stored procedures, tuning) | `sql/04_report_queries.sql`, `sql/tsql/usp_load_agg_daily.sql`, `app/app.py` queries |
| Dimensional modeling (grain, star schema, slowly changing dimensions) | `sql/01_schema.sql` (SCD type 2 in `dim_customer`) |
| Performance target (p95 under 1 second) | `sql/02_indexes.sql`, pre-aggregated table, `scripts/benchmark.py` |
| Validate new reports against existing ones, document metric definitions | `tests/test_api.py::test_kpis_match_raw_fact_table`, `/metrics` page |
| Python / Flask backend, JavaScript + D3 front end | `app/app.py`, `app/static/app.js` |
| Data visualization and UI/UX judgment | see "Design decisions" below |
| Git workflow | see "Put it on GitHub" below |

## Run it (step by step)

You need Python 3.10 or newer. Check with `python --version` (on Mac try `python3 --version`).

1. Open a terminal in this folder (`field-service-bi`).
2. Create a virtual environment (keeps packages tidy):
   - Windows: `python -m venv .venv` then `.venv\Scripts\activate`
   - Mac/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
3. Install: `pip install -r requirements.txt`
4. Build the database (takes a few seconds): `python scripts/build_db.py`
5. Run the tests (33 should pass): `python -m pytest -q`
6. Check speed: `python scripts/benchmark.py`
7. Start the app: `python -m flask --app app.app run`
8. Open http://127.0.0.1:5000 in your browser. Press Ctrl+C in the terminal to stop.

If port 5000 is busy (common on Mac), add `--port 5057` and open that port instead.

## Folder map

```
sql/01_schema.sql            tables: 5 dimensions + 1 fact + 1 aggregate (grain is documented at the top)
sql/02_indexes.sql           indexes that match the dashboard filters
sql/03_load_agg_daily.sql    rebuilds the aggregate table from the fact table
sql/04_report_queries.sql    9 practice queries (window functions, SCD2, top-1-per-group)
sql/tsql/usp_load_agg_daily.sql   Azure SQL stored procedure version (incremental load) - NOT executed here
scripts/build_db.py          creates the synthetic data (seeded, so it is the same every time)
scripts/benchmark.py         p50 / p95 timing per endpoint
app/app.py                   Flask API + metric definitions in one dictionary
app/templates/               dashboard page and metric-definitions page
app/static/app.js, style.css front end (D3 v7 is bundled in static/vendor, no internet needed)
tests/                       33 tests: data quality, API, SQL examples, insights
```

## Design decisions

- **Choose the chart for the question.** Trend over time -> line. Ranking branches -> sorted horizontal bars
  (easy to read labels, easy to compare lengths). Branch x service callback rate -> heatmap, because the
  question is "where are the hot spots?". Exact numbers for technicians -> a table.
- **One accent color, grey for everything else.** Color is used to mean something: the selected branch,
  or "worse than last year". Good/bad coloring respects direction (a higher callback rate is bad).
- **Never rely on color alone.** Changes show an arrow and a sign, heatmap cells print their number,
  and the trend has a "view as table" version. Colors are chosen to stay readable for color-blind users.
- **Honest comparisons.** Changes are compared with the *same dates one year earlier* so seasons
  (mosquito and termite season) do not look like growth. If last year's data does not exist, the
  dashboard says so instead of showing a made-up number. Partial weeks are dropped or marked.
- **Zero baseline where it matters.** Revenue and visit charts start at zero; rate and score charts zoom
  to their range, because a bar-style zero baseline would flatten a 4.2 to 4.4 change.
- **Accessible and responsive.** Keyboard-reachable bars, focus outlines, skip link, screen-reader labels,
  light and dark mode, phone layout (heatmap scrolls sideways instead of squashing labels).
- **Fast by design.** The dashboard reads a small pre-aggregated table (about 25,000 rows) instead of the
  190,000-row fact table. Only the technician leaderboard needs the fact table, and it is still well
  under a second.
- **Safe by design.** Every filter is validated; values go into SQL as parameters, never pasted in.
  The database connection is read-only. Bad input returns a clear 400 error, not a crash.

## Ideas to extend it

1. Run `scripts/benchmark.py`, remove the indexes in `sql/02_indexes.sql`, rebuild, and compare the timings.
2. Add a new metric (for example "visits per technician per day") in `METRICS` and `METRIC_SQL` in `app/app.py`.
3. Write a new report query in `sql/04_report_queries.sql` and add it to the tests.

## Known limits

- Demo runs on **SQLite**. The Azure SQL stored procedure is provided as a pattern and was **not executed**.
- Data is synthetic. Customer, branch and technician names are made up.
- No login, no deployment. It is a local sample, not a production app.

## Operations Insights page

`/insights` is a second web page built with HTML, CSS, JavaScript and D3. It answers four manager questions with SQL:
callback hotspots (branch x service vs company average), technician outliers (vs own-branch average, window functions),
seasonal demand peaks (service x month index) and revenue per visit by customer plan (SCD Type 2 join).
Endpoint: `GET /api/insights`. Tests: `tests/test_insights.py`. All numbers come from synthetic data and show the method only.
