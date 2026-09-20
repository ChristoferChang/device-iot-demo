import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function ProposeModal({ preselectedId, onClose, onCreated }) {
  const [equipment, setEquipment] = useState([]);
  const [equipmentId, setEquipmentId] = useState(preselectedId || "");
  const [priority, setPriority] = useState("HIGH");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet("/api/equipment")
      .then((d) => {
        setEquipment(d.equipment);
        if (!preselectedId && d.equipment.length) {
          setEquipmentId(d.equipment[0].equipment_id);
        }
      })
      .catch((e) => setError(String(e.message || e)));
  }, [preselectedId]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await apiPost("/api/work-orders/propose", {
        equipment_id: equipmentId,
        priority,
        notes,
      });
      onCreated(res.order);
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-head">
          <h3>Propose Work Order</h3>
          <button type="button" className="modal-x" onClick={onClose}>
            ×
          </button>
        </div>
        <label className="field">
          <span>Equipment</span>
          <select value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)} required>
            {equipment.map((eq) => (
              <option key={eq.equipment_id} value={eq.equipment_id}>
                {eq.equipment_id} — {String(eq.equipment_class).replace("_", " ")}
                {eq.health_risk_score > 0 ? ` (risk ${eq.health_risk_score})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Priority</span>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Notes</span>
          <textarea
            rows={3}
            value={notes}
            placeholder="What should the service tech check?"
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || !equipmentId}>
            {busy ? "Proposing…" : "Propose for Approval"}
          </button>
        </div>
        <p className="modal-hint">Creates a PENDING_APPROVAL row — a human approves before it becomes OPEN.</p>
      </form>
    </div>
  );
}
