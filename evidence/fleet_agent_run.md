# Fleet GenAI agent run log

**What this proves:** an explicit GenAI construct in the repo — prompt constants,
an agent class that retrieves governed fleet context and calls a Databricks
foundation model through the OpenAI-compatible serving client, with every step
traced to MLflow (`@mlflow.trace`).

| Item | Value |
|---|---|
| Script | `genai/fleet_agent.py` (run locally via the Databricks SDK) |
| Model endpoint | `databricks-meta-llama-3-3-70b-instruct` |
| Trace destination | Unity Catalog `sbr_iot_demo.traces.fleet_agent_traces` (MLflow experiment `fleet-genai-agent`) |
| Traces captured | 2 (verified spans on first trace: 5) |
| Run time (UTC) | 2026-10-30 18:01 UTC |


**Agent run: 3 machines, 4.3s, model `databricks-meta-llama-3-3-70b-instruct`**

### CMP-0005 (compressor) — risk 20
- Model priority: **MEDIUM**
- Recommended action: Schedule maintenance service due to "SVC_DUE" fault code.

### EXC-0007 (excavator) — risk 20
- Model priority: **MEDIUM**
- Recommended action: Schedule battery test and charging system inspection.

### LFT-0031 (aerial_lift) — risk 15
- Model priority: **LOW**
- Recommended action: Schedule routine inspection and battery check.

