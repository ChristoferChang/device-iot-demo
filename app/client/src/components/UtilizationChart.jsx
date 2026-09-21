import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";

const CLASS_COLORS = {
  generator: "#f3a800",
  compressor: "#007378",
  excavator: "#008545",
  aerial_lift: "#7dadd9",
};

function fmtDay(d) {
  const dt = new Date(d + "T00:00:00");
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function UtilizationChart({ trend }) {
  const byDay = new Map();
  const classes = new Set();
  for (const row of trend) {
    classes.add(row.equipment_class);
    if (!byDay.has(row.day)) byDay.set(row.day, { day: row.day });
    byDay.get(row.day)[row.equipment_class] = Number(row.utilization_pct);
  }
  const data = [...byDay.values()].sort((a, b) => (a.day < b.day ? -1 : 1));
  const last7 = data.slice(-7).map((d) => ({ ...d, day: fmtDay(d.day) }));

  // Dynamic Y domain: 50% of the value range padded beyond min and max, so
  // trends fill the chart instead of floating in a fixed 0–100% frame.
  const values = last7.flatMap((d) => [...classes].map((c) => d[c]).filter((v) => Number.isFinite(v)));
  let yDomain = [0, 100];
  if (values.length > 0) {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = Math.max((max - min) * 0.5, 5);
    yDomain = [min - pad, max + pad];
  }

  return (
    <div className="card chart-card">
      <div className="card-head">
        <h3>Fleet Utilization — Last 7 Days</h3>
        <span className="card-sub">% of machines with engine running, by class</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={last7} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#e5e5e5" vertical={false} />
          <XAxis dataKey="day" stroke="#737373" tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#d6d6d6" }} />
          <YAxis stroke="#737373" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} unit="%" domain={yDomain} />
          <Tooltip
            contentStyle={{ background: "#1c1c1c", border: "1px solid #1c1c1c", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#d6d6d6" }}
            formatter={(v) => [`${v}%`]}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 6 }} iconType="plainline" />
          {[...classes].map((c) => (
            <Line
              key={c}
              type="monotone"
              dataKey={c}
              name={c.replace("_", " ")}
              stroke={CLASS_COLORS[c] || "#737373"}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
