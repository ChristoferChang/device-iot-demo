import { useEffect, useRef, useState } from "react";
import { Map as MapLibre, Marker, Popup, AttributionControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { apiGet } from "../api.js";

// Self-contained raster style: no external style JSON, no vector-tile worker
// parsing — avoids silent style-load stalls seen with remote vector styles.
const TILE_STYLE = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};
const CENTER = [-80.75, 34.75];
const ZOOM = 7;

function riskColor(score) {
  const s = Number(score) || 0;
  if (s >= 20) return "#d23b12"; // red — critical
  if (s > 0) return "#e08700";   // amber — at-risk
  return "#008545";              // Sunbelt green — healthy
}

export default function MapCard() {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);
  const popupRef = useRef(null);
  const [machines, setMachines] = useState([]);
  const [error, setError] = useState(null);
  const [mapReady, setMapReady] = useState(false);
  // Legend focus filter: "all" | "healthy" | "atRisk" | "critical" — clicking a
  // legend category dims the other pins and raises the selected ones.
  const [focus, setFocus] = useState("all");

  // Load fleet-map data
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const d = await apiGet("/api/fleet-map");
        if (alive) setMachines(d.machines || []);
      } catch (e) {
        if (alive) setError(String(e.message || e));
      }
    }
    load();
    const t = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new MapLibre({
      container: containerRef.current,
      style: TILE_STYLE,
      center: CENTER,
      zoom: ZOOM,
      attributionControl: false,
    });
    map.addControl(new AttributionControl({ compact: true }), "bottom-right");
    map.on("load", () => setMapReady(true));
    map.on("error", (e) => {
      // Surface style/tile failures instead of failing silently on a blank canvas.
      const msg = e?.error?.message || String(e?.error || e || "");
      if (msg && !msg.includes("Failed to fetch")) console.warn("maplibre:", msg);
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Place/update markers as soon as the map instance exists and data changes —
  // markers are DOM overlays positioned by projection math, so they do not
  // depend on the basemap style finishing loading.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || machines.length === 0) return;

    // Remove old markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    if (popupRef.current) { popupRef.current.remove(); popupRef.current = null; }

    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 14 });
    popupRef.current = popup;

    machines.forEach((m) => {
      const lat = parseFloat(m.latitude);
      const lon = parseFloat(m.longitude);
      if (!isFinite(lat) || !isFinite(lon)) return;

      const el = document.createElement("div");
      const score = Number(m.health_risk_score) || 0;
      el.className = "fleet-marker" + (score >= 20 ? " fleet-marker-critical" : "");
      const color = riskColor(score);
      Object.assign(el.style, {
        width: "13px",
        height: "13px",
        borderRadius: "50%",
        background: color,
        border: "2px solid rgba(255,255,255,0.95)",
        cursor: "pointer",
        boxShadow: "0 1px 4px rgba(28,28,28,0.4)",
        transition: "opacity 0.25s ease",
      });
      // Critical pins always stack above at-risk, which stack above healthy.
      el.style.zIndex = score >= 20 ? "600" : score > 0 ? "400" : "200";

      el.addEventListener("mouseenter", () => {
        popup
          .setLngLat([lon, lat])
          .setHTML(
            `<div style="font:13px/1.5 'Roboto',sans-serif;color:#1c1c1c;padding:2px 4px">
              <strong>${m.equipment_id}</strong><br/>
              ${m.equipment_class?.replace(/_/g, " ")}<br/>
              Risk: <span style="color:${color};font-weight:700">${score}</span>
            </div>`
          )
          .addTo(map);
      });
      el.addEventListener("mouseleave", () => popup.remove());

      const marker = new Marker({ element: el }).setLngLat([lon, lat]).addTo(map);
      markersRef.current.push({ marker, el, score });
    });

    return () => {
      markersRef.current.forEach((m) => m.marker.remove());
      markersRef.current = [];
      if (popupRef.current) { popupRef.current.remove(); popupRef.current = null; }
    };
  }, [machines]);

  // Apply legend focus: dim non-selected pins and lift selected ones above the
  // rest. Kept as its own effect so highlight state never depends on marker
  // rebuild ordering.
  useEffect(() => {
    markersRef.current.forEach(({ el, score }) => {
      const base = score >= 20 ? "600" : score > 0 ? "400" : "200";
      const selected =
        focus === "all" ||
        (focus === "healthy" && score === 0) ||
        (focus === "atRisk" && score > 0 && score < 20) ||
        (focus === "critical" && score >= 20);
      el.style.opacity = selected ? "1" : "0.15";
      // Severity order governs stacking by default; the 900 boost applies only
      // when a legend filter is actively highlighting a group.
      el.style.zIndex = focus !== "all" && selected ? "900" : base;
      if (el.parentElement) el.parentElement.style.zIndex = focus !== "all" && selected ? "600" : "10";
    });
  }, [focus, machines]);

  const critical = machines.filter((m) => Number(m.health_risk_score) >= 20).length;
  const atRisk = machines.filter((m) => Number(m.health_risk_score) > 0 && Number(m.health_risk_score) < 20).length;
  const healthy = machines.filter((m) => Number(m.health_risk_score) === 0 || m.health_risk_score == null).length;

  return (
    <div className="card map-card">
      <div className="card-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 className="card-title">Fleet Location Map</h2>
        <div className="map-legend">
          {[
            { key: "healthy", label: "healthy", count: healthy, color: "#008545" },
            { key: "atRisk", label: "at-risk", count: atRisk, color: "#e08700" },
            { key: "critical", label: "critical", count: critical, color: "#d23b12" },
          ].map((item) => (
            <button
              key={item.key}
              className={"legend-item legend-btn" + (focus === item.key ? " legend-active" : "")}
              title={focus === item.key ? "Show all machines" : `Highlight ${item.label} machines`}
              onClick={() => setFocus(focus === item.key ? "all" : item.key)}
            >
              <span className="legend-dot" style={{ background: item.color }} />
              {item.count} {item.label}
            </button>
          ))}
        </div>
      </div>
      {error && <div style={{ color: "#d23b12", padding: "8px 0", fontSize: 13 }}>Map error: {error}</div>}
      <div ref={containerRef} style={{ width: "100%", height: 460, borderRadius: 8, overflow: "hidden", background: "#e8eaed" }} />
    </div>
  );
}
