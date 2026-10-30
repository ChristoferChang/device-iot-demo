# Genie generated-SQL transcript

Live questions asked of the demo Genie space over the governed gold views.
For each question: Genie's answer, the SQL it generated, and a sample of the rows returned.
Captured 2026-10-30 18:01 UTC on fevm-azure, space `01f1b456af5d124aacf95d5f5d8e3636`,
via the Genie Conversation API (`genai/capture_genie_sql.py`).

## Q: Which machines have the highest health risk score and what is driving their risk?

conversation_id `01f1d48beae91a599af7ca54727f8cde` · message_id `01f1d48beb021e87bb30fcd07b40b7d4` · status **COMPLETED**

**Genie's answer:**

> The highest health risk score is **20**, shared by **CMP-0005** and **EXC-0007**. For **CMP-0005**, the visible drivers are **702.7 engine hours** and a **12.25V** minimum running battery reading; for **EXC-0007**, the visible drivers are **1 fuel anomaly**, a **12.25V** minimum running battery reading, and **353.2 engine hours**. Across these top-risk machines, the common pattern is the same low-end battery reading, while one also shows very high engine hours and the other shows a fuel issue.

**Generated SQL (executed against the governed views):**

```sql
WITH ranked AS (
  SELECT
    `equipment_id`,
    `equipment_class`,
    `health_risk_score`,
    `min_battery_running_7d`,
    `engine_hours_latest`,
    `running_ratio_7d`,
    `fuel_anomalies_7d`,
    RANK() OVER (ORDER BY `health_risk_score` DESC) AS `risk_rank`
  FROM `sbr_iot_demo`.`fleet`.`gold_health_score`
  WHERE `health_risk_score` IS NOT NULL
    AND `equipment_id` IS NOT NULL
)
SELECT
  `equipment_id`,
  `equipment_class`,
  `health_risk_score`,
  `min_battery_running_7d`,
  `engine_hours_latest`,
  `running_ratio_7d`,
  `fuel_anomalies_7d`
FROM ranked
WHERE `risk_rank` = 1
ORDER BY `equipment_id`
```

**Rows returned: 2** — sample:

| equipment_id | equipment_class | health_risk_score | min_battery_running_7d | engine_hours_latest |
|---|---|---|---|---|
| CMP-0005 | compressor | 20 | 12.25 | 702.7 |
| EXC-0007 | excavator | 20 | 12.25 | 353.2 |

## Q: Show the fleet utilization trend by equipment class over the last 7 days.

conversation_id `01f1d48bf4fb1e7f9952da502df9e46e` · message_id `01f1d48bf50d151aa0c5d08e3968843f` · status **COMPLETED**

**Genie's answer:**

> Over the last **7 days** (2026-10-24 to 2026-10-30), utilization rose sharply across all equipment classes after 2026-10-25, moving from about **29.5%–31.9%** on 2026-10-24/25 to roughly **54.3%–57.2%** from 2026-10-26 onward. Across the full period, **compressors** were generally the highest-utilized class, while **aerial lifts** were usually the lowest; reporting volume was steady at **75 machines** for aerial lifts, compressors, and excavators, and **74** for generators.
> 
> Examples include:
> - **2026-10-24:** aerial lift **29.52%**, compressor **31.84%**, excavator **29.62%**, generator **31.37%**
> - **2026-10-26:** aerial lift **54.86%**, compressor **55.82%**, excavator **55.12%**, generator **55.55%**
> - **2026-10-28:** aerial lift **54.84%**, compressor **55.93%**, excavator **55.60%**, generator **55.34%**
> - **2026-10-29:** aerial lift **54.27%**, compressor **55.69%**, excavator **55.15%**, generator **55.49%**
> - **2026-10-30:** aerial lift **54.39%**, compressor **55.91%**, excavator **53.67%**, generator **57.17%**

**Generated SQL (executed against the governed views):**

```sql
SELECT `day`, `equipment_class`, `utilization_pct`, `machines_reporting`
FROM `sbr_iot_demo`.`fleet`.`gold_daily_agg`
WHERE `day` BETWEEN date_sub(current_date, 6) AND current_date
  AND `day` IS NOT NULL
  AND `equipment_class` IS NOT NULL
ORDER BY `day`, `equipment_class`
```

**Rows returned: 28** — sample:

| day | equipment_class | utilization_pct | machines_reporting |
|---|---|---|---|
| 2026-10-24 | aerial_lift | 0.2952 | 75 |
| 2026-10-24 | compressor | 0.3184 | 75 |
| 2026-10-24 | excavator | 0.2962 | 75 |
| 2026-10-24 | generator | 0.3137 | 74 |
| 2026-10-25 | aerial_lift | 0.2959 | 75 |

## Q: List machines with active fault codes and show their fault codes.

conversation_id `01f1d48bff0711998a6b66904fb534dc` · message_id `01f1d48bff1518a69f44573bd8154f52` · status **COMPLETED**

**Genie's answer:**

> There are **2 machines** with active fault codes in the latest status data: **CMP-0005** at **2026-10-30 17:55:00 UTC** with fault code **SVC_DUE**, and **GEN-0042** at **2026-10-22 04:10:00 UTC** with fault code **P0562**. In this result, the **most recent** active fault is on **CMP-0005**, while **GEN-0042** is the older active-fault record.

**Generated SQL (executed against the governed views):**

```sql
WITH latest_status AS (
  SELECT
    gold_machine_status.equipment_id,
    gold_machine_status.equipment_class,
    gold_machine_status.snapshot_ts,
    gold_machine_status.fault_codes,
    ROW_NUMBER() OVER (
      PARTITION BY gold_machine_status.equipment_id
      ORDER BY gold_machine_status.snapshot_ts DESC
    ) AS rn
  FROM sbr_iot_demo.fleet.gold_machine_status
  WHERE gold_machine_status.equipment_id IS NOT NULL
    AND gold_machine_status.snapshot_ts IS NOT NULL
)
SELECT
  latest_status.equipment_id,
  latest_status.equipment_class,
  latest_status.snapshot_ts,
  latest_status.fault_codes
FROM latest_status
WHERE latest_status.rn = 1
  AND latest_status.fault_codes IS NOT NULL
  AND size(latest_status.fault_codes) > 0
ORDER BY latest_status.snapshot_ts DESC, latest_status.equipment_id
```

**Rows returned: 2** — sample:

| equipment_id | equipment_class | snapshot_ts | fault_codes |
|---|---|---|---|
| CMP-0005 | compressor | 2026-10-30T17:55:00.000Z | ["SVC_DUE"] |
| GEN-0042 | generator | 2026-10-22T04:10:00.000Z | ["P0562"] |
