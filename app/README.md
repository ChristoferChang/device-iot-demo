# Fleet Copilot (sbr-fleet-copilot)

Databricks App: FastAPI + React (Vite), single process on `$DATABRICKS_APP_PORT`.

- App URL: https://sbr-fleet-copilot-7405615395376229.9.azure.databricksapps.com
- Profile: `fevm-azure` · Warehouse: `d0163299fb00cd64` · Genie space: `01f1b456af5d124aacf95d5f5d8e3636`
- Data: `sbr_iot_demo.fleet` (read-only); writes only to `work_orders` via the stored procedures.

## Deploy

```bash
cd client && npm run build && cd ..
databricks workspace import-dir . /Users/chris.chang@databricks.com/apps/sbr-fleet-copilot --profile fevm-azure --overwrite
databricks apps deploy sbr-fleet-copilot \
  --source-code-path "/Workspace/Users/chris.chang@databricks.com/apps/sbr-fleet-copilot" \
  --profile fevm-azure
```

## Auth model (current)

Primary = app service principal (injected DATABRICKS_CLIENT_ID/SECRET) for ALL warehouse SQL,
procedure CALLs, and Genie. OBO headers (x-forwarded-access-token / x-forwarded-email) are used
only for the approver identity, plus an automatic SQL fallback when the SP lacks UC grants
(/api/debug/auth shows the session token's scopes).

The SP has CAN_USE on warehouse d0163299fb00cd64 but still needs Unity Catalog grants. Until
these are run (as catalog owner/admin, e.g. chris.chang@databricks.com), SQL fails with
INSUFFICIENT_PERMISSIONS and the UI banner shows the same fix:

```sql
GRANT USE CATALOG ON CATALOG sbr_iot_demo TO `a10e4f96-5338-4016-adb8-cbd7a151530d`;
GRANT USE SCHEMA ON SCHEMA sbr_iot_demo.fleet TO `a10e4f96-5338-4016-adb8-cbd7a151530d`;
GRANT SELECT ON SCHEMA sbr_iot_demo.fleet TO `a10e4f96-5338-4016-adb8-cbd7a151530d`;
GRANT MODIFY ON TABLE sbr_iot_demo.fleet.work_orders TO `a10e4f96-5338-4016-adb8-cbd7a151530d`;
GRANT EXECUTE ON PROCEDURE sbr_iot_demo.fleet.propose_work_order TO `a10e4f96-5338-4016-adb8-cbd7a151530d`;
GRANT EXECUTE ON PROCEDURE sbr_iot_demo.fleet.approve_work_order TO `a10e4f96-5338-4016-adb8-cbd7a151530d`;
```

For the Genie chat pane: the app SP needs CAN_RUN on the Genie space 01f1b456af5d124aacf95d5f5d8e3636
(+ the UC grants above for its generated SQL). Alternatively add the `genie` user API scope so the
OBO fallback can run Genie as the user. Until one of those, chat returns a 502 with a hint.

## Email alerts (deferred by user)

Currently a strict no-op (`send_work_order_alert` in `app.py` logs and does nothing). To enable later,
set these two env vars on the app (Apps UI → Edit env, or add `env:` entries in `app.yaml`):

```
GMAIL_USER=<gmail address>
GMAIL_APP_PASSWORD=<16-char app password>
```

then add the SMTP send in `send_work_order_alert()` — it is the single designated hook.

## Local dev

```bash
python3 -m venv ../sbr-copilot-venv && ../sbr-copilot-venv/bin/pip install -r requirements.txt
(cd client && npm install)
export DATABRICKS_HOST=https://adb-7405615395376229.9.azuredatabricks.net
export DATABRICKS_TOKEN=$(databricks auth token --profile fevm-azure | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
../sbr-copilot-venv/bin/python app.py &   # backend on :8000
cd client && npm run dev                  # vite on :5173 (proxies /api)
```

Note: keep virtualenvs OUT of this directory — `databricks workspace import-dir`
uploads everything, and files >10MB (e.g. compiled .so in site-packages) fail the deploy.
