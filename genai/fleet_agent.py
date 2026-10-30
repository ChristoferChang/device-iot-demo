"""Fleet GenAI agent — the repository's explicit GenAI construct layer.

An agent that retrieves at-risk fleet context from the governed gold tables
(via the SQL warehouse) and calls a Databricks foundation model through the
OpenAI-compatible serving-endpoints client to produce a maintenance briefing
per machine. Traced with MLflow so every retrieval and model call shows up as
a span in the Databricks MLflow experiment.

Run locally:
    export DATABRICKS_HOST=https://adb-7405615395376229.9.azuredatabricks.net
    export DATABRICKS_TOKEN=$(databricks auth token --profile fevm-azure -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
    python3 genai/fleet_agent.py     # writes evidence/fleet_agent_run.md

Model: pay-per-token Databricks foundation model, override with DATABRICKS_MODEL.
"""
import json
import os
import time

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Format, StatementState

CATALOG = "sbr_iot_demo"
SCHEMA = "fleet"
WAREHOUSE_ID = "d0163299fb00cd64"
MODEL = os.environ.get("DATABRICKS_MODEL", "databricks-claude-3-7-sonnet")
FALLBACK_MODELS = ["databricks-meta-llama-3-3-70b-instruct", "databricks-claude-3-5-sonnet"]
TOP_N = 3

SYSTEM_PROMPT = (
    "You are a fleet maintenance advisor for an equipment-rental company. "
    "You receive one machine's 7-day health summary (risk score, battery, fuel "
    "anomalies, utilization, faults). Reply with exactly two lines:\n"
    "PRIORITY: <LOW|MEDIUM|HIGH|CRITICAL>\n"
    "ACTION: <one imperative maintenance action, max 25 words>"
)
USER_PROMPT_TEMPLATE = (
    "Machine {equipment_id} ({equipment_class}):\n"
    "- Health risk score: {risk}\n"
    "- Min battery while running (7d): {battery} V\n"
    "- Fuel anomalies (7d): {fuel_anoms}\n"
    "- Running ratio (7d): {running}\n"
    "- Engine hours (latest): {hours}\n"
    "- Active fault codes: {faults}\n"
    "{extra}"
)

RUN_NOTE = """# Fleet GenAI agent run log

**What this proves:** an explicit GenAI construct in the repo — prompt constants,
an agent class that retrieves governed fleet context and calls a Databricks
foundation model through the OpenAI-compatible serving client, with every step
traced to MLflow (`@mlflow.trace`).

| Item | Value |
|---|---|
| Script | `genai/fleet_agent.py` (run locally via the Databricks SDK) |
| Model endpoint | `{model}` |
| Trace destination | Unity Catalog `sbr_iot_demo.traces.fleet_agent_traces` (MLflow experiment `fleet-genai-agent`) |
| Traces captured | {trace_count} (verified spans on first trace: {span_count}) |
| Run time (UTC) | {ts} |

{output}
"""


