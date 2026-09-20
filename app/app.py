"""Sunbelt Fleet Copilot — Databricks App backend (FastAPI).

Serves the built React frontend from client/dist and the /api routes
from a single process bound to 0.0.0.0:$DATABRICKS_APP_PORT.

Auth model:
  - Reads run as the app's service principal (auto-injected creds).
  - Write actions (propose/approve work orders) use on-behalf-of user
    identity from x-forwarded-access-token when present, falling back to SP.
"""
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("fleet-copilot")

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Format, StatementState

app = FastAPI(title="Sunbelt Fleet Copilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
DIST = BASE_DIR / "client" / "dist"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "d0163299fb00cd64")
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "01f1b456af5d124aacf95d5f5d8e3636")
DEFAULT_APPROVER = os.environ.get("DEFAULT_APPROVER", "fleet-ops@databricks.com")
CATALOG = "sbr_iot_demo"
SCHEMA = "fleet"

# ---------------------------------------------------------------- auth
# Primary auth for ALL warehouse/Genie calls is the app's service principal
# (Databricks Apps injects DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET).
# OBO headers are used ONLY for identity (approver email in audit fields),
# and as an automatic fallback for Genie if the SP lacks space access.

_sp_client: Optional[WorkspaceClient] = None


def sp_client() -> WorkspaceClient:
    """App service-principal client (auto-injected env creds in Apps runtime)."""
    global _sp_client
    if _sp_client is None:
        kwargs: dict[str, Any] = {}
        if os.environ.get("DATABRICKS_HOST"):
            kwargs["host"] = os.environ["DATABRICKS_HOST"]
        if os.environ.get("DATABRICKS_CLIENT_ID"):
            kwargs["client_id"] = os.environ["DATABRICKS_CLIENT_ID"]
            kwargs["client_secret"] = os.environ.get("DATABRICKS_CLIENT_SECRET")
        _sp_client = WorkspaceClient(**kwargs)
    return _sp_client


def user_client(xfat: Optional[str]) -> Optional[WorkspaceClient]:
    """On-behalf-of user client from the app proxy header (fallback only)."""
    if not xfat:
        return None
    try:
        return WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=xfat, auth_type="pat")
    except Exception as e:
        log.warning("OBO client construction failed: %s", e)
        return None


def acting_email(request: Request) -> str:
    """Approver identity for audit fields: x-forwarded-email header, else default."""
    return request.headers.get("x-forwarded-email") or DEFAULT_APPROVER


# ---------------------------------------------------------------- sql helper


def run_sql(w: WorkspaceClient, sql: str, timeout_s: str = "30s") -> list[dict[str, Any]]:
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        wait_timeout=timeout_s,
        format=Format.JSON_ARRAY,
    )
    state = str(resp.status.state)
    if state != "StatementState.SUCCEEDED":
        err = resp.status.error.message if resp.status and resp.status.error else state
        raise HTTPException(status_code=502, detail=f"SQL failed: {err}")
    cols = [c.name for c in resp.manifest.schema.columns]
    rows = (resp.result.data_array if resp.result else None) or []
    return [dict(zip(cols, r)) for r in rows]


def q(w: WorkspaceClient, sql: str) -> list[dict[str, Any]]:
    return run_sql(w, sql)


def f(v: Any, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- email (deferred by user — strict no-op)


def send_work_order_alert(to_note: str, order: dict) -> None:
    """Email alerting is deferred by the user. Wired as a strict no-op:
    when GMAIL_USER / GMAIL_APP_PASSWORD are set later, this is the single
    hook where SMTP send will be added. No retry logic, never blocks UX."""
    configured = bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"))
    log.info(
        "[email:no-op] work order %s (%s) created; email_alerting_configured=%s (deferred by user)",
        order.get("order_id"),
        order.get("equipment_id"),
        configured,
    )


# ---------------------------------------------------------------- api: health


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "sbr-fleet-copilot", "warehouse_id": WAREHOUSE_ID}


@app.get("/api/debug/auth")
def debug_auth(request: Request):
    hdrs = {
        k: (f"<len={len(v)}>" if ("token" in k or "auth" in k) else v)
        for k, v in request.headers.items()
        if k.startswith("x-")
    }
    return {
        "client_id_set": bool(os.environ.get("DATABRICKS_CLIENT_ID")),
        "host": os.environ.get("DATABRICKS_HOST", ""),
        "x_headers": hdrs,
    }


# ---------------------------------------------------------------- api: dashboard


