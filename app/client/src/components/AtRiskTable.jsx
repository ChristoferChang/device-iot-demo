function severity(score) {
  const s = Number(score);
  if (s >= 20) return { label: "CRITICAL", cls: "sev-critical" };
  if (s >= 10) return { label: "HIGH", cls: "sev-high" };
  return { label: "WATCH", cls: "sev-watch" };
}

function aiTier(tier) {
  if (tier === "BELOW_AVERAGE") return { label: "BELOW AVG", cls: "ai-below" };
  if (tier === "ABOVE_AVERAGE") return { label: "ABOVE AVG", cls: "ai-above" };
  if (tier === "AT_AVERAGE") return { label: "AT AVG", cls: "ai-at" };
  return { label: "NO DATA", cls: "ai-nodata" };
}

export function AiAnalysis({ row }) {
  const t = aiTier(row.ai_tier);
  const asOf = row.ai_as_of ? new Date(row.ai_as_of).toLocaleString() : "";
  return (
    <div className="ai-cell" title={asOf ? `Classified ${asOf}` : ""}>
      <span className={`badge ${t.cls}`}>{t.label}</span>
      <span className="ai-suggestion">{row.ai_suggestion || "—"}</span>
    </div>
  );
}

export function SeverityBadge({ score }) {
  const sev = severity(score);
  return <span className={`badge ${sev.cls}`}>{sev.label}</span>;
}

export default function AtRiskTable({ rows, onPropose }) {
  return (
    <div className="card">
      <div className="card-head">
        <h3>At-Risk Machines</h3>
        <span className="card-sub">rule-based score &gt; 0 or AI-flagged below average, last 7 days</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Equipment</th>
            <th>Class</th>
            <th>Risk Score</th>
            <th>Min Battery (7d)</th>
            <th>Running Ratio</th>
            <th>Fuel Anomalies</th>
            <th>Fuel %</th>
            <th>Battery V</th>
            <th>Faults</th>
            <th>AI Analysis</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.equipment_id} className={Number(r.health_risk_score) === 0 ? "ai-only" : ""}>
              <td className="mono strong">{r.equipment_id}</td>
              <td className="dim">{String(r.equipment_class).replace("_", " ")}</td>
              <td>
                <span className="score">{r.health_risk_score}</span> <SeverityBadge score={r.health_risk_score} />
              </td>
              <td>{Number(r.min_battery_running_7d).toFixed(1)} V</td>
              <td>{(Number(r.running_ratio_7d) * 100).toFixed(0)}%</td>
              <td>{r.fuel_anomalies_7d}</td>
              <td>{r.fuel_level_pct != null ? `${Number(r.fuel_level_pct).toFixed(0)}%` : "—"}</td>
              <td className={Number(r.battery_voltage) < 12.3 ? "text-red" : ""}>
                {r.battery_voltage != null ? `${Number(r.battery_voltage).toFixed(2)}` : "—"}
              </td>
              <td className="mono dim">{r.fault_codes && r.fault_codes !== "[]" ? r.fault_codes : "—"}</td>
              <td>
                <AiAnalysis row={r} />
              </td>
              <td>
                <button className="btn btn-ghost" onClick={() => onPropose(r.equipment_id)}>
                  Propose WO
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={11} className="dim center">
                No at-risk machines — fleet healthy.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
