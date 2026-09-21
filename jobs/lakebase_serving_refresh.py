# Databricks notebook source
# Refreshes Lakebase sync-source tables from the gold views on the same 5-min
# cadence as the SDP pipeline. Small tables are fully overwritten; the events
# table is append-only (it is 500k+ rows of history and the app only reads the
# latest page, so full rewrites would create excessive CDF churn for sync).

CATALOG = "sbr_iot_demo"
SCHEMA = "fleet"

prefix = f"{CATALOG}.{SCHEMA}"

for view, target in [
    ("gold_machine_status", "serving_gold_machine_status"),
    ("gold_health_score", "serving_gold_health_score"),
    ("gold_daily_agg", "serving_gold_daily_agg"),
]:
    spark.sql(
        f"INSERT OVERWRITE {prefix}.{target} SELECT * FROM {prefix}.{view}"
    )

# COMMAND ----------

max_ts_row = spark.sql(
    f"SELECT COALESCE(MAX(event_ts), TIMESTAMP '1970-01-01') AS max_ts FROM {prefix}.serving_gold_events"
).collect()[0]
max_ts = max_ts_row["max_ts"]

spark.sql(
    f"""
    INSERT INTO {prefix}.serving_gold_events
    SELECT * FROM {prefix}.gold_events WHERE event_ts > '{max_ts.isoformat()}'
    """
)

new_count = spark.sql(
    f"SELECT COUNT(*) AS c FROM {prefix}.serving_gold_events"
).collect()[0]["c"]
print(f"serving tables refreshed; serving_gold_events now {new_count} rows")
