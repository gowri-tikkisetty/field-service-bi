"""Data-quality checks: the same kind of validation you would run on a new report."""
from datetime import date, timedelta


def one(db, sql):
    return db.execute(sql).fetchone()[0]


def test_aggregate_reconciles_with_fact(db):
    f = db.execute("""SELECT COUNT(*), SUM(is_completed),
                      SUM(CASE WHEN is_completed=1 THEN is_callback ELSE 0 END), ROUND(SUM(revenue),2)
                      FROM fact_service_visit""").fetchone()
    a = db.execute("""SELECT SUM(scheduled_visits), SUM(completed_visits), SUM(callbacks), ROUND(SUM(revenue),2)
                      FROM agg_daily_branch_service""").fetchone()
    assert tuple(f) == tuple(a)


def test_no_orphan_foreign_keys(db):
    for dim, col in [("dim_date", "date_key"), ("dim_customer", "customer_key"), ("dim_branch", "branch_key"),
                     ("dim_service", "service_key"), ("dim_technician", "technician_key")]:
        orphans = one(db, f"""SELECT COUNT(*) FROM fact_service_visit f
                              LEFT JOIN {dim} d ON d.{col} = f.{col} WHERE d.{col} IS NULL""")
        assert orphans == 0, f"{dim} has orphan keys"


def test_business_rules(db):
    assert one(db, "SELECT COUNT(*) FROM fact_service_visit WHERE is_completed = 0 AND revenue <> 0") == 0
    assert one(db, "SELECT COUNT(*) FROM fact_service_visit WHERE is_completed = 0 AND is_callback = 1") == 0
    assert one(db, "SELECT COUNT(*) FROM fact_service_visit WHERE revenue < 0") == 0
    assert one(db, "SELECT COUNT(*) FROM fact_service_visit WHERE csat IS NOT NULL AND (csat < 1 OR csat > 5)") == 0


def test_scd2_one_current_row_per_customer(db):
    bad = one(db, """SELECT COUNT(*) FROM (SELECT customer_id FROM dim_customer
                     GROUP BY customer_id HAVING SUM(is_current) <> 1)""")
    assert bad == 0


def test_scd2_no_gaps_or_overlaps(db):
    rows = db.execute("""SELECT customer_id, effective_from, effective_to FROM dim_customer
                         ORDER BY customer_id, effective_from""").fetchall()
    prev = None
    for cid, start, end in rows:
        if prev and prev[0] == cid:
            expected = date.fromisoformat(prev[2]) + timedelta(days=1)
            assert date.fromisoformat(start) == expected, f"gap/overlap for customer {cid}"
        prev = (cid, start, end)


def test_each_visit_uses_plan_version_in_effect_on_that_date(db):
    # Visits can be booked before the first recorded version starts (data arrives late);
    # after that, the visit date must fall inside the version's date range.
    bad = one(db, """SELECT COUNT(*) FROM fact_service_visit f
                     JOIN dim_date d ON d.date_key = f.date_key
                     JOIN dim_customer c ON c.customer_key = f.customer_key
                     WHERE d.full_date < c.effective_from OR d.full_date > c.effective_to""")
    assert bad == 0
