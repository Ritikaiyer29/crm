import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import type { TicketDetail } from "../api";
import { Icon } from "../components/Icon";
import { agentLabel, capitalize, deadlineInfo, formatDate, parseTriage, statusLabel, timeAgo } from "../format";

function Property({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="property">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function TimelineOutput({ text }: { text: string | null }) {
  const triage = parseTriage(text);
  if (!triage) return <p className="timeline-text">{text}</p>;
  return (
    <div className="timeline-text">
      <div className="proposal-fields">
        <span className="chip chip-strong">{triage.category}</span>
        <span className={`pill priority-${triage.priority}`}>{capitalize(triage.priority)} priority</span>
      </div>
      <p className="proposal-text muted">{triage.reasoning}</p>
    </div>
  );
}

function slaProgress(received: string, deadline: string | null): number | null {
  if (!deadline) return null;
  const start = new Date(received).getTime();
  const end = new Date(deadline).getTime();
  if (end <= start) return null;
  return Math.min(1, Math.max(0, (Date.now() - start) / (end - start)));
}

export function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api
      .getTicket(id)
      .then(setTicket)
      .catch(() => setTicket(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="page">
        <div className="skeleton" style={{ width: 120, height: 14 }} />
        <div className="skeleton" style={{ width: 320, height: 28, marginTop: 14 }} />
        <div className="detail-grid" style={{ marginTop: 24 }}>
          <div className="card panel">
            <div className="skeleton" style={{ height: 120 }} />
          </div>
          <div className="card panel">
            <div className="skeleton" style={{ height: 220 }} />
          </div>
        </div>
      </div>
    );
  }
  if (!ticket) {
    return (
      <div className="page">
        <Link to="/tickets" className="back-link">
          <Icon name="arrowLeft" size={14} /> All tickets
        </Link>
        <div className="card empty-card">
          <h2>Ticket not found</h2>
        </div>
      </div>
    );
  }

  const info = deadlineInfo(ticket.regulatory_deadline, ticket.status);
  const progress = ticket.status === "resolved" ? null : slaProgress(ticket.date_received, ticket.regulatory_deadline);

  async function copyId() {
    if (!ticket) return;
    await navigator.clipboard.writeText(ticket.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="page">
      <Link to="/tickets" className="back-link">
        <Icon name="arrowLeft" size={14} /> All tickets
      </Link>
      <div className="page-header">
        <div>
          <h1>Complaint from {ticket.contact_name}</h1>
          <p className="page-description">{ticket.category_name}</p>
        </div>
        <div className="page-actions">
          <span className={`pill status-${ticket.status}`}>{statusLabel(ticket.status)}</span>
          <span className={`pill priority-${ticket.priority}`}>{capitalize(ticket.priority)} priority</span>
        </div>
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          <section className="card panel">
            <header className="panel-header">
              <h2>Customer's account</h2>
              <span className="cell-muted">{formatDate(ticket.date_received, true)}</span>
            </header>
            <p className="narrative">{ticket.narrative}</p>
          </section>

          <section className="card panel">
            <header className="panel-header">
              <div>
                <h2>Agent timeline</h2>
                <p className="panel-subtitle">Everything an agent proposed for this complaint, and what a reviewer did with it</p>
              </div>
            </header>
            {ticket.agent_actions.length === 0 ? (
              <p className="empty">No agent activity yet.</p>
            ) : (
              <ol className="timeline">
                {ticket.agent_actions.map((a) => (
                  <li key={a.id}>
                    <span className={`agent-avatar agent-${a.agent_name}`}>
                      <Icon name="bot" size={14} />
                    </span>
                    <div className="timeline-body">
                      <div className="timeline-head">
                        <strong>{agentLabel(a.agent_name)} agent</strong>
                        <span className="chip">{a.action_type.replace(/_/g, " ")}</span>
                        <span className={`pill status-${a.approval_status}`}>{statusLabel(a.approval_status)}</span>
                        <span className="cell-muted timeline-time">{timeAgo(a.created_at)}</span>
                      </div>
                      <TimelineOutput text={a.final_output ?? a.proposed_output} />
                      {a.confidence !== null && (
                        <span className="cell-muted">Confidence {Math.round(Number(a.confidence) * 100)}%</span>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        <aside className="card panel detail-side">
          <h2>Details</h2>
          <dl className="properties">
            <Property label="Status">
              <span className={`pill status-${ticket.status}`}>{statusLabel(ticket.status)}</span>
            </Property>
            <Property label="Priority">
              <span className={`pill priority-${ticket.priority}`}>{capitalize(ticket.priority)}</span>
            </Property>
            <Property label="Category">{ticket.category_name}</Property>
            <Property label="Customer">{ticket.contact_name}</Property>
            <Property label="Received">{formatDate(ticket.date_received, true)}</Property>
            <Property label="RBI deadline">
              <div>{formatDate(ticket.regulatory_deadline)}</div>
              <span className={`deadline tone-${info.tone}`}>
                <Icon name="clock" size={13} /> {info.label}
              </span>
            </Property>
          </dl>
          {progress !== null && (
            <div className="sla">
              <div className="sla-label">
                <span>30-day resolution window</span>
                <span>{Math.round(progress * 100)}% elapsed</span>
              </div>
              <div className="meter-track tall">
                <div className={`meter-fill tone-${info.tone}`} style={{ width: `${progress * 100}%` }} />
              </div>
            </div>
          )}
          <div className="panel-divider" />
          <div className="property">
            <dt>Reference</dt>
            <dd>
              <button className="ref-copy" onClick={copyId} title="Copy reference">
                <code>{ticket.id}</code>
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            </dd>
          </div>
        </aside>
      </div>
    </div>
  );
}
