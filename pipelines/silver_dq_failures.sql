-- DQ quarantine: inverse of the silver_telemetry expectations. Rows failing any
-- check land here instead of being silently dropped, so the demo can show
-- observability ("DQ caught N bad readings"). Mirrors silver_telemetry constraints.
CREATE OR REFRESH STREAMING TABLE silver_dq_failures AS
SELECT
  equipment_id,
  equipment_class,
  snapshot_ts,
  _ingest_timestamp,
  payload_raw,
  CONCAT_WS(' | ',
    CASE WHEN NOT (battery_voltage BETWEEN 8.0 AND 16.0) THEN 'valid_battery' END,
    CASE WHEN NOT (fuel_level_pct BETWEEN 0 AND 100) THEN 'valid_fuel' END,
    CASE WHEN NOT (coolant_temp_c BETWEEN -20 AND 140) THEN 'valid_coolant' END,
    CASE WHEN NOT (latitude BETWEEN 30 AND 38 AND longitude BETWEEN -115 AND -108) THEN 'valid_gps' END,
    CASE WHEN NOT (engine_hours >= 0 AND engine_hours < 100000) THEN 'valid_hours' END
  ) AS dq_reasons
FROM STREAM(bronze_telemetry)
WHERE NOT (battery_voltage BETWEEN 8.0 AND 16.0)
   OR NOT (fuel_level_pct BETWEEN 0 AND 100)
   OR NOT (coolant_temp_c BETWEEN -20 AND 140)
   OR NOT (latitude BETWEEN 30 AND 38 AND longitude BETWEEN -115 AND -108)
   OR NOT (engine_hours >= 0 AND engine_hours < 100000);
