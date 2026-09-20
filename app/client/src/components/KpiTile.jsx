export default function KpiTile({ label, value, sub, tone = "default", pulse }) {
  return (
    <div className={`kpi kpi-${tone}`}>
      {pulse && <span className="kpi-pulse" />}
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}
