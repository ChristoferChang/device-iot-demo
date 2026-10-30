# Migrating your IoT Platform to Databricks

*Signal to Action: equipment-rental IoT fleet-health proof of concept. FE Bar submission.*

Catch failing equipment before your renters do, at a cost that doesn't scale with your fleet.

> Figures are measured from Databricks system tables unless labeled **illustrative**. Demo fleet data is synthetic (300 machines).

---

## 1. Title

**Catch failing equipment before your renters do, at a cost that doesn't scale with your fleet.**

Speaker notes: Lead with the outcome. Two things to prove: the platform catches failures early, and its cost is driven by data, not device count. Everything below is either measured (cited) or labeled illustrative.

---

## 2. The customer problem

Every new machine adds cost on the legacy stack, and renters find the failures first.

- Telemetry from every machine (battery, fuel, GPS, hours) lands on an in-house platform: ingestion pipelines, streaming infrastructure, a message bus and serving replicas.
- Each of those layers **scales linearly with fleet size**, and every new machine class adds another pipeline to build, run and monitor.
- Insight stays buried in raw telemetry; yard managers and analysts cannot ask questions without an engineering queue.
- Maintenance is **reactive**: the renter discovers the failed unit before the rental company does.

*Qualitative pattern for an equipment-rental fleet on an in-place stack. Not a measured customer figure.*

Speaker notes: Frame this as the pattern, not as the customer's numbers. Ask the audience which of these layers they operate today.

---

## 3. The cost problem

On an in-place stack, cost follows the fleet. On Databricks, it follows the data.

- Per-device connection and pipeline costs grow with every machine.
- Clusters are sized for peak fleet load and run 24/7.
- Serving infrastructure is duplicated per application.
- Ops headcount rises with each new equipment class.

Databricks: ingest, process and serve run on serverless pipelines and Lakebase, so cost is driven by data volume, not device count.

**Cost model (illustrative, not customer actuals)**

| | Legacy in-place (illustrative) | Databricks (illustrative) |
|---|---|---|
| Cost driver | Device count, peak-sized clusters, headcount | Data volume and serverless compute per run |
| Cost per machine / month | Roughly flat, so total grows ~linearly | Falls as the fleet grows |
| Total platform cost at 10x fleet | ~10x | ~5.5x |

*Illustrative model. Total platform cost index, 1x = today's fleet. Legacy assumed flat per machine, so total is linear. Databricks assumes 50% fixed per-run overhead and 50% volume-driven (see slide 5).*

Speaker notes: This is the core slide. The legacy curve is an assumption about how in-place stacks scale, not a measured figure for the customer. Ask the customer for their current bill to replace the illustrative curve with actuals.

---

## 4. Measured proof point

The demo runs 300 machines, every 5 minutes, for about $103 a day at list price.

| Component (Databricks job or pipeline) | Runs (14 full days) | Succeeded | Avg run time | List cost / day |
|---|---:|---:|---:|---:|
| Live telemetry ingest (job 350422921403193) | 4,034 | 4,032 | 0.6 min | $20.20 |
| Lakebase serving refresh (job 882651434551167) | 4,033 | 4,032 | 0.5 min | $22.31 |
| SDP refresh, bronze to silver to gold (job 1039479508136923) | 4,032 | 4,032 | 2.6 min (p95 3.2) | $60.97 |
| **Total, three components** | | | | **$103.48** |

- **Measured:** $10.49 per machine per month = $103.48/day x 30.4 days / 300 machines (list price).
- **Derived:** two-job subtotal (ingest + serving refresh) is $42.51/day. Excludes discounts, and excludes Apps, SQL and Genie usage on the shared workspace, which cannot be isolated to this demo.

**Source:** query on `fevm-azure`, run 2026-10-30.
- Cost: `system.billing.usage` (filtered on `usage_metadata.job_id` for the two jobs and `usage_metadata.dlt_pipeline_id = 'b02360cc-15d8-4342-bc81-60c8570c26b2'` for the SDP refresh pipeline that job 1039479508136923 runs), joined to `system.billing.list_prices` on sku and price window. Usage date 2026-10-16 to 2026-10-29 (14 complete days).
- Runs and durations: `system.lakeflow.job_run_timeline`, `period_start_time` 2026-10-16 to 2026-10-29.

Speaker notes: All costs are list prices, before any negotiated discount. An earlier estimate of about $13.10/day for the two 5-minute jobs could not be reproduced. The query-backed figure for those two jobs is $42.51/day, so use the table above, not the earlier number. Shared workspace: SQL-warehouse and Apps usage cannot be tied to this demo, so the $103.48/day covers only the three pipelines above, not the full demo bill.

---

## 5. Scale projection

At 10x the fleet: about $31k a month in the worst case, about $17k in the illustrative sub-linear model.

| Scenario | Machines | Monthly cost (list) | Per machine / month | Basis |
|---|---:|---:|---:|---|
| Demo, as measured | 300 | $3,146 | $10.49 | Measured |
| 10x fleet, cost scales linearly (worst case) | 3,000 | $31,456 | $10.49 | Projection |
| 10x fleet, sub-linear (5.5x multiple) | 3,000 | $17,301 | $5.77 | **Illustrative model** |

