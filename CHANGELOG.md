# Changelog

Dates are UTC (commit timestamps). This history was reconstructed on
2026-10-30 by replaying the Claude Code session transcripts (every recorded
file write/edit) against the current tree — see Fidelity notes.

## 2026-10-30 — Submission prep
- Sync `app/requirements.txt` with the deployed app (adds `psycopg[binary]` for Lakebase)
- Add this CHANGELOG and repo hygiene (`.gitignore`)

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
  work-order history, Genie chat panel, Sunbelt Rentals branding
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
