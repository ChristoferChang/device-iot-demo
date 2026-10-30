# ai_triage run log

Feature: GenAI performance triage for the equipment-rental IoT fleet — two foundation-model
calls per machine via Databricks AI Functions run in SQL: `ai_classify` (BELOW_AVERAGE /
AT_AVERAGE / ABOVE_AVERAGE tier) and `ai_gen` (a concise maintenance `recommended_action`
written from the same telemetry-vs-class-average comparison).
Output table: `sbr_iot_demo.fleet.ai_triage` (NEW table; no existing table, view, job or pipeline was modified).
Workspace: fevm-azure (`adb-7405615395376229.9.azuredatabricks.net`). Warehouse `d0163299fb00cd64` (validation queries only).

## Run 3 — current notebook version (ai_classify + ai_gen recommended actions)

Adds the `recommended_action` column, generated per machine by `ai_gen` from the
telemetry-vs-class-average summary (max 25 words, imperative, no preamble). The
column was added to the live table with `ALTER TABLE ... ADD COLUMN` (identity and
CDF preserved); the Lakebase synced table evolved the schema automatically.

| Item | Value |
|---|---|
| Job name | `sbr_iot_demo_ai_triage` |
| Job ID | `1062733724985487` |
| Run ID | `101147775045264` |
| Run start (UTC) | 2026-10-30 17:18:16 |
| Run finish (UTC) | 2026-10-30 17:21:58 |
| Duration | ~222 s |
| Result | `TERMINATED` / `SUCCESS` |
| Lakebase sync after run | `fleet.ai_triage` in Postgres includes `recommended_action`, populated |

Tier distribution this run:

| Tier | Machines |
|---|---:|
| BELOW_AVERAGE | 162 |
| AT_AVERAGE | 69 |
| ABOVE_AVERAGE | 68 |
| NO_DATA | 1 (GEN-0042) |

Sample model-written recommended actions (BELOW_AVERAGE machines):

| Equipment | Recommended action (verbatim from `ai_gen`) |
|---|---|
| CMP-0005 | Inspect and address SVC_DUE fault code on CMP-0005. |
| CMP-0012 | Check battery and charging system on CMP-0012. |
| CMP-0018 | Check and address low running ratio on CMP-0018. |
| CMP-0020 | Inspect CMP-0020's electrical system and battery. |

The app's AI Analysis column displays these model-written actions; the deterministic
delta-based suggestion remains as a fallback when the model returns nothing.

## Run 2 — INSERT OVERWRITE notebook, post Lakebase sync

The notebook was changed from `CREATE OR REPLACE TABLE ... AS SELECT` to
`CREATE TABLE IF NOT EXISTS` + `INSERT OVERWRITE` so the Delta table identity — and
therefore its CDF feed and the Lakebase synced table — survive every run. This run
proves the committed notebook version executes cleanly and keeps the sync intact.

| Item | Value |
|---|---|
| Job name | `sbr_iot_demo_ai_triage` |
| Job ID | `1062733724985487` |
| Run ID | `470403615524291` |
| Task | `ai_triage` (notebook_task, serverless `environment_version` 2) |
| Run start (UTC) | 2026-10-30 16:25 |
| Run finish (UTC) | 2026-10-30 16:28 |
| Duration | ~175 s |
| Result | `TERMINATED` / `SUCCESS` |
| `classified_at` written | 2026-10-30T16:28:30 (all 300 rows) |
| Lakebase sync after run | `fleet.ai_triage` in Postgres: 300 rows, `MAX(classified_at)` = 16:28:30 — sync survived the overwrite unchanged |

Tier distribution this run (live telemetry, ai_classify is nondeterministic):

| Tier | Machines |
|---|---:|
| BELOW_AVERAGE | 151 |
| AT_AVERAGE | 69 |
| ABOVE_AVERAGE | 79 |
| NO_DATA | 1 (GEN-0042 — last telemetry 2026-10-22, outside the 7-day window) |

## Run 1 — original notebook version (CREATE OR REPLACE), initial build

## Rows

- Rows written to `sbr_iot_demo.fleet.ai_triage`: **300** (300 distinct `equipment_id`).
- Machines universe: `gold_machine_status` (300 machines).
- Rows with a 7-day telemetry window (`gold_health_score`): 299. Each of these went through `ai_classify`.
- Rows without a 7-day window: 1 (`GEN-0042`), written as `performance_tier = 'NO_DATA'`, not sent to `ai_classify`.

## Label distribution (persisted run)

Query: `SELECT performance_tier, COUNT(*) FROM sbr_iot_demo.fleet.ai_triage GROUP BY performance_tier`

| performance_tier | machines | share |
|---|---|---|
| BELOW_AVERAGE | 153 | 51.0% |
| AT_AVERAGE | 74 | 24.7% |
| ABOVE_AVERAGE | 72 | 24.0% |
| NO_DATA | 1 | 0.3% |
| **total** | **300** | |

Mean running-ratio delta vs class average by tier: BELOW -0.038, AT +0.016, ABOVE +0.024. The ordering is monotone, which is what we expect.

Validation pass (not persisted, a plain `SELECT` with the same logic on the warehouse, before the `fault_codes` empty-string fix, statement `01f1d470-6dfc-1885-99b3-1890c3925f85`) produced BELOW 144 / AT 77 / ABOVE 78 / NO_DATA 1. The difference from the job run shows `ai_classify` is nondeterministic across runs, and the live telemetry also moved between the two runs (see caveats).

