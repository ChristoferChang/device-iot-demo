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
    try:
        resp = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=sql,
            wait_timeout=timeout_s,
            format=Format.JSON_ARRAY,
        )
    except Exception as e:
        if "PermissionDenied" in type(e).__name__ or "permission to use the SQL Warehouse" in str(e):
            raise HTTPException(
                status_code=502,
                detail=(
                    "OBO fallback failed: the session token lacks the required scopes. "
                    "Fix: fully log out of Databricks (and this app) then re-open the app so the "
                    "consent re-issues tokens with the 'sql' scope — check /api/debug/auth "
                    f"token_scope. Underlying error: {str(e)[:120]}"
                ),
            )
        raise
    state = str(resp.status.state)
    if state != "StatementState.SUCCEEDED":
        err = resp.status.error.message if resp.status and resp.status.error else state
        detail = f"SQL failed: {err}"
        if "INSUFFICIENT_PERMISSIONS" in str(err):
            sp = os.environ.get("DATABRICKS_CLIENT_ID", "<app-sp-id>")
            detail += (
                " | Fix — run these GRANTs as catalog owner/admin: "
                f"GRANT USE CATALOG ON CATALOG sbr_iot_demo TO `{sp}`; "
                f"GRANT USE SCHEMA ON SCHEMA sbr_iot_demo.fleet TO `{sp}`; "
                f"GRANT SELECT ON SCHEMA sbr_iot_demo.fleet TO `{sp}`; "
                f"GRANT MODIFY ON TABLE sbr_iot_demo.fleet.work_orders TO `{sp}`; "
                f"GRANT EXECUTE ON PROCEDURE sbr_iot_demo.fleet.propose_work_order TO `{sp}`; "
                f"GRANT EXECUTE ON PROCEDURE sbr_iot_demo.fleet.approve_work_order TO `{sp}`;"
            )
        raise HTTPException(status_code=502, detail=detail)
    cols = [c.name for c in resp.manifest.schema.columns]
    rows = (resp.result.data_array if resp.result else None) or []
    return [dict(zip(cols, r)) for r in rows]


def q(w: WorkspaceClient, sql: str) -> list[dict[str, Any]]:
    return run_sql(w, sql)


def _is_permission_error(detail: str) -> bool:
    d = str(detail).lower()
    return ("insufficient_permissions" in d or "permission" in d or "403" in d
            or "invalid scope" in d)


def sql_authed(xfat: Optional[str], sql: str, timeout_s: str = "30s") -> list[dict[str, Any]]:
    """Run SQL as the app SP first; on a permission error retry with the
    logged-in user's OBO token (works when the SP lacks UC grants)."""
    try:
        return run_sql(sp_client(), sql, timeout_s)
    except (HTTPException, Exception) as first_err:
        detail = getattr(first_err, "detail", None) or str(first_err)
        obo = user_client(xfat)
        if obo and _is_permission_error(detail):
            log.warning("SQL via SP failed (%s); retrying with OBO user identity", str(detail)[:120])
            try:
                return run_sql(obo, sql, timeout_s)
            except (HTTPException, Exception) as obo_err:
                obo_detail = getattr(obo_err, "detail", None) or str(obo_err)
                raise HTTPException(
                    status_code=502,
                    detail=f"SP auth failed: {detail} || OBO fallback also failed: {obo_detail}",
                )
        raise


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
    import base64
    import json as _json

    tok = request.headers.get("x-forwarded-access-token") or ""
    scope = None
    if tok.count(".") == 2:
        try:
            payload = tok.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            scope = _json.loads(base64.urlsafe_b64decode(payload)).get("scope")
        except Exception:
            scope = "decode-failed"
    return {
        "app_version": "2026-09-20.7-wofix",
        "client_id_set": bool(os.environ.get("DATABRICKS_CLIENT_ID")),
        "host": os.environ.get("DATABRICKS_HOST", ""),
        "email": request.headers.get("x-forwarded-email"),
        "token_len": len(tok),
        "token_scope": scope,
    }



# ---------------------------------------------------------------- api: dashboard


