/* ---------------------------------------------------------------------------
   Azure SQL / SQL Server version of the load procedure (INCREMENTAL).
   NOTE: written to show the pattern. It was NOT executed in this project
   (the demo runs on SQLite); test it in your own Azure SQL database.
   Pattern: reload only the last @days_back days inside one transaction.
--------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.usp_load_agg_daily
    @days_back INT = 7
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @from_key INT =
        CONVERT(INT, FORMAT(DATEADD(DAY, -@days_back, CAST(GETDATE() AS DATE)), 'yyyyMMdd'));

    BEGIN TRAN;

        DELETE FROM dbo.agg_daily_branch_service
        WHERE date_key >= @from_key;

        INSERT INTO dbo.agg_daily_branch_service
            (date_key, branch_key, service_key, scheduled_visits, completed_visits,
             callbacks, revenue, csat_sum, csat_n)
        SELECT  f.date_key, f.branch_key, f.service_key,
                COUNT(*),
                SUM(CAST(f.is_completed AS INT)),
                SUM(CASE WHEN f.is_completed = 1 THEN CAST(f.is_callback AS INT) ELSE 0 END),
                ROUND(SUM(f.revenue), 2),
                COALESCE(SUM(f.csat), 0),
                SUM(CASE WHEN f.csat IS NULL THEN 0 ELSE 1 END)
        FROM    dbo.fact_service_visit AS f
        WHERE   f.date_key >= @from_key
        GROUP BY f.date_key, f.branch_key, f.service_key;

    COMMIT;
END;
GO
/* Tuning checklist used in the project (talk track for "p95 under 1 second"):
   1. Dashboard reads the pre-aggregated table, not the 200k+ row fact table.
   2. Composite indexes match the filters: (branch_key, date_key), (service_key, date_key).
   3. Check the plan: look for scans vs seeks, key lookups, and implicit conversions.
   4. Measure p50 / p95 over many runs (scripts/benchmark.py), not a single run.
*/
