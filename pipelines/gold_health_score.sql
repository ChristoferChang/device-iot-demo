-- Per-machine risk score (0 = healthy, 100 = critical), rolling 7 days relative
-- to the latest tick. Additive weights:
--   battery running-voltage < 11.5V -> 40, < 12.2V -> 25
--   fuel anomaly in window          -> 20
--   engine hours > 500 (service)    -> 20
--   running ratio < 5% (idle)       -> 15
-- Battery is scored on voltage WHILE RUNNING: parked machines sag to ~11.8V
-- normally, so raw min voltage would flag the entire fleet.
-- Expected top-4: GEN-0042 (25), EXC-0007 (20), CMP-0005 (20), LFT-0031 (15).
CREATE OR REFRESH MATERIALIZED VIEW gold_health_score AS
WITH now_ts AS (
  SELECT MAX(snapshot_ts) AS now_ts FROM silver_telemetry
),
recent AS (
  SELECT s.* FROM silver_telemetry s CROSS JOIN now_ts n
  WHERE s.snapshot_ts >= n.now_ts - INTERVAL 7 DAYS
),
per_machine AS (
  SELECT
    equipment_id,
    ANY_VALUE(equipment_class) AS equipment_class,
    MIN(CASE WHEN engine_running THEN battery_voltage END) AS min_battery_running_7d,
    MAX(engine_hours) AS engine_hours_latest,
    AVG(CASE WHEN engine_running THEN 1.0 ELSE 0.0 END) AS running_ratio_7d
  FROM recent
  GROUP BY equipment_id
),
anomalies AS (
  SELECT e.equipment_id, COUNT(*) AS fuel_anomalies_7d
  FROM gold_events e CROSS JOIN now_ts n
  WHERE e.event_type = 'FUEL_ANOMALY'
    AND e.event_ts >= n.now_ts - INTERVAL 7 DAYS
  GROUP BY e.equipment_id
)
SELECT
  p.equipment_id,
  p.equipment_class,
  p.min_battery_running_7d,
  ROUND(p.engine_hours_latest, 1) AS engine_hours_latest,
  ROUND(p.running_ratio_7d, 3) AS running_ratio_7d,
  COALESCE(a.fuel_anomalies_7d, 0) AS fuel_anomalies_7d,
  LEAST(100,
    CASE WHEN p.min_battery_running_7d < 11.5 THEN 40
         WHEN p.min_battery_running_7d < 12.2 THEN 25
         ELSE 0 END
    + CASE WHEN COALESCE(a.fuel_anomalies_7d, 0) > 0 THEN 20 ELSE 0 END
    + CASE WHEN p.engine_hours_latest > 500 THEN 20 ELSE 0 END
    + CASE WHEN p.running_ratio_7d < 0.05 THEN 15 ELSE 0 END
  ) AS health_risk_score
FROM per_machine p
LEFT JOIN anomalies a ON p.equipment_id = a.equipment_id;