## Cross-check: narrative units

| Unit | Class | running_ratio_7d (class avg) | Other deltas | Tier | Sensible? |
|---|---|---|---|---|---|
| LFT-0031 | aerial_lift | 0.026 (0.485), delta -0.459 | engine hours -91.9; battery -0.34 V | BELOW_AVERAGE | Yes. Idle-on-rent underutilizer, the strongest outlier in the fleet. |
| CMP-0005 | compressor | 0.478 (0.497), delta -0.019 | SVC_DUE active; engine hours +396.5; fault count +0.99 | BELOW_AVERAGE | Yes. Service-overdue, high-hours unit. Utilization is near average, so the tier is driven by the fault and hours deltas. |
| EXC-0007 | excavator | 0.536 (0.487), delta +0.049 | 1 fuel anomaly (+0.99 vs class 0.01); engine hours +57.6 | BELOW_AVERAGE | Partly. Utilization is above average, so the BELOW tier comes from the fuel-anomaly delta. That is a defensible reading, but it is a judgment call, not a utilization finding. |
| GEN-0042 | generator | not scored (no telemetry in the 7-day window) | latest snapshot battery 8.0 V vs class 12.56 V; active P0562 | NO_DATA | Not scored, by design. Its last telemetry is 2026-10-22 04:10 UTC, 8 days before the fleet anchor. The battery-decay signal is visible in the latest status but is outside the 7-day window the triage uses. This is a real gap for the demo narrative. See caveats. |

Other checks:
- Bottom 10 machines by running ratio: 8 BELOW_AVERAGE, 2 AT_AVERAGE. LFT-0031 (0.026) is the lowest, and the next-lowest are all at 0.32 to 0.34.
- Top 10 by running ratio: 6 ABOVE_AVERAGE, 2 AT_AVERAGE, 2 BELOW_AVERAGE.
- BELOW_AVERAGE machines with a negative running-ratio delta: 100 of 153. ABOVE_AVERAGE machines with a positive delta: 56 of 72.
- Machines with active fault codes in the job-time snapshot: CMP-0005 (SVC_DUE, BELOW_AVERAGE) and GEN-0042 (P0562, NO_DATA). The dry run also showed EXC-0049 (P0128, BELOW_AVERAGE), which had cleared by the job run.

## Sanity validation

- Label distribution is not degenerate: three tiers are populated, and BELOW is the largest group at 51%.
- Below-average machines are dominated by low running ratio: the lowest-utilization machines are almost all BELOW.
- Sensible outcome for the known underutilizer: LFT-0031 is BELOW_AVERAGE.
- Known gap: the one fault-coded unit with the clearest decay signal (GEN-0042) is not scored because it is outside the 7-day window.

## LLM call count and cost

- Persisted job run: 299 `ai_classify` calls (one per machine with a 7-day window; GEN-0042 excluded).
- Validation pass on the warehouse: another 299 calls (SELECT only, not persisted).
- Total for this work: about 598 `ai_classify` calls. Re-running the job makes another 299.

## Caveats

1. `ai_classify` is nondeterministic. The dry run and the job run gave different tier counts on the same prompt. Expect small shifts on re-runs.
2. The telemetry views are live. Between the dry run and the job, the fault state changed (EXC-0049 P0128 cleared). The table does not store the 7-day anchor timestamp, so an exact replay needs the Delta version of `silver_telemetry` at the time of the run. Recording the anchor in a future version would help.
3. The 7-day window used by `gold_health_score` excludes stale machines. GEN-0042 has been silent since 2026-10-22, so it is `NO_DATA`. A stale-unit rule (score on last-known state, or flag as offline) would be a reasonable next step.
4. The prompt gives no explicit tolerance band for AT_AVERAGE, so AT is narrow (about 25%). Adding a tolerance (for example plus or minus 0.02 running ratio) would make AT more meaningful.
5. `model_name` is a label. `ai_classify` does not expose the underlying model ID, so the column records `ai_classify (Databricks-hosted default)`.
6. The data has 4 equipment classes (aerial_lift, compressor, excavator, generator), 75 machines each, not 6 as stated in the brief.

## Exact code

Source of truth: `notebooks/ai_triage.py` in this repo. The SQL below is the exact statement the job executed (`spark.sql(ai_triage_sql)`):

```sql
CREATE OR REPLACE TABLE sbr_iot_demo.fleet.ai_triage AS
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
```

Verification queries (read-only, run after the job):
- `SELECT COUNT(*), COUNT(DISTINCT equipment_id), MIN(classified_at), MAX(classified_at) FROM sbr_iot_demo.fleet.ai_triage`
- `SELECT performance_tier, COUNT(*) FROM sbr_iot_demo.fleet.ai_triage GROUP BY performance_tier`
- Narrative-unit and sample rows: `SELECT ... FROM sbr_iot_demo.fleet.ai_triage WHERE equipment_id IN ('GEN-0042','EXC-0007','LFT-0031','CMP-0005')`
- Full table pull, statement `01f1d471-680b-1b24-bda5-9231ba450035` (300 rows), used to build `evidence/ai_triage_sample.csv`.
