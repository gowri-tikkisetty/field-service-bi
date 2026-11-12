"""Build the demo database (SQLite) with SYNTHETIC data.

Run:  python scripts/build_db.py
Creates data/field_service.db. All names, customers and numbers are made up
(seeded random generator) so the result is the same every time.
"""
import bisect
import math
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "field_service.db"
SQL_DIR = ROOT / "sql"

SEED = 42
START = date(2025, 1, 1)
END = date(2026, 10, 31)

BRANCHES = [  # name, region, state, size multiplier, callback risk
    ("Dallas North", "North Texas", "TX", 1.25, 0.060),
    ("Irving", "North Texas", "TX", 1.10, 0.055),
    ("Fort Worth", "North Texas", "TX", 0.95, 0.075),
    ("Plano", "North Texas", "TX", 1.00, 0.050),
    ("Austin", "Central Texas", "TX", 0.90, 0.065),
    ("San Antonio", "Central Texas", "TX", 0.80, 0.085),
    ("Houston", "Gulf Coast", "TX", 1.15, 0.070),
    ("Oklahoma City", "Plains", "OK", 0.60, 0.095),
]

SERVICES = [  # name, category, recurring, base price, minutes
    ("General Pest - Recurring", "Recurring", 1, 118.0, 38),
    ("Mosquito Control", "Seasonal", 1, 92.0, 30),
    ("Rodent Control", "Specialty", 0, 245.0, 55),
    ("Termite Treatment", "Specialty", 0, 640.0, 120),
    ("Initial Clean-Out", "One-Time", 0, 210.0, 70),
    ("Lawn Pest", "Seasonal", 1, 76.0, 28),
]

PLANS = ["Monthly", "Bi-Monthly", "Quarterly", "One-Time"]
PLAN_FACTOR = {"Monthly": 0.88, "Bi-Monthly": 0.94, "Quarterly": 1.0, "One-Time": 1.18}
OPEN_END = "9999-12-31"


def seasonal(service, month):
    """Demand multiplier by month (1-12) for each service."""
    if service == "Mosquito Control":
        return {4: 0.6, 5: 1.4, 6: 2.0, 7: 2.2, 8: 2.1, 9: 1.5, 10: 0.5}.get(month, 0.05)
    if service == "Lawn Pest":
        return {3: 0.6, 4: 1.2, 5: 1.5, 6: 1.5, 7: 1.3, 8: 1.2, 9: 1.0, 10: 0.5}.get(month, 0.1)
    if service == "Termite Treatment":
        return {3: 1.5, 4: 2.0, 5: 2.0, 6: 1.4}.get(month, 0.6)
    if service == "Rodent Control":
        return {10: 1.5, 11: 1.9, 12: 2.0, 1: 2.0, 2: 1.6, 3: 1.1}.get(month, 0.6)
    if service == "Initial Clean-Out":
        return 1.0 + 0.3 * math.sin((month - 2) / 12 * 2 * math.pi)
    return 1.0 + 0.15 * math.sin((month - 3) / 12 * 2 * math.pi)


