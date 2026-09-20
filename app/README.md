# Sunbelt Fleet Copilot (sbr-fleet-copilot)

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

## Auth gate (REQUIRED before the dashboard renders data)

The app reads/writes on-behalf-of the logged-in user (OBO). The app's user authorization currently
only has scopes `iam.current-user:read, iam.access-control:read` — the warehouse API needs the
**`sql` scope**. Until added, the dashboard shows a banner: "No SQL warehouse access for this identity…".

Two equivalent one-step fixes (either works):
1. Apps UI → `sbr-fleet-copilot` → Authorization → add user API scope `sql`, then re-open the app
   and re-consent. (Equivalent API: `PATCH /api/2.0/apps/sbr-fleet-copilot` with
   `{"user_api_scopes": [..., "sql"]}`.)
2. Or grant the app's service principal `a10e4f96-5338-4016-adb8-cbd7a151530d` `CAN_USE` on
   SQL warehouse `d0163299fb00cd64` (SP fallback then serves all queries).

Option 1 is preferred — all data access then respects the viewer's own UC permissions.

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
