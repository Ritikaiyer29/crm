import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import type { TicketDetail } from "../api";

export function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api
      .getTicket(id)
      .then(setTicket)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="centered-message">Loading...</p>;
  if (!ticket) return <p className="empty-state">Ticket not found.</p>;

  return (
    <div>
      <Link to="/tickets" className="back-link">
        &larr; All tickets
      </Link>
      <h1>Ticket</h1>
      <p className="narrative">{ticket.narrative}</p>
      <div className="meta-row">
        <span>Contact: {ticket.contact_name}</span>
        <span>Category: {ticket.category_name}</span>
        <span className={`pill pill-${ticket.status}`}>{ticket.status}</span>
        <span className={`pill pill-priority-${ticket.priority}`}>{ticket.priority}</span>
        <span>
          Deadline: {ticket.regulatory_deadline ? new Date(ticket.regulatory_deadline).toLocaleString() : "-"}
        </span>
      </div>

      <h2>Agent History</h2>
      {ticket.agent_actions.length === 0 && <p className="empty-state">No agent activity yet.</p>}
      {ticket.agent_actions.map((a) => (
        <div key={a.id} className="card">
          <div className="action-header">
            <span className="badge">{a.agent_name}</span>
            <span className="badge badge-muted">{a.action_type}</span>
            <span className={`pill pill-${a.approval_status}`}>{a.approval_status}</span>
          </div>
          <p>{a.final_output ?? a.proposed_output}</p>
        </div>
      ))}
    </div>
  );
}
