-- Practice report queries on the star schema. Each one is executed by tests/test_sql_examples.py.
-- SQLite syntax; the T-SQL differences are noted in comments.

-- Q1. Monthly revenue with month-over-month % change (CTE + LAG window function)
WITH monthly AS (
    SELECT d.month_start, SUM(f.revenue) AS revenue
    FROM fact_service_visit f JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.month_start
)
SELECT month_start, revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month_start))
             / NULLIF(LAG(revenue) OVER (ORDER BY month_start), 0), 1) AS mom_pct
FROM monthly ORDER BY month_start;

-- Q2. Rank branches by revenue inside each region (RANK vs DENSE_RANK vs ROW_NUMBER)
WITH by_branch AS (
    SELECT b.region, b.branch_name, SUM(f.revenue) AS revenue
    FROM fact_service_visit f JOIN dim_branch b ON b.branch_key = f.branch_key
    GROUP BY b.region, b.branch_name
)
SELECT region, branch_name, revenue,
       RANK()       OVER (PARTITION BY region ORDER BY revenue DESC) AS rnk,
       DENSE_RANK() OVER (PARTITION BY region ORDER BY revenue DESC) AS dense_rnk,
       ROW_NUMBER() OVER (PARTITION BY region ORDER BY revenue DESC) AS row_num
FROM by_branch ORDER BY region, rnk;

-- Q3. Running total of revenue within each year
SELECT d.year, d.month_start,
       SUM(a.revenue) AS revenue,
       SUM(SUM(a.revenue)) OVER (PARTITION BY d.year ORDER BY d.month_start) AS ytd_revenue
FROM agg_daily_branch_service a JOIN dim_date d ON d.date_key = a.date_key
GROUP BY d.year, d.month_start ORDER BY d.month_start;

-- Q4. 7-day rolling average of completed visits for one branch (window frame)
WITH daily AS (
    SELECT a.date_key, SUM(a.completed_visits) AS visits
    FROM agg_daily_branch_service a WHERE a.branch_key = 1 GROUP BY a.date_key
)
SELECT date_key, visits,
       ROUND(AVG(visits) OVER (ORDER BY date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS rolling_7d
FROM daily ORDER BY date_key;

-- Q5. Best technician per branch by callback rate (min 200 completed visits). Top-1 per group.
WITH tech AS (
    SELECT t.tech_name, t.branch_key,
           SUM(f.is_completed) AS completed,
           1.0 * SUM(CASE WHEN f.is_completed = 1 THEN f.is_callback ELSE 0 END) / SUM(f.is_completed) AS callback_rate
    FROM fact_service_visit f JOIN dim_technician t ON t.technician_key = f.technician_key
    GROUP BY t.technician_key, t.tech_name, t.branch_key
    HAVING SUM(f.is_completed) >= 200
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY branch_key ORDER BY callback_rate, completed DESC) AS rn FROM tech
)
SELECT b.branch_name, r.tech_name, ROUND(r.callback_rate, 4) AS callback_rate, r.completed
FROM ranked r JOIN dim_branch b ON b.branch_key = r.branch_key WHERE r.rn = 1 ORDER BY b.branch_name;

-- Q6. SCD type 2 "as of" question: revenue by the plan the customer had ON the visit date.
-- Joining on the surrogate key already gives this, because each visit stores the right version.
SELECT c.plan_type, COUNT(*) AS visits, ROUND(SUM(f.revenue), 0) AS revenue
FROM fact_service_visit f JOIN dim_customer c ON c.customer_key = f.customer_key
GROUP BY c.plan_type ORDER BY revenue DESC;

-- Q7. Which customers changed plan? (self-join on the natural key; LEAD would also work)
SELECT cur.customer_id, old.plan_type AS from_plan, cur.plan_type AS to_plan, cur.effective_from AS changed_on
FROM dim_customer cur
JOIN dim_customer old ON old.customer_id = cur.customer_id AND old.effective_to = date(cur.effective_from, '-1 day')
ORDER BY cur.effective_from LIMIT 20;
-- T-SQL: replace date(x, '-1 day') with DATEADD(DAY, -1, x).

-- Q8. Duplicate check (a classic): any visit_id appearing more than once?
SELECT visit_id, COUNT(*) AS n FROM fact_service_visit GROUP BY visit_id HAVING COUNT(*) > 1;

-- Q9. Callback rate by month, only where there are at least 500 completed visits (HAVING vs WHERE)
SELECT d.month_start, SUM(a.completed_visits) AS completed,
       ROUND(1.0 * SUM(a.callbacks) / SUM(a.completed_visits), 4) AS callback_rate
FROM agg_daily_branch_service a JOIN dim_date d ON d.date_key = a.date_key
GROUP BY d.month_start HAVING SUM(a.completed_visits) >= 500 ORDER BY d.month_start;
-- T-SQL note: SQL Server needs a CAST because integer / integer is integer division,
-- e.g. 1.0 * SUM(...) / NULLIF(SUM(...), 0) as used here.
