# Changelog

Dates are UTC (commit timestamps). This history was reconstructed on
2026-10-30 by replaying the Claude Code session transcripts (every recorded
file write/edit) against the current tree — see Fidelity notes.

## 2026-10-30 — Submission prep
- Sync `app/requirements.txt` with the deployed app (adds `psycopg[binary]` for Lakebase)
- Add this CHANGELOG and repo hygiene (`.gitignore`)
- Sunbelt branding removed across repo, app, and workspace copies
- **AI Analysis in the app**: `ai_triage` synced into Lakebase (6th synced table, CDF),
  triage notebook switched to INSERT OVERWRITE (sync-safe) and scheduled daily 06:00 UTC;
  At-Risk Machines table now shows an AI Analysis column (tier + maintenance suggestion)
  and includes machines the AI flags below-average even when the rule-based score is 0
  (153 rows: 3 rule-based + 150 AI-only)
- **Explicit GenAI construct layer** added under `genai/`: `fleet_agent.py` (prompt
  constants + agent class retrieving governed fleet context and calling a Databricks
  foundation model through the OpenAI-compatible chat-completions endpoint, traced
  with MLflow to Unity Catalog `sbr_iot_demo.traces.fleet_agent_traces`) and
  `capture_genie_sql.py` (Genie Conversation API capture); run outputs committed to
  `evidence/fleet_agent_run.md` and `evidence/genie_sql_transcript.md` — the latter
  shows Genie's generated SQL over the governed views for three live questions with
  the returned rows
- Triage upgraded to two GenAI calls per machine: `ai_classify` tiers the machine and
  `ai_gen` writes a maintenance `recommended_action` from the same telemetry comparison;
  column synced to Lakebase (auto schema evolution), shown in the app's AI Analysis
  column, deterministic suggestion kept as fallback
- Postgres fix: the app SP's `SELECT` grant does not extend to tables created by the
  sync pipeline (default privileges only cover owner-created tables) — every new
  synced table needs an explicit `GRANT SELECT ON ALL TABLES IN SCHEMA fleet`; applied
  after `ai_triage` synced and the dashboard briefly 403'd

## 2026-10-06 — Lakebase migration (operational serving)
- New `jobs/lakebase_serving_refresh.py`: 5-minute job materializing gold views
  into CDF-enabled `serving_*` Delta tables (append-only for the 470k-row events table)
- Five continuous synced tables into Lakebase Postgres (`lakebase_demo_db.fleet`):
  `gold_machine_status`, `gold_health_score`, `gold_daily_agg`, `gold_events`, `work_orders`
- App read endpoints (`/api/dashboard`, `/api/fleet-map`, `/api/equipment`) moved to
  Postgres via psycopg with OAuth token refresh; propose/approve writes stay on Delta
- Lakebase resource attached to the app; SP granted SELECT on the Postgres `fleet` schema

## 2026-09-22 — HITL correctness + UX fixes
- At-Risk Machines table hides machines with an active (pending/open) work order
- Map markers stack by severity: critical > at-risk > healthy (legend filter still lifts group)
- Fleet Utilization Y-axis reverted to fixed 0–100%
- Full-width app header

## 2026-09-21 — Architecture page + polish
- New Architecture Diagram page (staggered swim lanes: IoT data → Lakeflow SDP →
  Serving → the human-in-the-loop action loop), linked from the app header
- Header branding, legend highlighting, layout and spacing polish

## 2026-09-20 — Fleet Copilot app + fleet relocation
- Fleet Copilot app (FastAPI + React): exec KPIs, utilization chart, at-risk table,
  work-order history, Genie chat panel, brand styling
- Genie chat hardening: async start/poll (Apps gateway 504 workaround),
  OBO-first auth with service-principal fallback
- Fleet relocated to 12 Charlotte NC/SC yards; GPS data-quality guardrail extended
- Fleet location map (MapLibre, risk-colored markers)
- Ingest deploy notebooks (live + backfill)

## 2026-09-19 — Initial build
- Synthetic fleet simulator (`simulator/fleet_sim.py`): 300 machines across 4
  equipment classes (75 each), deterministic per-tick telemetry, scripted
  narratives (battery decay, fuel anomaly, service-due, idle-on-rent)
- Lakeflow SDP pipeline: bronze → silver (dedupe + DQ guardrails) → gold
- Unity Catalog governance: HITL work-order procedures, metric views
- Fleet Copilot app scaffold + AI/BI dashboard

## Fidelity notes
- Commit contents are exact reconstructions of the tree at each milestone, rebuilt
  from recorded Write/Edit operations; Sep 21+ states derive backward from the
  current tree, Sep 20 states forward from the recorded build.
- Two build-era edits (of ~90) could not be re-applied — their effect is limited to
  sub-line details of the 2026-09-20 app state.
- `app/app.py` between 01:25Z and 20:27Z on 2026-09-20 (Genie async-chat rewrite) is
  represented by its 20:27Z snapshot.
- `app/client/package-lock.json` reflects the final dependency set (npm installs ran
  outside tracked file edits).
- A brief Databricks Asset Bundle experiment on 2026-09-20 (removed the same day at
  the user's request) is intentionally omitted.
