# Databricks notebook source
# ai_classify-based performance triage for the equipment-rental IoT fleet.
#
# For every machine in sbr_iot_demo.fleet.gold_machine_status it builds a compact
# performance summary (7-day metrics vs equipment-class averages, with explicit
# numeric deltas), sends that text to ai_classify, and persists the result to
# sbr_iot_demo.fleet.ai_triage via INSERT OVERWRITE — the table identity is
# preserved so its CDF feed and Lakebase synced table stay valid across runs.
#
# Sources (read-only): gold_machine_status, gold_health_score, gold_daily_agg,
# silver_telemetry (for the 7-day anchor). Nothing else is modified.
#
# Machines with no telemetry in the 7-day window (the gold_health_score window)
# are written with performance_tier = 'NO_DATA' and do not trigger an ai_classify call.

CATALOG = "sbr_iot_demo"
SCHEMA = "fleet"
TARGET = f"{CATALOG}.{SCHEMA}.ai_triage"

# Sync-safe write: the table is created once (IF NOT EXISTS) and every run
# INSERT OVERWRITEs all rows, keeping the Delta table identity stable.
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TARGET} (
  equipment_id STRING,
  equipment_class STRING,
  running_ratio_7d DOUBLE,
  class_avg_running_ratio_7d DOUBLE,
  running_ratio_delta DOUBLE,
  fuel_anomalies_7d DOUBLE,
  class_avg_fuel_anomalies_7d DOUBLE,
  fuel_anomalies_delta DOUBLE,
  min_battery_running_7d DOUBLE,
  class_avg_min_battery_running_7d DOUBLE,
  min_battery_delta DOUBLE,
  engine_hours_latest DOUBLE,
  class_avg_engine_hours DOUBLE,
  engine_hours_delta DOUBLE,
  fuel_level_pct DOUBLE,
  class_avg_fuel_level_pct DOUBLE,
  fuel_level_delta DOUBLE,
  battery_voltage DOUBLE,
  class_avg_battery_voltage DOUBLE,
  battery_delta DOUBLE,
  fault_code_count DOUBLE,
  class_avg_fault_code_count DOUBLE,
  fault_code_delta DOUBLE,
  fault_codes STRING,
  performance_summary STRING,
  performance_tier STRING,
  model_name STRING,
  classified_at TIMESTAMP
) USING DELTA
""")

ai_triage_sql = r"""
INSERT OVERWRITE sbr_iot_demo.fleet.ai_triage
WITH anchor AS (
  SELECT MAX(snapshot_ts) AS now_ts FROM sbr_iot_demo.fleet.silver_telemetry
),
class_util AS (
  SELECT d.equipment_class, AVG(d.utilization_pct) AS class_avg_running_ratio_7d
  FROM sbr_iot_demo.fleet.gold_daily_agg d CROSS JOIN anchor a
  WHERE d.day >= CAST(a.now_ts - INTERVAL 7 DAYS AS DATE)
  GROUP BY d.equipment_class
),
class_health AS (
  SELECT equipment_class,
         AVG(fuel_anomalies_7d) AS class_avg_fuel_anomalies_7d,
         AVG(min_battery_running_7d) AS class_avg_min_battery_running_7d,
         AVG(engine_hours_latest) AS class_avg_engine_hours
  FROM sbr_iot_demo.fleet.gold_health_score
  GROUP BY equipment_class
),
class_latest AS (
  SELECT equipment_class,
         AVG(fuel_level_pct) AS class_avg_fuel_level_pct,
         AVG(battery_voltage) AS class_avg_battery_voltage,
         AVG(CASE WHEN fault_codes IS NULL THEN 0 ELSE size(fault_codes) END) AS class_avg_fault_code_count
  FROM sbr_iot_demo.fleet.gold_machine_status
  GROUP BY equipment_class
),
machines AS (
  SELECT m.equipment_id, m.equipment_class, m.snapshot_ts AS latest_snapshot_ts,
         m.fuel_level_pct, m.battery_voltage,
         CASE WHEN m.fault_codes IS NULL THEN 0 ELSE size(m.fault_codes) END AS fault_code_count,
         CASE WHEN m.fault_codes IS NULL OR size(m.fault_codes) = 0 THEN 'none' ELSE concat_ws(',', m.fault_codes) END AS fault_codes
  FROM sbr_iot_demo.fleet.gold_machine_status m
),
joined AS (
  SELECT m.equipment_id, m.equipment_class, m.latest_snapshot_ts,
         CAST(h.running_ratio_7d AS DOUBLE) AS running_ratio_7d, CAST(cu.class_avg_running_ratio_7d AS DOUBLE) AS class_avg_running_ratio_7d,
         CAST(h.fuel_anomalies_7d AS DOUBLE) AS fuel_anomalies_7d, CAST(ch.class_avg_fuel_anomalies_7d AS DOUBLE) AS class_avg_fuel_anomalies_7d,
         CAST(h.min_battery_running_7d AS DOUBLE) AS min_battery_running_7d, CAST(ch.class_avg_min_battery_running_7d AS DOUBLE) AS class_avg_min_battery_running_7d,
         CAST(h.engine_hours_latest AS DOUBLE) AS engine_hours_latest, CAST(ch.class_avg_engine_hours AS DOUBLE) AS class_avg_engine_hours,
         CAST(m.fuel_level_pct AS DOUBLE) AS fuel_level_pct, CAST(cl.class_avg_fuel_level_pct AS DOUBLE) AS class_avg_fuel_level_pct,
         CAST(m.battery_voltage AS DOUBLE) AS battery_voltage, CAST(cl.class_avg_battery_voltage AS DOUBLE) AS class_avg_battery_voltage,
         CAST(m.fault_code_count AS DOUBLE) AS fault_code_count, CAST(cl.class_avg_fault_code_count AS DOUBLE) AS class_avg_fault_code_count, m.fault_codes
  FROM machines m
  LEFT JOIN sbr_iot_demo.fleet.gold_health_score h ON h.equipment_id = m.equipment_id
  LEFT JOIN class_util cu ON cu.equipment_class = m.equipment_class
  LEFT JOIN class_health ch ON ch.equipment_class = m.equipment_class
  LEFT JOIN class_latest cl ON cl.equipment_class = m.equipment_class
),
scored AS (
  SELECT j.*,
         ROUND(running_ratio_7d - class_avg_running_ratio_7d, 3) AS running_ratio_delta,
         ROUND(fuel_anomalies_7d - class_avg_fuel_anomalies_7d, 2) AS fuel_anomalies_delta,
         ROUND(min_battery_running_7d - class_avg_min_battery_running_7d, 2) AS min_battery_delta,
         ROUND(engine_hours_latest - class_avg_engine_hours, 1) AS engine_hours_delta,
         ROUND(fuel_level_pct - class_avg_fuel_level_pct, 1) AS fuel_level_delta,
         ROUND(battery_voltage - class_avg_battery_voltage, 2) AS battery_delta,
         ROUND(fault_code_count - class_avg_fault_code_count, 2) AS fault_code_delta
  FROM joined j
),
prompted AS (
  SELECT s.*,
    CASE WHEN running_ratio_7d IS NULL THEN
      concat('Equipment ', equipment_id, ' (class: ', equipment_class, ') reported no telemetry in the last 7 days (last snapshot ', CAST(latest_snapshot_ts AS STRING), '). No 7-day comparison with the class average is possible.')
    ELSE
      concat_ws('\n',
        concat('Classify the 7-day operating performance of equipment ', equipment_id, ' (class: ', equipment_class, ') relative to the average of its own equipment class. Answer with one label: BELOW_AVERAGE, AT_AVERAGE or ABOVE_AVERAGE.'),
        'Direction: a higher running ratio, higher minimum battery voltage and higher fuel level are better. More fuel anomalies, more active fault codes and higher engine hours are worse.',
        format_string('Running ratio (7d): %.3f vs class average %.3f (delta %+.3f).', running_ratio_7d, class_avg_running_ratio_7d, running_ratio_delta),
        format_string('Fuel anomalies (7d): %.0f vs class average %.2f (delta %+.2f).', fuel_anomalies_7d, class_avg_fuel_anomalies_7d, fuel_anomalies_delta),
        format_string('Minimum battery voltage while running (7d): %.2f V vs class average %.2f V (delta %+.2f V).', min_battery_running_7d, class_avg_min_battery_running_7d, min_battery_delta),
        format_string('Engine hours (latest): %.1f vs class average %.1f (delta %+.1f).', engine_hours_latest, class_avg_engine_hours, engine_hours_delta),
        format_string('Fuel level (latest): %.1f%% vs class average %.1f%% (delta %+.1f points).', fuel_level_pct, class_avg_fuel_level_pct, fuel_level_delta),
        format_string('Battery voltage (latest): %.2f V vs class average %.2f V (delta %+.2f V).', battery_voltage, class_avg_battery_voltage, battery_delta),
        format_string('Active fault codes (latest): %s (count %.0f) vs class average count %.2f (delta %+.2f).', fault_codes, fault_code_count, class_avg_fault_code_count, fault_code_delta)
      )
    END AS performance_summary
  FROM scored s
)
SELECT p.equipment_id, p.equipment_class,
       p.running_ratio_7d, p.class_avg_running_ratio_7d, p.running_ratio_delta,
       p.fuel_anomalies_7d, p.class_avg_fuel_anomalies_7d, p.fuel_anomalies_delta,
       p.min_battery_running_7d, p.class_avg_min_battery_running_7d, p.min_battery_delta,
       p.engine_hours_latest, p.class_avg_engine_hours, p.engine_hours_delta,
       p.fuel_level_pct, p.class_avg_fuel_level_pct, p.fuel_level_delta,
       p.battery_voltage, p.class_avg_battery_voltage, p.battery_delta,
       p.fault_code_count, p.class_avg_fault_code_count, p.fault_code_delta, p.fault_codes,
       p.performance_summary,
       CASE WHEN p.running_ratio_7d IS NULL THEN 'NO_DATA'
            ELSE ai_classify(p.performance_summary, array('BELOW_AVERAGE','AT_AVERAGE','ABOVE_AVERAGE')) END AS performance_tier,
       CASE WHEN p.running_ratio_7d IS NULL THEN NULL ELSE 'ai_classify (Databricks-hosted default)' END AS model_name,
       current_timestamp() AS classified_at
FROM prompted p

"""

spark.sql(ai_triage_sql)

# COMMAND ----------

# Sanity checks on the persisted result (read-only).
summary = spark.sql(f"""
    SELECT performance_tier, COUNT(*) AS machines
    FROM {TARGET}
    GROUP BY performance_tier
    ORDER BY performance_tier
""")
summary.show()

rows = spark.sql(f"SELECT COUNT(*) AS n, COUNT(DISTINCT equipment_id) AS d FROM {TARGET}").collect()[0]
print(f"ai_triage rows={rows['n']} distinct_equipment={rows['d']}")
