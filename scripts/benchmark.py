"""Measure p50 / p95 server time per endpoint.  Run:  python scripts/benchmark.py [runs]

The job post talks about a p95 target of under 1 second. This is how you would
check that claim: many runs, report percentiles, never a single run.
Times are for THIS demo (SQLite, ~190k fact rows, local machine), not Azure SQL.
"""
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.app import create_app  # noqa: E402

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
ENDPOINTS = ["/api/kpis", "/api/trend", "/api/trend?grain=week", "/api/branches", "/api/service-mix",
             "/api/heatmap", "/api/technicians", "/api/kpis?branch=3&service=2"]

client = create_app().test_client()
print(f"{'endpoint':34}{'p50 ms':>9}{'p95 ms':>9}{'max ms':>9}")
worst = 0
for url in ENDPOINTS:
    client.get(url)  # warm up
    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        assert client.get(url).status_code == 200
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    worst = max(worst, p95)
    print(f"{url:34}{statistics.median(times):9.1f}{p95:9.1f}{times[-1]:9.1f}")
print(f"\nWorst p95: {worst:.1f} ms  ->  {'PASS' if worst < 1000 else 'FAIL'} (target < 1000 ms)")
