"""Deterministic Sunbelt-style fleet telemetry simulator.

Readings are a pure function of (machine, tick_ts): same inputs -> same rows.
All tick timestamps are aligned to 5-minute boundaries so retried/backfilled
runs emit identical rows (duplicates are dropped downstream at silver).

Narratives (fixed machine IDs, deterministic onset times relative to ref date):
- GEN-0142: battery voltage decays over 21 days, crosses 12.0V threshold.
- EXC-0007: fuel anomaly — level drops abnormally fast mid-day (theft/leak pattern).
- LFT-0031: under-utilized — engine_running ~0 despite being "on rent".
- CMP-0005: maintenance-due — engine_hours crosses 500h service threshold.
"""

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TICK_MINUTES = 5
CLASSES = {
    "generator": ("GEN", 75),
    "aerial_lift": ("LFT", 75),
    "excavator": ("EXC", 75),
    "compressor": ("CMP", 75),
}
REF_DATE = datetime(2026, 9, 1, tzinfo=timezone.utc)  # fleet "birth"; all trajectories run from here

NARRATIVE_BATTERY_UNIT = "GEN-0042"
NARRATIVE_FUEL_UNIT = "EXC-0007"
NARRATIVE_IDLE_UNIT = "LFT-0031"
NARRATIVE_SERVICE_UNIT = "CMP-0005"


def align_tick(ts: datetime) -> datetime:
    minutes = (ts.minute // TICK_MINUTES) * TICK_MINUTES
    return ts.replace(minute=minutes, second=0, microsecond=0)


@dataclass(frozen=True)
class Machine:
    equipment_id: str
    equipment_class: str
    seed: float
    lat: float
    lon: float
    tank_size_l: float
    duty_cycle_amp: float   # how "busy" the machine is 0..1
    duty_phase: float       # offset of daily activity pattern


def build_fleet() -> list[Machine]:
    machines = []
    for equipment_class, (prefix, count) in CLASSES.items():
        for i in range(1, count + 1):
            h = float(int(hashlib.sha256(f"{prefix}-{i:04d}".encode()).hexdigest()[:12], 16))
            machines.append(Machine(
                equipment_id=f"{prefix}-{i:04d}",
                equipment_class=equipment_class,
                seed=(h % 1_000_000) / 1_000_000,
                lat=33.0 + (h % 900) / 900 * 4.0,          # scatter around AZ/Sunbelt south region
                lon=-113.5 + (h % 1300) / 1300 * 5.0,
                tank_size_l=200 + (h % 300),
                duty_cycle_amp=0.35 + (h % 100) / 100 * 0.5,
                duty_phase=(h % 628) / 100,
            ))
    return machines


def _rng(machine: Machine, tick_iso: str) -> random.Random:
    return random.Random(f"{machine.seed}:{tick_iso}")


def _utilization(machine: Machine, ts: datetime) -> float:
    """Daily activity pattern 0..1, deterministic in wall-clock time."""
    hour = ts.hour + ts.minute / 60.0
    daily = 0.5 + 0.5 * math.sin((hour / 24) * 2 * math.pi + machine.duty_phase)
    weekend_dip = 0.4 if ts.weekday() >= 5 else 1.0
    return max(0.0, min(1.0, daily * machine.duty_cycle_amp * weekend_dip))


def reading(machine: Machine, ts: datetime) -> dict:
    """One telemetry row. Pure function of (machine, aligned ts)."""
    ts = align_tick(ts)
    rng = _rng(machine, ts.isoformat())
    days_since_ref = (ts - REF_DATE).total_seconds() / 86400.0

    util = _utilization(machine, ts)
    running = util > 0.15 and rng.random() < 0.85
    if machine.equipment_id == NARRATIVE_IDLE_UNIT:
        running = rng.random() < 0.02  # on rent but sitting idle — under-utilization narrative

    # Battery: healthy machines wobble around 12.6-14.2V while running.
    battery = 12.4 + rng.uniform(-0.15, 1.6) if running else 12.1 + rng.uniform(-0.3, 0.3)
    if machine.equipment_id == NARRATIVE_BATTERY_UNIT:
        # Linear decay 13.8V -> 11.4V across 21 days from ref date.
        battery = 13.8 - (days_since_ref / 21.0) * 2.4 + rng.uniform(-0.05, 0.05)

    # Fuel: drains with utilization, refills on scripted service events (every ~6 days).
    cycle_pos = (days_since_ref % 6.0) / 6.0
    fuel = max(5.0, 100.0 * (1 - cycle_pos) * (1 - 0.4 * util) + rng.uniform(-2, 2))
    if machine.equipment_id == NARRATIVE_FUEL_UNIT and 12 <= ts.hour <= 14 and ts.weekday() == 2:
        fuel = max(3.0, fuel - 45.0)  # abnormal mid-week midday drop

    # Engine hours: accrue with utilization (~0.15h per tick when running).
    engine_hours = days_since_ref * 24 * 0.35 * machine.duty_cycle_amp + rng.uniform(0, 2)
    if machine.equipment_id == NARRATIVE_SERVICE_UNIT:
        engine_hours += 430.0  # crosses the 500h service threshold ~Sep 15-16

    faults = []
    if machine.equipment_id == NARRATIVE_BATTERY_UNIT and battery < 12.2:
        faults.append("P0562")  # system voltage low
    if machine.equipment_id == NARRATIVE_SERVICE_UNIT and engine_hours > 500:
        faults.append("SVC_DUE")
    if running and rng.random() < 0.01:
        faults.append(rng.choice(["P0128", "P0401", "U0100"]))

    return {
        "equipment_id": machine.equipment_id,
        "equipment_class": machine.equipment_class,
        "snapshot_ts": ts.isoformat(),
        "engine_running": running,
        "engine_hours": round(engine_hours, 2),
        "fuel_level_pct": round(fuel, 1),
        "battery_voltage": round(battery, 2),
        "coolant_temp_c": round(72 + (18 * util if running else 0) + rng.uniform(-3, 3), 1),
        "latitude": round(machine.lat + rng.uniform(-0.001, 0.001), 5),
        "longitude": round(machine.lon + rng.uniform(-0.001, 0.001), 5),
        "speed_kph": round(rng.uniform(0, 6) * util, 1),
        "fault_codes": faults,
    }


def payload_raw(row: dict) -> str:
    """Simulated OEM envelope — slightly messy, like a real vendor payload."""
    import json
    return json.dumps({"v": 2, "ts": row["snapshot_ts"], "device": row["equipment_id"],
                       "data": {k: v for k, v in row.items()
                                if k not in ("equipment_id", "snapshot_ts")}},
                      separators=(",", ":"))


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
