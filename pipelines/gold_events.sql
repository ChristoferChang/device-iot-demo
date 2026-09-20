-- Event stream over full silver history. Batch recompute (not foreachBatch lag)
-- by design: the JCB review's bug #2 showed LAG across micro-batches silently
-- drops transitions — recomputing over the whole table makes that impossible.
-- Event types: ENGINE_START / ENGINE_STOP (transitions), FUEL_ANOMALY
-- (>20-point drop in one tick — the EXC-0007 Wednesday pattern), BATTERY_LOW
-- (P0562), SERVICE_DUE (SVC_DUE).
CREATE OR REFRESH MATERIALIZED VIEW gold_events AS
WITH w AS (
  SELECT *,
         LAG(engine_running) OVER (PARTITION BY equipment_id ORDER BY snapshot_ts) AS prev_running,
         LAG(fuel_level_pct) OVER (PARTITION BY equipment_id ORDER BY snapshot_ts) AS prev_fuel
  FROM silver_telemetry
),
starts AS (
  SELECT equipment_id, equipment_class, snapshot_ts AS event_ts,
         'ENGINE_START' AS event_type,
         CAST(NULL AS DOUBLE) AS metric_value,
         CAST(NULL AS STRING) AS detail
  FROM w WHERE prev_running = false AND engine_running = true
),
stops AS (
  SELECT equipment_id, equipment_class, snapshot_ts AS event_ts,
         'ENGINE_STOP' AS event_type,
         CAST(NULL AS DOUBLE) AS metric_value,
         CAST(NULL AS STRING) AS detail
  FROM w WHERE prev_running = true AND engine_running = false
),
fuel_anomalies AS (
  SELECT equipment_id, equipment_class, snapshot_ts AS event_ts,
         'FUEL_ANOMALY' AS event_type,
         ROUND(prev_fuel - fuel_level_pct, 1) AS metric_value,
         CONCAT('fuel dropped ', CAST(ROUND(prev_fuel - fuel_level_pct, 1) AS STRING),
                ' points in one tick') AS detail
  FROM w WHERE prev_fuel IS NOT NULL AND (prev_fuel - fuel_level_pct) > 20
),
battery_low AS (
  SELECT equipment_id, equipment_class, snapshot_ts AS event_ts,
         'BATTERY_LOW' AS event_type,
         battery_voltage AS metric_value,
         'P0562 system voltage low' AS detail
  FROM w WHERE ARRAY_CONTAINS(fault_codes, 'P0562')
),
service_due AS (
  SELECT equipment_id, equipment_class, snapshot_ts AS event_ts,
         'SERVICE_DUE' AS event_type,
         engine_hours AS metric_value,
         'SVC_DUE: engine hours over 500h service threshold' AS detail
  FROM w WHERE ARRAY_CONTAINS(fault_codes, 'SVC_DUE')
)
SELECT * FROM starts
UNION ALL SELECT * FROM stops
UNION ALL SELECT * FROM fuel_anomalies
UNION ALL SELECT * FROM battery_low
UNION ALL SELECT * FROM service_due;
