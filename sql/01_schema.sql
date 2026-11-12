-- Star schema for a field-service (pest control style) business.
-- GRAIN of fact_service_visit: one row per scheduled service visit.
-- SQLite dialect (runs anywhere). The Azure SQL / T-SQL version of the load
-- procedure is in sql/tsql/usp_load_agg_daily.sql.

DROP TABLE IF EXISTS agg_daily_branch_service;
DROP TABLE IF EXISTS fact_service_visit;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_technician;
DROP TABLE IF EXISTS dim_service;
DROP TABLE IF EXISTS dim_branch;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,   -- YYYYMMDD
    full_date    TEXT NOT NULL,         -- ISO date
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    month_start  TEXT NOT NULL,         -- first day of month, handy for trends
    week_start   TEXT NOT NULL,         -- Monday of the week
    day_of_week  INTEGER NOT NULL,      -- 1 = Monday ... 7 = Sunday
    is_weekend   INTEGER NOT NULL
);

CREATE TABLE dim_branch (
    branch_key   INTEGER PRIMARY KEY,
    branch_name  TEXT NOT NULL,
    region       TEXT NOT NULL,
    state        TEXT NOT NULL
);

CREATE TABLE dim_service (
    service_key  INTEGER PRIMARY KEY,
    service_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    is_recurring INTEGER NOT NULL
);

CREATE TABLE dim_technician (
    technician_key INTEGER PRIMARY KEY,
    tech_name      TEXT NOT NULL,       -- synthetic names only
    branch_key     INTEGER NOT NULL REFERENCES dim_branch(branch_key),
    hire_date      TEXT NOT NULL
);

-- Slowly changing dimension TYPE 2: one row per customer per plan version.
CREATE TABLE dim_customer (
    customer_key   INTEGER PRIMARY KEY,   -- surrogate key (one per version)
    customer_id    INTEGER NOT NULL,      -- natural / business key
    plan_type      TEXT NOT NULL,         -- Monthly, Bi-Monthly, Quarterly, One-Time
    zip3           TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to   TEXT NOT NULL,         -- '9999-12-31' for the current version
    is_current     INTEGER NOT NULL
);

CREATE TABLE fact_service_visit (
    visit_id       INTEGER PRIMARY KEY,
    date_key       INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key   INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    branch_key     INTEGER NOT NULL REFERENCES dim_branch(branch_key),
    service_key    INTEGER NOT NULL REFERENCES dim_service(service_key),
    technician_key INTEGER NOT NULL REFERENCES dim_technician(technician_key),
    is_completed   INTEGER NOT NULL,      -- 1 completed, 0 cancelled / no access
    is_callback    INTEGER NOT NULL,      -- 1 if customer needed a re-service
    revenue        REAL    NOT NULL,      -- 0 when not completed
    duration_min   INTEGER NOT NULL,
    csat           INTEGER                -- 1-5, NULL when no survey returned
);

-- Pre-aggregated table the dashboard reads from (rebuilt by 03_load_agg_daily.sql).
CREATE TABLE agg_daily_branch_service (
    date_key          INTEGER NOT NULL,
    branch_key        INTEGER NOT NULL,
    service_key       INTEGER NOT NULL,
    scheduled_visits  INTEGER NOT NULL,
    completed_visits  INTEGER NOT NULL,
    callbacks         INTEGER NOT NULL,
    revenue           REAL    NOT NULL,
    csat_sum          INTEGER NOT NULL,
    csat_n            INTEGER NOT NULL,
    PRIMARY KEY (date_key, branch_key, service_key)
);
