const EVENT_STYLE = {
  ENGINE_START: { cls: "ev-start", label: "ENGINE START" },
  ENGINE_STOP: { cls: "ev-stop", label: "ENGINE STOP" },
  FUEL_ANOMALY: { cls: "ev-fuel", label: "FUEL ANOMALY" },
  BATTERY_LOW: { cls: "ev-battery", label: "BATTERY LOW" },
  SERVICE_DUE: { cls: "ev-service", label: "SERVICE DUE" },
};

export default function EventsFeed({ events }) {
  return (
    <div className="card events-card">
      <div className="card-head">
        <h3>Live Events</h3>
        <span className="card-sub">latest {events.length}</span>
      </div>
      <div className="events-list">
        {events.map((e, i) => {
          const st = EVENT_STYLE[e.event_type] || { cls: "ev-stop", label: e.event_type };
          return (
            <div className="event-row" key={i}>
              <span className={`ev-dot ${st.cls}`} />
              <div className="event-body">
                <div className="event-top">
                  <span className={`mono strong ${st.cls === "ev-start" ? "" : ""}`}>{e.equipment_id}</span>
                  <span className={`badge ev-badge ${st.cls}`}>{st.label}</span>
                </div>
                <div className="event-meta">
                  {new Date(e.event_ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                  {" · "}
                  {String(e.equipment_class).replace("_", " ")}
                  {e.metric_value != null && ` · ${Number(e.metric_value).toFixed(1)}`}
                  {e.detail && ` · ${e.detail}`}
                </div>
              </div>
            </div>
          );
        })}
        {events.length === 0 && <div className="dim center pad">No events.</div>}
      </div>
    </div>
  );
}
