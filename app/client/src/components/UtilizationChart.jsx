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
  generator: "#ff6a13",
  compressor: "#60a5fa",
  excavator: "#34d399",
  aerial_lift: "#c084fc",
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

  return (
    <div className="card chart-card">
      <div className="card-head">
        <h3>Fleet Utilization — Last 7 Days</h3>
        <span className="card-sub">% of machines with engine running, by class</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={last7} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#1b2437" vertical={false} />
          <XAxis dataKey="day" stroke="#5d6b84" tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#233047" }} />
          <YAxis stroke="#5d6b84" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} />
          <Tooltip
            contentStyle={{ background: "#121826", border: "1px solid #233047", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#93a1b8" }}
            formatter={(v) => [`${v}%`]}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 6 }} iconType="plainline" />
          {[...classes].map((c) => (
            <Line
              key={c}
              type="monotone"
              dataKey={c}
              name={c.replace("_", " ")}
              stroke={CLASS_COLORS[c] || "#93a1b8"}
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