@app.get("/api/dashboard")
def dashboard(x_forwarded_access_token: Optional[str] = Header(default=None)):
    t0 = time.time()
    payload: dict[str, Any] = {}

    def run(key: str, sql: str):
        payload[key] = sql_authed(x_forwarded_access_token, sql)

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


# ---------------------------------------------------------------- api: fleet map


@app.get("/api/fleet-map")
def fleet_map(x_forwarded_access_token: Optional[str] = Header(default=None)):
    rows = sql_authed(
        x_forwarded_access_token,
        f"""
        SELECT m.equipment_id, m.equipment_class, m.latitude, m.longitude,
               COALESCE(h.health_risk_score, 0) AS health_risk_score
        FROM {CATALOG}.{SCHEMA}.gold_machine_status m
        LEFT JOIN {CATALOG}.{SCHEMA}.gold_health_score h ON m.equipment_id = h.equipment_id
        ORDER BY m.equipment_id
        """,
    )
    return {"machines": rows}


# ---------------------------------------------------------------- api: equipment list (for propose modal)


@app.get("/api/equipment")
def equipment(x_forwarded_access_token: Optional[str] = Header(default=None)):
    rows = sql_authed(
        x_forwarded_access_token,
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
def propose_work_order(
    body: ProposeRequest,
    request: Request,
    x_forwarded_access_token: Optional[str] = Header(default=None),
):
    if body.priority not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise HTTPException(status_code=400, detail="priority must be LOW|MEDIUM|HIGH|CRITICAL")
    email = acting_email(request)
    eq = body.equipment_id.replace("'", "")
    notes = body.notes.replace("'", "''")
    log.info("propose_work_order by %s: %s (%s)", email, eq, body.priority)
    sql_authed(
        x_forwarded_access_token,
        f"CALL {CATALOG}.{SCHEMA}.propose_work_order('{eq}', '{body.priority}', '{notes}', '{email}')",
        timeout_s="50s",
    )
    rows = sql_authed(
        x_forwarded_access_token,
        f"SELECT order_id, equipment_id, priority, status, notes, created_by, created_at "
        f"FROM {CATALOG}.{SCHEMA}.work_orders WHERE equipment_id = '{eq}' ORDER BY created_at DESC LIMIT 1",
    )
    order = rows[0] if rows else {}
    send_work_order_alert(email, order)
    return {"ok": True, "order": order, "acted_as": email}


@app.post("/api/work-orders/{order_id}/approve")
def approve_work_order(
    order_id: str,
    request: Request,
    x_forwarded_access_token: Optional[str] = Header(default=None),
):
    email = acting_email(request)
    oid = order_id.replace("'", "")
    log.info("approve_work_order by %s: %s", email, oid)
    sql_authed(
        x_forwarded_access_token,
        f"CALL {CATALOG}.{SCHEMA}.approve_work_order('{oid}', '{email}')",
        timeout_s="50s",
    )
    rows = sql_authed(
        x_forwarded_access_token,
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


def _genie_start(w: WorkspaceClient, message: str, conversation_id: Optional[str]):
    """Fire a Genie message; returns (conversation_id, message_id) immediately."""
    if conversation_id:
        started = w.genie.create_message(
            space_id=GENIE_SPACE_ID, conversation_id=conversation_id, content=message
        )
        return conversation_id, started.message_id
    started = w.genie.start_conversation(space_id=GENIE_SPACE_ID, content=message)
    return started.conversation_id, started.message_id


def _genie_terminal(status: Optional[str]) -> bool:
    return bool(status) and any(
        s in status for s in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT")
    )


def _genie_result(w: WorkspaceClient, conv_id: str, msg_id: str) -> dict:
    """One poll: message status, plus answer/SQL/rows when COMPLETED."""
    msg = w.genie.get_message(space_id=GENIE_SPACE_ID, conversation_id=conv_id, message_id=msg_id)
    raw = str(msg.status) if msg and msg.status else None
    # SDK enum str() is "MessageStatus.COMPLETED" — normalize to the bare word,
    # otherwise the exact != "COMPLETED" compare below always early-returns and
    # the answer/attachments are never extracted.
    status = raw.split(".")[-1] if raw else None
    out = {"conversation_id": conv_id, "message_id": msg_id, "status": status}
    err = getattr(msg, "error", None)
    if err:
        out["error"] = str(err)
    if status != "COMPLETED":
        return out
    if err:
        # Message flipped to FAILED post-hoc under the SP identity — surface it
        # instead of a silent empty answer.
        out["status"] = "FAILED"
        return out

    # Genie flips status to COMPLETED while the attachment payload is still
    # filling in (attachment list can even appear empty on the first polls).
    # Only treat it as done once real content (text / SQL / rows) is present,
    # otherwise report pending so the client keeps polling.
    answer_text = ""
    sql_text = ""
    rows: list[dict] = []
    columns: list[str] = []
    for att in msg.attachments or []:
        if att.text and att.text.content:
            c = att.text.content
            if c not in answer_text:  # Genie sometimes attaches the same text twice
                answer_text += (answer_text + "\n\n" if answer_text else "") + c
        if att.query:
            sql_text = att.query.query or sql_text
            att_id = att.attachment_id or att.query.id
            if att_id:
                try:
                    qr = w.genie.get_message_query_result_by_attachment(
                        space_id=GENIE_SPACE_ID, conversation_id=conv_id,
                        message_id=msg_id, attachment_id=att_id,
                    )
                    sr = qr.statement_response
                    if sr:
                        columns = [c.name for c in sr.manifest.schema.columns]
                        data = sr.result.data_array if sr.result and sr.result.data_array else []
                        rows = [dict(zip(columns, r)) for r in data]
                except Exception as e:
                    log.warning("genie query result fetch failed: %s", e)
    if not answer_text.strip() and not sql_text.strip() and not rows:
        out["status"] = "PENDING"
        return out
    out.update({"answer": answer_text.strip(), "sql": sql_text,
                "columns": columns, "rows": rows[:50]})
    return out


@app.post("/api/copilot/start")
def copilot_start(body: CopilotRequest, x_forwarded_access_token: Optional[str] = Header(default=None)):
    """Kick off a Genie message and return its IDs at once. The client polls
    /api/copilot/status — a synchronous wait would hit the Apps gateway's
    ~60s timeout on slow Genie answers (observed 504s)."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # OBO first: chat runs under the logged-in user's identity and UC grants
    # (the demo's "AI acts under human governance" story). The SP path also
    # flips messages COMPLETED->FAILED post-hoc (restricted tool access), so it
    # is fallback only.
    obo = user_client(x_forwarded_access_token)
    if obo:
        try:
            conv_id, msg_id = _genie_start(obo, message, body.conversation_id)
            return {"conversation_id": conv_id, "message_id": msg_id, "auth": "obo"}
        except Exception as obo_err:
            d = str(obo_err)
            if "required scopes: genie" in d or "required scopes: sql" in d:
                # Missing user API scopes = stale consent, not a fatal config error.
                # Fall through to the SP path so chat still works; the OBO story
                # returns once the user re-consents (logout -> login -> approve).
                log.warning("OBO token missing api scopes; falling back to SP")
            else:
                log.warning("genie start via OBO failed (%s); retrying with SP", d[:200])
    w = sp_client()
    try:
        conv_id, msg_id = _genie_start(w, message, body.conversation_id)
        return {"conversation_id": conv_id, "message_id": msg_id, "auth": "sp"}
    except Exception as sp_err:
        raise HTTPException(status_code=502, detail=f"Genie failed: {str(sp_err)[:200]}")


@app.get("/api/copilot/status")
def copilot_status(
    conversation_id: str,
    message_id: str,
    auth: str = "obo",
    x_forwarded_access_token: Optional[str] = Header(default=None),
):
    if auth == "sp":
        w = sp_client()
    else:
        w = user_client(x_forwarded_access_token)
    if not w:
        raise HTTPException(status_code=502, detail="no usable credentials for Genie status poll")
    return _genie_result(w, conversation_id, message_id)


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
