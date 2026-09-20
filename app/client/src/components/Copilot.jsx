import { useRef, useState } from "react";
import { apiPost } from "../api.js";

function renderMarkdown(text) {
  // minimal markdown: **bold** + line breaks
  return text.split("\n").map((line, li) => {
    const parts = line.split(/\*\*(.+?)\*\*/g);
    return (
      <p key={li} style={line.trim().startsWith("-") ? { paddingLeft: 10 } : undefined}>
        {parts.map((p, i) => (i % 2 === 1 ? <strong key={i}>{p}</strong> : p))}
      </p>
    );
  });
}

export default function Copilot({ open, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const conversationId = useRef(null);
  const listRef = useRef(null);

  async function ask(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", loading: true }]);
    try {
      const res = await apiPost("/api/copilot", {
        message: text,
        conversation_id: conversationId.current,
      });
      conversationId.current = res.conversation_id;
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = {
          role: "assistant",
          text: res.answer || "(no answer returned)",
          sql: res.sql,
          columns: res.columns,
          rows: res.rows,
        };
        return next;
      });
    } catch (e2) {
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = { role: "assistant", text: "", error: String(e2.message || e2) };
        return next;
      });
    } finally {
      setBusy(false);
      requestAnimationFrame(() => listRef.current?.scrollTo(0, listRef.current.scrollHeight));
    }
  }

  return (
    <>
      <div className={`copilot-drawer ${open ? "open" : ""}`}>
        <div className="copilot-head">
          <div>
            <h3>Fleet Copilot</h3>
            <span className="card-sub">Ask about your fleet in plain English</span>
          </div>
          <button className="modal-x" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="copilot-messages" ref={listRef}>
          {messages.length === 0 && (
            <div className="copilot-empty">
              <p>Try asking:</p>
              <button className="chip" onClick={() => setInput("which machines are at risk this week?")}>
                Which machines are at risk this week?
              </button>
              <button className="chip" onClick={() => setInput("summarize fleet utilization by class")}>
                Summarize fleet utilization by class
              </button>
              <button className="chip" onClick={() => setInput("any fuel anomalies in the last 7 days?")}>
                Any fuel anomalies in the last 7 days?
              </button>
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div className="msg msg-user" key={i}>
                {m.text}
              </div>
            ) : (
              <div className="msg msg-bot" key={i}>
                {m.loading && <span className="typing">Analyzing fleet data…</span>}
                {m.error && <span className="form-error">{m.error}</span>}
                {m.text && <div className="md">{renderMarkdown(m.text)}</div>}
                {m.rows && m.rows.length > 0 && (
                  <table className="table msg-table">
                    <thead>
                      <tr>{m.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      {m.rows.slice(0, 8).map((r, ri) => (
                        <tr key={ri}>{m.columns.map((c) => <td key={c}>{String(r[c])}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {m.sql && (
                  <details className="sql-details">
                    <summary>Generated SQL</summary>
                    <pre>{m.sql}</pre>
                  </details>
                )}
              </div>
            )
          )}
          {busy && <div className="typing-row">Copilot is thinking…</div>}
        </div>
        <form className="copilot-input" onSubmit={ask}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the fleet a question…"
            disabled={busy}
          />
          <button className="btn btn-primary" disabled={busy || !input.trim()}>
            Ask
          </button>
        </form>
      </div>
      {open && <div className="drawer-scrim" onClick={onClose} />}
    </>
  );
}