@app.get("/api/dashboard")
def dashboard():
    w = sp_client()
    t0 = time.time()
    payload: dict[str, Any] = {}

    def run(key: str, sql: str):
        payload[key] = q(w, sql)

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {
            "kpis": ex.submit(
                run,
                "kpis",
                f"""
                SELECT
                  (SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.gold_health_score WHERE health_risk_score >= 15) AS at_risk_count,
                  (SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.gold_health_score WHERE health_risk_score >= 20) AS critical_count,
                  (SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.work_orders WHERE status = 'OPEN') AS open_work_orders,
                  (SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.work_orders WHERE status = 'PENDING_APPROVAL') AS pending_approvals,
                  (SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.gold_machine_status) AS machines_reporting,
                  (SELECT ROUND(AVG(utilization_pct) * 100, 1) FROM {CATALOG}.{SCHEMA}.gold_daily_agg
                     WHERE day >= (SELECT MAX(day) FROM {CATALOG}.{SCHEMA}.gold_daily_agg) - INTERVAL 6 DAYS) AS avg_utilization_7d
                """,
            ),
            "trend": ex.submit(
                run,
                "utilization_trend",
                f"SELECT equipment_class, day, ROUND(utilization_pct * 100, 1) AS utilization_pct, machines_reporting "
                f"FROM {CATALOG}.{SCHEMA}.gold_daily_agg ORDER BY day",
            ),
            "risk": ex.submit(
                run,
                "at_risk",
                f"""
                SELECT h.equipment_id, h.equipment_class, h.health_risk_score, h.min_battery_running_7d,
                       h.running_ratio_7d, h.fuel_anomalies_7d,
                       s.fuel_level_pct, s.battery_voltage, s.fault_codes, s.engine_running
                FROM {CATALOG}.{SCHEMA}.gold_health_score h
                LEFT JOIN {CATALOG}.{SCHEMA}.gold_machine_status s ON h.equipment_id = s.equipment_id
                WHERE h.health_risk_score > 0
                ORDER BY h.health_risk_score DESC, h.equipment_id
                """,
            ),
            "events": ex.submit(
                run,
                "events",
                f"SELECT event_ts, equipment_id, equipment_class, event_type, metric_value, detail "
                f"FROM {CATALOG}.{SCHEMA}.gold_events ORDER BY event_ts DESC, equipment_id LIMIT 25",
            ),
            "wos": ex.submit(
                run,
                "work_orders",
                f"SELECT order_id, equipment_id, priority, status, notes, created_by, created_at "
                f"FROM {CATALOG}.{SCHEMA}.work_orders ORDER BY created_at DESC LIMIT 25",
            ),
        }
        # surface exceptions from any branch
        for fut in futs.values():
            fut.result()

    payload["kpis"] = payload["kpis"][0] if payload.get("kpis") else {}

    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["elapsed_ms"] = int((time.time() - t0) * 1000)
    return payload


# ---------------------------------------------------------------- api: equipment list (for propose modal)


@app.get("/api/equipment")
def equipment():
    w = sp_client()
    rows = q(
        w,
        f"""
        SELECT m.equipment_id, m.equipment_class,
               COALESCE(h.health_risk_score, 0) AS health_risk_score
        FROM {CATALOG}.{SCHEMA}.gold_machine_status m
        LEFT JOIN {CATALOG}.{SCHEMA}.gold_health_score h ON m.equipment_id = h.equipment_id
        ORDER BY health_risk_score DESC, m.equipment_id
        """,
    )
    return {"equipment": rows}


# ---------------------------------------------------------------- api: work order actions (HITL)


class ProposeRequest(BaseModel):
    equipment_id: str
    priority: str = "MEDIUM"
    notes: str = ""


@app.post("/api/work-orders/propose")
def propose_work_order(body: ProposeRequest, request: Request, x_forwarded_access_token: Optional[str] = Header(default=None)):
    if body.priority not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise HTTPException(status_code=400, detail="priority must be LOW|MEDIUM|HIGH|CRITICAL")
    w = acting_client(x_forwarded_access_token)
    email = acting_email(request, x_forwarded_access_token)
    eq = body.equipment_id.replace("'", "")
    notes = body.notes.replace("'", "''")
    log.info("propose_work_order by %s: %s (%s)", email, eq, body.priority)
    run_sql(
        w,
        f"CALL {CATALOG}.{SCHEMA}.propose_work_order('{eq}', '{body.priority}', '{notes}', '{email}')",
        timeout_s="60s",
    )
    rows = q(
        viewer_client(x_forwarded_access_token),
        f"SELECT order_id, equipment_id, priority, status, notes, created_by, created_at "
        f"FROM {CATALOG}.{SCHEMA}.work_orders WHERE equipment_id = '{eq}' ORDER BY created_at DESC LIMIT 1",
    )
    order = rows[0] if rows else {}
    send_work_order_alert(email, order)
    return {"ok": True, "order": order, "acted_as": email}


