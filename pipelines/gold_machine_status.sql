-- Latest snapshot per machine: "right now" state for the dashboard KPIs and
-- Genie current-state questions. Batch read of silver (full history is cheap:
-- ~300 machines), so window functions are allowed here unlike in the stream.
CREATE OR REFRESH MATERIALIZED VIEW gold_machine_status AS
SELECT
  equipment_id, equipment_class, snapshot_ts, engine_running, engine_hours,
  fuel_level_pct, battery_voltage, coolant_temp_c, latitude, longitude,
  speed_kph, fault_codes, _ingest_timestamp
FROM (
  SELECT *,
         ROW_NUMBER() OVER (PARTITION BY equipment_id ORDER BY snapshot_ts DESC) AS rn
  FROM silver_telemetry
)
WHERE rn = 1;
