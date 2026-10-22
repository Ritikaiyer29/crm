import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getComplaintStatus, type ComplaintStatus } from "../api";
import { ChatWidget } from "../components/ChatWidget";

function formatDate(value: string | null): string {
  if (!value) return "--";
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

export function ComplaintStatusPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [reference, setReference] = useState(id ?? "");
  const [status, setStatus] = useState<ComplaintStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function lookup(ref: string) {
    setError(null);
    setLoading(true);
    setStatus(null);
    try {
      setStatus(await getComplaintStatus(ref));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not find that complaint");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (id) lookup(id);
  }, [id]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (reference.trim()) navigate(`/complaint-status/${reference.trim()}`);
  }

  return (
    <div className="centered-page">
      <div className="card login-card">
        <h1>Check complaint status</h1>
        <p className="subtitle">NovaPay Bank -- complaint operations</p>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label>
            Reference number
            <input value={reference} onChange={(e) => setReference(e.target.value)} required autoFocus />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Looking up..." : "Check status"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        {status && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px dashed var(--border)" }}>
            <p className="action-header">
              <span className={`pill pill-${status.status}`}>{status.status.replace("_", " ")}</span>
              <span className={`pill pill-priority-${status.priority}`}>{status.priority}</span>
            </p>
            <p className="context">Category: {status.category_name}</p>
            <p className="context">Received: {formatDate(status.date_received)}</p>
            <p className="context">
              {status.resolved_at
                ? `Resolved: ${formatDate(status.resolved_at)}`
                : `Due by: ${formatDate(status.regulatory_deadline)}`}
            </p>
          </div>
        )}
        <p className="hint" style={{ marginTop: 16, marginBottom: 0 }}>
          Need to raise a new complaint? <Link to="/submit-complaint">Start here</Link>.
        </p>
      </div>
      <ChatWidget />
    </div>
  );
}
