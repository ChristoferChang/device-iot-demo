import { useState } from "react";

const PRIORITY_CLS = {
  CRITICAL: "sev-critical",
  HIGH: "sev-high",
  MEDIUM: "sev-watch",
  LOW: "sev-neutral",
};

export function PendingApprovals({ rows, onApprove, busyId }) {
  return (
    <div className="card">
      <div className="card-head">
        <h3>Pending Approvals</h3>
        <span className="card-sub">human-in-the-loop gate</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Order</th>
            <th>Equipment</th>
            <th>Priority</th>
            <th>Notes</th>
            <th>Proposed By</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.order_id}>
              <td className="mono dim small">{r.order_id}</td>
              <td className="mono strong">{r.equipment_id}</td>
              <td>
                <span className={`badge ${PRIORITY_CLS[r.priority] || "sev-neutral"}`}>{r.priority}</span>
              </td>
              <td className="notes" title={r.notes}>
                {r.notes}
              </td>
              <td className="dim small">{r.created_by}</td>
              <td>
                <button
                  className="btn btn-primary"
                  disabled={busyId === r.order_id}
                  onClick={() => onApprove(r.order_id)}
                >
                  {busyId === r.order_id ? "Approving…" : "Approve"}
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="dim center">
                Nothing awaiting approval.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function WorkOrderHistory({ rows }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, 6);
  return (
    <div className="card">
      <div className="card-head">
        <h3>Work Orders</h3>
        <span className="card-sub">latest {rows.length}</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Order</th>
            <th>Equipment</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Notes</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.order_id}>
              <td className="mono dim small">{r.order_id}</td>
              <td className="mono strong">{r.equipment_id}</td>
              <td>
                <span className={`badge ${PRIORITY_CLS[r.priority] || "sev-neutral"}`}>{r.priority}</span>
              </td>
              <td>
                <span className={`status status-${r.status.toLowerCase().replace("_", "-")}`}>
                  {r.status.replace("_", " ")}
                </span>
              </td>
              <td className="notes" title={r.notes}>
                {r.notes}
              </td>
              <td className="dim small">
                {new Date(r.created_at).toLocaleString("en-US", {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="dim center">
                No work orders yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {rows.length > 6 && (
        <button className="btn btn-ghost show-more" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show less" : `Show all ${rows.length}`}
        </button>
      )}
    </div>
  );
}