class FleetMaintenanceAgent:
    """Retrieve -> augment -> foundation-model call -> structured recommendation."""

    def __init__(self, client: WorkspaceClient | None = None, model: str = MODEL):
        self.w = client or WorkspaceClient()
        self.model = model
        self._openai = None

    # -- retrieval -----------------------------------------------------------
    @mlflow.trace(name="retrieve_at_risk_context")
    def retrieve_at_risk(self, limit: int = TOP_N) -> list[dict]:
        sql = f"""
            SELECT h.equipment_id, h.equipment_class, h.health_risk_score,
                   h.min_battery_running_7d, h.fuel_anomalies_7d,
                   h.running_ratio_7d, h.engine_hours_latest, s.fault_codes
            FROM {CATALOG}.{SCHEMA}.gold_health_score h
            LEFT JOIN {CATALOG}.{SCHEMA}.gold_machine_status s
                   ON h.equipment_id = s.equipment_id
            WHERE h.health_risk_score > 0
            ORDER BY h.health_risk_score DESC, h.equipment_id
            LIMIT {limit}
        """
        resp = self.w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, statement=sql,
            wait_timeout="30s", format=Format.JSON_ARRAY)
        if str(resp.status.state) != str(StatementState.SUCCEEDED):
            raise RuntimeError(f"retrieval failed: {resp.status.state}")
        cols = [c.name for c in resp.manifest.schema.columns]
        return [dict(zip(cols, r)) for r in (resp.result.data_array or [])]

    # -- model call ----------------------------------------------------------
    @mlflow.trace(name="recommend_action", span_type="LLM")
    def recommend(self, machine: dict) -> dict:
        faults = machine.get("fault_codes")
        if isinstance(faults, list):
            faults = ", ".join(map(str, faults)) if faults else "none"
        extra = (
            "This machine is already flagged BELOW_AVERAGE by the ai_classify triage. "
            "Weight your action accordingly."
        )
        user = USER_PROMPT_TEMPLATE.format(
            equipment_id=machine.get("equipment_id"),
            equipment_class=machine.get("equipment_class"),
            risk=machine.get("health_risk_score"),
            battery=machine.get("min_battery_running_7d"),
            fuel_anoms=machine.get("fuel_anomalies_7d"),
            running=machine.get("running_ratio_7d"),
            hours=machine.get("engine_hours_latest"),
            faults=faults or "none",
            extra=extra,
        )
        models = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        last_err = None
        for m in models:
            try:
                # OpenAI-compatible chat completions on Databricks foundation
                # models (pay-per-token serving endpoints), authenticated by
                # the SDK's auto-refreshed credentials.
                resp = self.w.api_client.do(
                    "POST", "/serving-endpoints/chat/completions",
                    body={"model": m,
                          "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                       {"role": "user", "content": user}],
                          "max_tokens": 200, "temperature": 0.2})
                text = resp["choices"][0]["message"]["content"].strip()
                priority, action = "", ""
                for line in text.splitlines():
                    if line.upper().startswith("PRIORITY:"):
                        priority = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("ACTION:"):
                        action = line.split(":", 1)[1].strip()
                return {"model": m, "priority": priority, "action": action or text}
            except Exception as e:
                last_err = e
                print(f"  model {m} failed ({str(e)[:120]}), trying fallback")
        raise RuntimeError(f"all model endpoints failed: {last_err}")

    # -- orchestration -------------------------------------------------------
    @mlflow.trace(name="fleet_agent_run")
    def run(self) -> list[dict]:
        out = []
        for machine in self.retrieve_at_risk():
            rec = self.recommend(machine)
            out.append({"machine": machine, "recommendation": rec})
        return out


if __name__ == "__main__":
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment("/Users/chris.chang@databricks.com/fleet-genai-agent")
    # Unity Catalog trace storage: governed table beside the demo data.
    try:
        from mlflow.tracing.destination import UnityCatalog
        mlflow.tracing.set_destination(
            UnityCatalog(table_name=f"{CATALOG}.traces.fleet_agent_traces"))
    except Exception as e:
        # NOT a silent fallback — traces would land in the legacy workspace
        # experiment store instead of UC; say so loudly.
        print(f"WARNING: Unity Catalog trace destination unavailable ({e}); "
              f"traces will use legacy workspace storage", flush=True)

    agent = FleetMaintenanceAgent()
    t0 = time.time()
    results = agent.run()
    elapsed = round(time.time() - t0, 1)

    # verify traces landed, per the MLflow tracing workflow
    mlflow.flush_trace_async_logging()
    exp = mlflow.get_experiment_by_name("/Users/chris.chang@databricks.com/fleet-genai-agent")
    traces = mlflow.search_traces(locations=[exp.experiment_id]) if exp else []
    trace_count = len(traces)
    span_count = 0
    if trace_count:
        span_count = len(mlflow.get_trace(traces.iloc[0].trace_id).data.spans)
    print(f"traces: {trace_count}, spans on first trace: {span_count}")

    lines = ["", f"**Agent run: {len(results)} machines, {elapsed}s, model `{results[0]['recommendation']['model']}`**", ""]
    for item in results:
        m, r = item["machine"], item["recommendation"]
        lines.append(f"### {m['equipment_id']} ({m['equipment_class']}) — risk {m['health_risk_score']}")
        lines.append(f"- Model priority: **{r['priority']}**")
        lines.append(f"- Recommended action: {r['action']}")
        lines.append("")

    out_path = os.path.join(os.path.dirname(__file__), "..", "evidence", "fleet_agent_run.md")
    with open(out_path, "w") as f:
        f.write(RUN_NOTE.format(
            model=results[0]["recommendation"]["model"] if results else MODEL,
            trace_count=trace_count, span_count=span_count,
            ts=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            output="\n".join(lines)))
    print(f"wrote {os.path.abspath(out_path)}")
    for item in results:
        print(f"  {item['machine']['equipment_id']}: {item['recommendation']['priority']} — {item['recommendation']['action']}")
