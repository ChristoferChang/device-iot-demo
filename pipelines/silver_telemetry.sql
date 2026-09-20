-- Silver telemetry: dedupe on (equipment_id, snapshot_ts) — the live-ingest job
-- retries are safe because identical ticks collapse here. Ticks are 5-min aligned,
-- so the dedup key doubles as the streaming aggregation key. DQ checks drop invalid
-- rows (mirror constraints live in silver_dq_failures.sql which quarantines them).
-- NOTE: ROW_NUMBER() over a stream is rejected by this runtime (NON_TIME_WINDOW_
-- NOT_SUPPORTED_IN_STREAMING) — stateful GROUP BY is the supported dedup form.
CREATE OR REFRESH STREAMING TABLE silver_telemetry (
  CONSTRAINT valid_battery EXPECT (battery_voltage BETWEEN 8.0 AND 16.0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_fuel EXPECT (fuel_level_pct BETWEEN 0 AND 100) ON VIOLATION DROP ROW,
  CONSTRAINT valid_coolant EXPECT (coolant_temp_c BETWEEN -20 AND 140) ON VIOLATION DROP ROW,
  CONSTRAINT valid_gps EXPECT (latitude BETWEEN 30 AND 38 AND longitude BETWEEN -115 AND -108) ON VIOLATION DROP ROW,
  CONSTRAINT valid_hours EXPECT (engine_hours >= 0 AND engine_hours < 100000) ON VIOLATION DROP ROW
)
AS SELECT
  equipment_id,
  snapshot_ts,
  ANY_VALUE(equipment_class)  AS equipment_class,
  ANY_VALUE(engine_running)   AS engine_running,
  ANY_VALUE(engine_hours)     AS engine_hours,
  ANY_VALUE(fuel_level_pct)   AS fuel_level_pct,
  ANY_VALUE(battery_voltage)  AS battery_voltage,
  ANY_VALUE(coolant_temp_c)   AS coolant_temp_c,
  ANY_VALUE(latitude)         AS latitude,
  ANY_VALUE(longitude)        AS longitude,
  ANY_VALUE(speed_kph)        AS speed_kph,
  ANY_VALUE(fault_codes)      AS fault_codes,
  ANY_VALUE(payload_raw)      AS payload_raw,
  MAX(_ingest_timestamp)      AS _ingest_timestamp
FROM STREAM(bronze_telemetry)
GROUP BY equipment_id, snapshot_ts;
