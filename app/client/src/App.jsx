import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "./api.js";
import KpiTile from "./components/KpiTile.jsx";
import UtilizationChart from "./components/UtilizationChart.jsx";
import AtRiskTable from "./components/AtRiskTable.jsx";
import { PendingApprovals, WorkOrderHistory } from "./components/WorkOrders.jsx";
import EventsFeed from "./components/EventsFeed.jsx";
import ProposeModal from "./components/ProposeModal.jsx";
import Copilot from "./components/Copilot.jsx";
import MapCard from "./components/MapCard.jsx";

const REFRESH_MS = 60_000;

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [ago, setAgo] = useState(0);
  const [proposeFor, setProposeFor] = useState(null); // equipment id or "new"
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [busyApprove, setBusyApprove] = useState(null);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  const load = useCallback(async () => {
    try {
      const d = await apiGet("/api/dashboard");
      setData(d);
      setError("");
      setUpdatedAt(Date.now());
    } catch (e) {
      setError(String(e.message || e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const t = setInterval(() => setAgo(updatedAt ? Math.round((Date.now() - updatedAt) / 1000) : 0), 1000);
    return () => clearInterval(t);
  }, [updatedAt]);

  function showToast(msg, tone = "ok") {
    setToast({ msg, tone });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4500);
  }

  async function approve(orderId) {
    setBusyApprove(orderId);
    try {
      const res = await apiPost(`/api/work-orders/${orderId}/approve`, {});
      showToast(`Work order ${orderId} approved → OPEN (by ${res.acted_as})`);
      await load();
    } catch (e) {
      showToast(`Approve failed: ${e.message || e}`, "err");
    } finally {
      setBusyApprove(null);
    }
  }

  const k = data?.kpis || {};
  const pending = (data?.work_orders || []).filter((w) => w.status === "PENDING_APPROVAL");
  const openOrders = (data?.work_orders || []).filter((w) => w.status !== "PENDING_APPROVAL");
  // Machines with a pending or open work order have been actioned — drop them
  // from the at-risk table so they can't be proposed for twice.
  const activeWoIds = new Set(
    (data?.work_orders || [])
      .filter((w) => w.status === "PENDING_APPROVAL" || w.status === "OPEN")
      .map((w) => w.equipment_id)
  );
  const atRiskRows = (data?.at_risk || []).filter((r) => !activeWoIds.has(r.equipment_id));

  return (
    <div>
      <header className="topbar">
        <div className="brand">
          <h1>IoT Fleet Health Center</h1>
        </div>
        <div className="topbar-right">
          <span className={`refresh-note ${ago > 90 ? "stale" : ""}`}>
            {updatedAt ? `Updated ${ago}s ago` : "Loading…"}
          </span>
          <button className="btn btn-ghost" onClick={load} title="Refresh now">
            ⟳ Refresh
          </button>
          <a className="btn btn-ghost" href="/architecture.html" title="Architecture diagram">
            Architecture
          </a>
          <button className="btn btn-primary" onClick={() => setProposeFor("new")}>
            + Propose Work Order
          </button>
          <button className="btn btn-accent" onClick={() => setCopilotOpen(true)}>
            ✦ Genie
          </button>
        </div>
      </header>
      <div className="shell">
      {error && <div className="banner-error">Dashboard load failed: {error}</div>}

      {!data ? (
        <div className="loading">Loading fleet data…</div>
      ) : (
        <main className="main">
          <section className="kpi-grid">
            <KpiTile label="At-Risk Machines" value={k.AT_RISK_COUNT ?? k.at_risk_count ?? "—"} tone="amber" pulse={Number(k.at_risk_count) > 0} sub="risk score ≥ 15" />
            <KpiTile label="Critical" value={k.critical_count ?? "—"} tone="red" sub="risk score ≥ 20" />
            <KpiTile label="Open Work Orders" value={k.open_work_orders ?? "—"} tone="blue" />
            <KpiTile label="Pending Approvals" value={k.pending_approvals ?? "—"} tone="amber" pulse={Number(k.pending_approvals) > 0} sub="awaiting HITL gate" />
            <KpiTile label="Machines Reporting" value={k.machines_reporting ?? "—"} tone="green" sub="live telemetry snapshot" />
            <KpiTile label="7-Day Avg Utilization" value={k.avg_utilization_7d != null ? `${Number(k.avg_utilization_7d).toFixed(1)}%` : "—"} tone="default" sub="all classes" />
          </section>

          <MapCard />

          <section className="grid-2-1">
            <UtilizationChart trend={data.utilization_trend} />
            <EventsFeed events={data.events} />
          </section>

          <AtRiskTable rows={atRiskRows} onPropose={(id) => setProposeFor(id)} />

          <PendingApprovals rows={pending} onApprove={approve} busyId={busyApprove} />

          <WorkOrderHistory rows={openOrders} />
        </main>
      )}
      </div>

      {proposeFor && (
        <ProposeModal
          preselectedId={proposeFor === "new" ? null : proposeFor}
          onClose={() => setProposeFor(null)}
          onCreated={async (order) => {
            setProposeFor(null);
            showToast(`Work order ${order?.order_id} proposed — pending approval`);
            await load();
          }}
        />
      )}

      <Copilot open={copilotOpen} onClose={() => setCopilotOpen(false)} />

      {toast && <div className={`toast ${toast.tone === "err" ? "toast-err" : ""}`}>{toast.msg}</div>}
    </div>
  );
}
