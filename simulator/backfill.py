"""Backfill historical telemetry into bronze via Spark (run as a Databricks serverless job).

Generates the full history from REF_DATE to a target end time, chunked by day,
writing each chunk with append. Deterministic: a backfill and later live ticks
produce identical rows for identical ticks.
"""

import sys
from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession
from pyspark.sql import types as T

sys.path.insert(0, "/Workspace/Users/chris.chang@databricks.com/sbr_iot_demo")
from fleet_sim import build_fleet, reading, payload_raw  # noqa: E402

CATALOG = "sbr_iot_demo"
BRONZE = f"{CATALOG}.fleet.bronze_telemetry"

SCHEMA = T.StructType([
    T.StructField("equipment_id", T.StringType()),
    T.StructField("equipment_class", T.StringType()),
    T.StructField("snapshot_ts", T.TimestampType()),
    T.StructField("engine_running", T.BooleanType()),
    T.StructField("engine_hours", T.DoubleType()),
    T.StructField("fuel_level_pct", T.DoubleType()),
    T.StructField("battery_voltage", T.DoubleType()),
    T.StructField("coolant_temp_c", T.DoubleType()),
    T.StructField("latitude", T.DoubleType()),
    T.StructField("longitude", T.DoubleType()),
    T.StructField("speed_kph", T.DoubleType()),
    T.StructField("fault_codes", T.ArrayType(T.StringType())),
    T.StructField("payload_raw", T.StringType()),
    T.StructField("_ingest_timestamp", T.TimestampType()),
])


def day_rows(day_start: datetime, day_end: datetime, now: datetime):
    machines = build_fleet()
    ts = day_start
    while ts < day_end:
        if ts <= now:
            for m in machines:
                r = reading(m, ts)
                yield (m.equipment_id, m.equipment_class,
                       datetime.fromisoformat(r["snapshot_ts"]), r["engine_running"],
                       r["engine_hours"], r["fuel_level_pct"], r["battery_voltage"],
                       r["coolant_temp_c"], r["latitude"], r["longitude"], r["speed_kph"],
                       r["fault_codes"], payload_raw(r), now)
        ts += timedelta(minutes=5)


def main():
    now = datetime.now(timezone.utc)
    end = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)  # fleet_sim.REF_DATE

    spark = SparkSession.builder.getOrCreate()
    day = start
    while day < end:
        next_day = min(day + timedelta(days=1), end)
        rows = list(day_rows(day, next_day, now))
        df = spark.createDataFrame(rows, SCHEMA)
        (df.write.mode("append").saveAsTable(BRONZE))
        print(f"backfilled {day:%Y-%m-%d} -> {len(rows)} rows")
        day = next_day
    print(f"DONE: bronze now at {spark.table(BRONZE).count()} rows")


main()  # Databricks notebook/job entry — no __main__ guard
