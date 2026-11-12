-- "Load procedure" for the pre-aggregated table.
-- Full rebuild keeps it simple and idempotent; the T-SQL version in
-- sql/tsql/ shows the incremental (last N days) pattern.
DELETE FROM agg_daily_branch_service;

INSERT INTO agg_daily_branch_service
SELECT  f.date_key,
        f.branch_key,
        f.service_key,
        COUNT(*)                                        AS scheduled_visits,
        SUM(f.is_completed)                             AS completed_visits,
        SUM(CASE WHEN f.is_completed = 1 THEN f.is_callback ELSE 0 END) AS callbacks,
        ROUND(SUM(f.revenue), 2)                        AS revenue,
        COALESCE(SUM(f.csat), 0)                        AS csat_sum,
        SUM(CASE WHEN f.csat IS NULL THEN 0 ELSE 1 END) AS csat_n
FROM    fact_service_visit f
GROUP BY f.date_key, f.branch_key, f.service_key;