@app.post("/api/work-orders/{order_id}/approve")
def approve_work_order(order_id: str, request: Request, x_forwarded_access_token: Optional[str] = Header(default=None)):
    w = acting_client(x_forwarded_access_token)
    email = acting_email(request, x_forwarded_access_token)
    oid = order_id.replace("'", "")
    log.info("approve_work_order by %s: %s", email, oid)
    run_sql(
        w,
        f"CALL {CATALOG}.{SCHEMA}.approve_work_order('{oid}', '{email}')",
        timeout_s="60s",
    )
    rows = q(
        viewer_client(x_forwarded_access_token),
        f"SELECT order_id, equipment_id, priority, status, notes, created_by, created_at "
        f"FROM {CATALOG}.{SCHEMA}.work_orders WHERE order_id = '{oid}'",
    )
    if not rows:
        raise HTTPException(status_code=404, detail="work order not found after approve")
    return {"ok": True, "order": rows[0], "acted_as": email}


# ---------------------------------------------------------------- api: copilot (Genie)


class CopilotRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


@app.post("/api/copilot")
def copilot(body: CopilotRequest, x_forwarded_access_token: Optional[str] = Header(default=None)):
    """Genie natural-language query. Primary: app service principal (SP).
    If the SP lacks access to the Genie space, falls back to the logged-in
    user's OBO identity."""
    import datetime

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    SID = GENIE_SPACE_ID

    def genie_exchange(w: WorkspaceClient):
        if body.conversation_id:
            started = w.genie.create_message(space_id=SID, conversation_id=body.conversation_id, content=message)
            conv_id = body.conversation_id
        else:
            started = w.genie.start_conversation(space_id=SID, content=message)
            conv_id = started.conversation_id
        msg_id = started.message_id

        deadline = time.time() + 120
        msg = None
        status = None
        while time.time() < deadline:
            time.sleep(2.5)
            msg = w.genie.get_message(space_id=SID, conversation_id=conv_id, message_id=msg_id)
            status = str(msg.status) if msg and msg.status else None
            if status and ("COMPLETED" in status or "FAILED" in status or "CANCELLED" in status or "TIMEOUT" in status):
                break

        answer_text = ""
        sql_text = ""
        rows: list[dict] = []
        columns: list[str] = []
        if status and "COMPLETED" in status:
            for att in msg.attachments or []:
                if att.text and att.text.content:
                    answer_text += (answer_text + "\n\n" if answer_text else "") + att.text.content
                if att.query:
                    sql_text = att.query.query or sql_text
                    att_id = att.attachment_id or att.query.id
                    if att_id:
                        try:
                            qr = w.genie.get_message_query_result_by_attachment(
                                space_id=SID, conversation_id=conv_id, message_id=msg_id, attachment_id=att_id
                            )
                            sr = qr.statement_response
                            if sr:
                                columns = [c.name for c in sr.manifest.schema.columns]
                                data = sr.result.data_array if sr.result and sr.result.data_array else []
                                rows = [dict(zip(columns, r)) for r in data]
                        except Exception as e:
                            log.warning("genie query result fetch failed: %s", e)

        return conv_id, msg_id, status, answer_text, sql_text, columns, rows

    # primary: app service principal
    w = sp_client()
    try:
        conv_id, msg_id, status, answer_text, sql_text, columns, rows = genie_exchange(w)
        auth_used = "sp"
    except Exception as sp_err:
        # fallback: on-behalf-of user identity (e.g. SP lacks Genie space access)
        obo = user_client(x_forwarded_access_token)
        if not obo:
            log.error("genie via SP failed and no OBO token available: %s", sp_err)
            raise HTTPException(status_code=502, detail=f"Genie failed: {sp_err}")
        log.warning("genie via SP failed (%s); retrying with OBO user identity", sp_err)
        conv_id, msg_id, status, answer_text, sql_text, columns, rows = genie_exchange(obo)
        auth_used = "obo"

    if not status or "COMPLETED" not in status:
        raise HTTPException(status_code=504, detail=f"Genie did not complete in time (status={status})")

    return {
        "conversation_id": conv_id,
        "message_id": msg_id,
        "status": status,
        "auth": auth_used,
        "answer": answer_text.strip(),
        "sql": sql_text,
        "columns": columns,
        "rows": rows[:50],
    }


# ---------------------------------------------------------------- static frontend

if DIST.exists() and (DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
