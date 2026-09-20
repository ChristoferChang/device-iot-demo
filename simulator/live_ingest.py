"""Live telemetry tick — pushes one aligned 5-min tick per machine via ZeroBus.

Run as a recurring Databricks job every 5 minutes. Reads nothing; computes the
current tick deterministically and pushes. Retries are safe: silver dedupes on
(equipment_id, snapshot_ts).

ZeroBus credentials (table-scoped OAuth) are passed via job parameters /
environment: ZEROBUS_CLIENT_ID, ZEROBUS_CLIENT_SECRET, ZEROBUS_ENDPOINT.
If credentials are absent the script falls back to a direct Delta append so the
demo pipeline never hard-stops on the ZeroBus spike.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/Workspace")
from fleet_sim import build_fleet, reading, payload_raw  # noqa: E402

CATALOG = "sbr_iot_demo"
BRONZE = f"{CATALOG}.fleet.bronze_telemetry"


def current_tick() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)


def push_zerobus(rows: list[dict]) -> bool:
    client_id = os.environ.get("ZEROBUS_CLIENT_ID")
    client_secret = os.environ.get("ZEROBUS_CLIENT_SECRET")
    endpoint = os.environ.get("ZEROBUS_ENDPOINT")
    if not (client_id and client_secret and endpoint):
        return False
    # zerobus-ingest-sdk: gRPC push, serverless, table-scoped token.
    from databricks_zerobus_ingest_sdk import ZerobusSdk, TableProperties  # type: ignore

    sdk = ZerobusSdk(endpoint, os.environ["DATABRICKS_HOST"])
    table_props = TableProperties(f"{BRONZE}", "equipment_id STRING, ...")  # full schema at wiring time
    stream = sdk.ingest(table_props, client_id, client_secret)
    for r in rows:
        stream.ingest_record(payload_raw(r))
    stream.close()
    return True


def fallback_append(rows: list[dict]):
    """Direct Delta append (fallback when ZeroBus creds aren't provisioned)."""
    from pyspark.sql import SparkSession
    from pyspark.sql import types as T

    # Serverless/Spark Connect chokes on list-of-dicts — tuples in schema order only.
    schema = T.StructType([
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
    now = datetime.now(timezone.utc)
    tuples = [
        (r["equipment_id"], r["equipment_class"], datetime.fromisoformat(r["snapshot_ts"]),
         r["engine_running"], r["engine_hours"], r["fuel_level_pct"], r["battery_voltage"],
         r["coolant_temp_c"], r["latitude"], r["longitude"], r["speed_kph"],
         r["fault_codes"], r["payload_raw"], now)
        for r in rows
    ]
    spark = SparkSession.builder.getOrCreate()
    spark.createDataFrame(tuples, schema).write.mode("append").saveAsTable(BRONZE)


def main():
    tick = current_tick()
    now = datetime.now(timezone.utc)
    rows = []
    for m in build_fleet():
        r = reading(m, tick)
        r["payload_raw"] = payload_raw(r)
        rows.append(r)
    if not push_zerobus(rows):
        fallback_append(rows)
    print(f"tick {tick.isoformat()}: pushed {len(rows)} rows")


main()  # Databricks notebook/job entry — no __main__ guard
