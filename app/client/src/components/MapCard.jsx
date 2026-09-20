import { useEffect, useRef, useState } from "react";
import { Map as MapLibre, Marker, Popup, AttributionControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { apiGet } from "../api.js";

const TILE_STYLE = "https://demotiles.maplibre.org/style.json";
const CENTER = [-80.9, 34.6];
const ZOOM = 6;

function riskColor(score) {
  const s = Number(score) || 0;
  if (s >= 20) return "#d23b12"; // red — critical
  if (s > 0) return "#e08700";   // amber — at-risk
  return "#737373";               // grey — healthy
}

export default function MapCard() {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);
  const popupRef = useRef(null);
  const [machines, setMachines] = useState([]);
  const [error, setError] = useState(null);
  const [mapReady, setMapReady] = useState(false);

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
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Place/update markers whenever map is ready and data changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || machines.length === 0) return;

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
      el.className = "fleet-marker";
      const score = Number(m.health_risk_score) || 0;
      const color = riskColor(score);
      Object.assign(el.style, {
        width: "10px",
        height: "10px",
        borderRadius: "50%",
        background: color,
        border: "1.5px solid rgba(255,255,255,0.8)",
        cursor: "pointer",
        boxShadow: score >= 20 ? `0 0 0 3px ${color}44` : "none",
      });

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
      markersRef.current.push(marker);
    });

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      if (popupRef.current) { popupRef.current.remove(); popupRef.current = null; }
    };
  }, [machines, mapReady]);

  const critical = machines.filter((m) => Number(m.health_risk_score) >= 20).length;
  const atRisk = machines.filter((m) => Number(m.health_risk_score) > 0 && Number(m.health_risk_score) < 20).length;
  const healthy = machines.filter((m) => Number(m.health_risk_score) === 0 || m.health_risk_score == null).length;

  return (
    <div className="card map-card">
      <div className="card-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 className="card-title">Fleet Location Map</h2>
        <div className="map-legend">
          <span className="legend-item"><span className="legend-dot" style={{ background: "#737373" }} />{healthy} healthy</span>
          <span className="legend-item"><span className="legend-dot" style={{ background: "#e08700" }} />{atRisk} at-risk</span>
          <span className="legend-item"><span className="legend-dot" style={{ background: "#d23b12" }} />{critical} critical</span>
        </div>
      </div>
      {error && <div style={{ color: "#d23b12", padding: "8px 0", fontSize: 13 }}>Map error: {error}</div>}
      <div ref={containerRef} style={{ width: "100%", height: 300, borderRadius: 8, overflow: "hidden", background: "#e8eaed" }} />
    </div>
  );
}
