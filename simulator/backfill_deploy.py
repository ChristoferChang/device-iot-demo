"""Deterministic equipment-rental fleet telemetry simulator.

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


# Charlotte NC metro + South Carolina yard locations (12 rental yards)
YARDS = [
    (35.227, -80.843),  # Charlotte NC
    (35.409, -80.581),  # Concord NC
    (35.411, -80.856),  # Huntersville NC
    (35.262, -81.187),  # Gastonia NC
    (34.985, -80.549),  # Monroe NC
    (34.925, -81.025),  # Rock Hill SC
    (34.000, -81.035),  # Columbia SC
    (34.853, -82.394),  # Greenville SC
    (34.950, -81.932),  # Spartanburg SC
    (32.776, -79.931),  # Charleston SC
    (33.690, -78.887),  # Myrtle Beach SC
    (34.198, -79.764),  # Florence SC
]


def build_fleet() -> list[Machine]:
    machines = []
    for equipment_class, (prefix, count) in CLASSES.items():
        for i in range(1, count + 1):
            h = float(int(hashlib.sha256(f"{prefix}-{i:04d}".encode()).hexdigest()[:12], 16))
            h_int = int(h)
            yard_lat, yard_lon = YARDS[h_int % len(YARDS)]
            # Hash-based fixed offset ±0.02 deg so machines cluster tightly around their yard
            lat_offset = ((h_int >> 6) % 401 - 200) / 10000.0
            lon_offset = ((h_int >> 15) % 401 - 200) / 10000.0
            machines.append(Machine(
                equipment_id=f"{prefix}-{i:04d}",
                equipment_class=equipment_class,
                seed=(h % 1_000_000) / 1_000_000,
                lat=yard_lat + lat_offset,
                lon=yard_lon + lon_offset,
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


# ---- job body (auto-concatenated from fleet_sim.py at build time) ----
"""Backfill historical telemetry into bronze via Spark (run as a Databricks serverless job).

Generates the full history from REF_DATE to a target end time, chunked by day,
writing each chunk with append. Deterministic: a backfill and later live ticks
produce identical rows for identical ticks.
"""

import sys
from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession
from pyspark.sql import types as T


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
