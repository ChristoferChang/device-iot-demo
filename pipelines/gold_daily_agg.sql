-- Daily rollup per equipment class: utilization trend + health context for the
-- exec dashboard. Utilization = share of 5-min ticks with engine running.
CREATE OR REFRESH MATERIALIZED VIEW gold_daily_agg AS
SELECT
  equipment_class,
  CAST(snapshot_ts AS DATE) AS day,
  COUNT(DISTINCT equipment_id) AS machines_reporting,
  ROUND(AVG(CASE WHEN engine_running THEN 1.0 ELSE 0.0 END), 4) AS utilization_pct,
  ROUND(AVG(fuel_level_pct), 1) AS avg_fuel_pct,
  ROUND(AVG(battery_voltage), 2) AS avg_battery_voltage
FROM silver_telemetry
GROUP BY equipment_class, CAST(snapshot_ts AS DATE);
