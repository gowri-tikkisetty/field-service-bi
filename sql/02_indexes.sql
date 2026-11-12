-- Indexes chosen for the dashboard queries (filter by date range, branch, service).
CREATE INDEX ix_fact_date_branch      ON fact_service_visit (date_key, branch_key);
CREATE INDEX ix_fact_tech_date        ON fact_service_visit (technician_key, date_key);
CREATE INDEX ix_fact_customer         ON fact_service_visit (customer_key);
CREATE INDEX ix_cust_natural          ON dim_customer (customer_id, effective_from);
CREATE INDEX ix_agg_branch_date       ON agg_daily_branch_service (branch_key, date_key);
CREATE INDEX ix_agg_service_date      ON agg_daily_branch_service (service_key, date_key);