def run_sql_file(con, name):
    con.executescript((SQL_DIR / name).read_text())


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    rng = random.Random(SEED)
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    run_sql_file(con, "01_schema.sql")

    # ---- dim_date
    rows = []
    for d in daterange(START, END):
        dow = d.isoweekday()
        rows.append((int(d.strftime("%Y%m%d")), d.isoformat(), d.year, (d.month - 1) // 3 + 1,
                     d.month, d.replace(day=1).isoformat(),
                     (d - timedelta(days=dow - 1)).isoformat(), dow, 1 if dow >= 6 else 0))
    con.executemany("INSERT INTO dim_date VALUES (?,?,?,?,?,?,?,?,?)", rows)

    # ---- dim_branch / dim_service
    con.executemany("INSERT INTO dim_branch VALUES (?,?,?,?)",
                    [(i + 1, b[0], b[1], b[2]) for i, b in enumerate(BRANCHES)])
    con.executemany("INSERT INTO dim_service VALUES (?,?,?,?)",
                    [(i + 1, s[0], s[1], s[2]) for i, s in enumerate(SERVICES)])

    # ---- dim_technician (a few strong, a few weak -> gives the leaderboard a story)
    techs = []          # (key, name, branch_key, hire_date, callback_multiplier)
    tkey = 0
    for bi, b in enumerate(BRANCHES):
        for n in range(max(5, int(10 * b[3]))):
            tkey += 1
            hire = START - timedelta(days=rng.randint(60, 2200))
            skill = rng.choice([0.55, 0.8, 0.9, 1.0, 1.0, 1.1, 1.3, 1.7])
            techs.append((tkey, f"Tech {tkey:03d}", bi + 1, hire.isoformat(), skill))
    con.executemany("INSERT INTO dim_technician VALUES (?,?,?,?)", [t[:4] for t in techs])
    techs_by_branch = {}
    for t in techs:
        techs_by_branch.setdefault(t[2], []).append(t)

    # ---- dim_customer (SCD Type 2) --------------------------------------
    customers = []      # (customer_id, branch_key, start_date)
    cust_versions = {}  # customer_id -> sorted list of (from_date, customer_key)
    cust_rows = []
    ckey = 0
    n_customers = 9000
    weights = [b[3] for b in BRANCHES]
    for cid in range(1, n_customers + 1):
        bk = rng.choices(range(1, len(BRANCHES) + 1), weights)[0]
        start = START - timedelta(days=rng.randint(0, 400)) + timedelta(days=rng.randint(0, 700))
        start = min(start, END - timedelta(days=30))
        plan = rng.choices(PLANS, [0.18, 0.12, 0.50, 0.20])[0]
        zip3 = str(rng.choice([750, 751, 752, 760, 761, 787, 782, 770, 731]))
        versions = [(start, plan)]
        if plan != "One-Time" and rng.random() < 0.28 and (END - start).days > 120:
            change = start + timedelta(days=rng.randint(60, (END - start).days - 30))
            new_plan = rng.choice([p for p in PLANS if p not in (plan, "One-Time")])
            versions.append((change, new_plan))
        customers.append((cid, bk, start))
        cust_versions[cid] = []
        for vi, (vfrom, vplan) in enumerate(versions):
            ckey += 1
            vto = (versions[vi + 1][0] - timedelta(days=1)).isoformat() if vi + 1 < len(versions) else OPEN_END
            cust_rows.append((ckey, cid, vplan, zip3, vfrom.isoformat(), vto, 1 if vto == OPEN_END else 0))
            cust_versions[cid].append((vfrom, ckey, vplan))
    con.executemany("INSERT INTO dim_customer VALUES (?,?,?,?,?,?,?)", cust_rows)

    cust_by_branch = {}
    for cid, bk, start in customers:
        cust_by_branch.setdefault(bk, []).append((start, cid))
    for bk in cust_by_branch:
        cust_by_branch[bk].sort()

    # ---- fact_service_visit ---------------------------------------------
    fact = []
    visit_id = 0
    total_days = (END - START).days
    for d in daterange(START, END):
        dow = d.isoweekday()
        if dow == 7:
            continue
        dow_mult = 1.0 if dow <= 5 else 0.35
        growth = 1.0 + 0.22 * ((d - START).days / total_days)   # business grows ~22% over the period
        date_key = int(d.strftime("%Y%m%d"))
        svc_w = [seasonal(s[0], d.month) for s in SERVICES]
        for bi, b in enumerate(BRANCHES):
            bk = bi + 1
            lam = 44 * b[3] * dow_mult * growth * (0.55 + 0.45 * (sum(svc_w) / len(svc_w)))
            n = max(0, int(rng.gauss(lam, math.sqrt(lam))))
            pool = cust_by_branch[bk]
            # only customers who already started
            idx = bisect.bisect_right(pool, (d, 10**9))
            if idx == 0:
                continue
            for _ in range(n):
                _, cid = pool[rng.randrange(idx)]
                versions = cust_versions[cid]
                ver = versions[0]
                for v in versions:
                    if v[0] <= d:
                        ver = v
                plan = ver[2]
                si = rng.choices(range(len(SERVICES)), svc_w)[0]
                svc = SERVICES[si]
                tech = rng.choice(techs_by_branch[bk])
                visit_id += 1
                completed = 1 if rng.random() > 0.045 else 0
                cb_p = b[4] * tech[4] * (1.5 if svc[0] in ("Rodent Control", "Termite Treatment") else 1.0)
                callback = 1 if (completed and rng.random() < cb_p) else 0
                price = svc[3] * PLAN_FACTOR[plan] * rng.uniform(0.9, 1.15)
                revenue = round(price, 2) if completed else 0.0
                minutes = int(svc[4] * rng.uniform(0.75, 1.35)) if completed else 0
                csat = None
                if completed and rng.random() < 0.31:
                    base = 4.55 - 1.4 * callback - 0.25 * (tech[4] - 1)
                    csat = max(1, min(5, int(round(rng.gauss(base, 0.8)))))
                fact.append((visit_id, date_key, ver[1], bk, si + 1, tech[0],
                             completed, callback, revenue, minutes, csat))
    con.executemany("INSERT INTO fact_service_visit VALUES (?,?,?,?,?,?,?,?,?,?,?)", fact)

    run_sql_file(con, "03_load_agg_daily.sql")
    run_sql_file(con, "02_indexes.sql")
    con.execute("ANALYZE")
    con.commit()
    n_fact = con.execute("SELECT COUNT(*) FROM fact_service_visit").fetchone()[0]
    n_agg = con.execute("SELECT COUNT(*) FROM agg_daily_branch_service").fetchone()[0]
    con.close()
    print(f"Built {DB_PATH}")
    print(f"  fact_service_visit rows: {n_fact:,}")
    print(f"  agg_daily_branch_service rows: {n_agg:,}")
    print(f"  dim_customer rows (SCD2 versions): {len(cust_rows):,}")


if __name__ == "__main__":
    sys.exit(main())