**Assumptions (not measured at 3,000 machines)**
- Monthly = daily cost x 30.4.
- Worst case keeps the measured $/machine (every cost scales with the fleet).
- Illustrative sub-linear case assumes 50% of cost is fixed per-run overhead (scheduling, start-up) and 50% scales with telemetry volume: 0.5 + 0.5 x 10 = 5.5x.
- Run times at 10x are not measured and need a pilot check against the 5-minute cadence.
- Excludes Apps, Lakebase and GenAI costs, and any legacy comparison, which depend on the customer's actual bill.

Speaker notes: Present the worst case first, then the illustrative case. The split between fixed and volume-driven cost is an assumption; say so out loud.

---

## 6. Architecture

One governed platform carries the journey from telemetry to work order.

1. **Lakeflow ingest:** serverless ingest job every 5 min; SDP with DQ guardrails quarantines bad rows.
2. **Unity Catalog governance:** catalog, HITL procedures, metric views and grants on one platform.
3. **Lakebase serving:** continuous synced tables; the app reads operational data from Postgres.
4. **GenAI:** ai_classify triage flags units for review; Genie answers questions over gold.
5. **Fleet Copilot app:** human-in-the-loop; AI or people propose, a human approves.

*Diagram: `architecture.png`.*

Speaker notes: Walk left to right. Stress that the governed gold data is the single source for the app, Genie and the dashboard. Note that the diagram's step names may differ slightly from the function names used on slide 7 (propose_work_order in the diagram vs create_work_order in the Genie tool). Confirm the name before the live demo.

---

## 7. What makes it intelligent

AI finds and proposes. Governed data answers. A person decides.

- **Genie space over governed gold data:** natural-language answers with certified answers and cited sources, so yard managers query without SQL.
- **Work-order tool** (`create_work_order`): a Genie request can propose a work order, but it lands as pending approval, never as open.
- **AI-functions triage** (`ai_classify`): flags equipment running below the fleet average for review.
- **AI proposes; a human approves.** The model never opens a work order on its own.

*Status: the ai_classify triage table is in progress. Confirm it is populated before the live demo.*

Speaker notes: Be explicit that the triage is a flag for review, not an automatic action.

---

## 8. The human-in-the-loop loop

Every work order passes a human gate before anyone dispatches a truck.

1. **Propose:** AI or a person, from a telemetry alert, a triage flag or a Genie question. Row lands as PENDING_APPROVAL; proposer is audited.
2. **Pending:** shown in the Copilot queue. The unit leaves the at-risk list while an active order exists, so there are no duplicate orders.
3. **Approve:** only a human. Approving flips the order to OPEN; the approver is audited.
4. **Dispatch:** the fix is dispatched; telemetry shows recovery, which closes the loop.

**Demo beat:** pick an at-risk unit on the map, ask Genie which units need service this week, propose a work order, approve it, and watch the status flip to OPEN.

Speaker notes: This is the trust slide. Repeat that the AI cannot perform the approve step.

---

## 9. Buyer KPIs

What we measured on the demo, and what a pilot must prove.

- **48.3% fleet utilization, 7-day average (measured).** Source: `sbr_iot_demo.fleet.gold_daily_agg`, days 2026-10-24 to 2026-10-30, machine-weighted across the 4 equipment classes. Synthetic demo fleet, so this is a demo value.
- **$10.49 cost per machine per month (measured, list price).** See slide 4.
- **< 10 min telemetry to app (derived).** 5-minute cadence plus measured run times of 0.6, 0.5 and 2.6 min. Not timed end to end; confirm in the pilot.
- **Machine downtime avoided: illustrative target, not measured.** Set the baseline with the customer during the pilot. The "-10%" on the slide is a placeholder.

Speaker notes: Do not present the downtime figure as a result. The utilization number is from synthetic telemetry; say that before the customer does.

---

## 10. Value framing

For the executive sponsor: lower TCO. For the domain owner: less babysitting.

**Executive sponsor**
- **Lower TCO:** one platform in place of separate ingest, streaming, serving and ops stacks (illustrative; confirm the customer's current stack count).
- **Cost follows data volume**, not device count or headcount.
- **Governed from day one** with Unity Catalog grants and audit.

**Domain owner (fleet operations)**
- **No pipeline babysitting:** DQ guardrails quarantine bad rows with full accounting.
- **Governed metrics:** one definition of utilization, health and anomalies.
- **Natural-language access** for the yard team through Genie, with no SQL queue.

Speaker notes: Tailor the sponsor version to the customer's cost centers. Use the domain-owner version with the people who run the yards.

---

## 11. Demo and next steps

Try it live, then start a 30-day pilot on your own fleet data.

**Live demo, in this order**
1. **Fleet map:** risk-colored markers; click an at-risk unit.
2. **Genie chat:** ask a natural-language question and check the cited answer.
3. **Propose, then approve:** create a work order, approve it, and watch it go OPEN.

**30-day pilot (proposed)**
- **Week 1:** connect a telemetry sample; agree on KPIs and baselines.
- **Week 2:** ingest with DQ guardrails; governed metrics in Unity Catalog.
- **Week 3:** Copilot app and Genie for the yard team; propose and approve on real alerts.
- **Week 4:** measure utilization, downtime and cost per machine against baseline; decide on scale-out.

Speaker notes: Ask for the telemetry sample and the current cost bill in week 1. Those two inputs replace the illustrative model with the customer's actuals.
