import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api";
import type { Ticket } from "../api";

export function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .getTickets(statusFilter || undefined)
      .then(setTickets)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  return (
    <div>
      <h1>Tickets</h1>
      <label className="filter-label">
        Status
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All</option>
          <option value="open">Open</option>
          <option value="in_review">In review</option>
          <option value="pending_approval">Pending approval</option>
          <option value="escalated">Escalated</option>
          <option value="resolved">Resolved</option>
        </select>
      </label>

      {loading ? (
        <p className="centered-message">Loading...</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Contact</th>
              <th>Category</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Deadline</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id}>
                <td>
                  <Link to={`/tickets/${t.id}`}>{t.contact_name}</Link>
                </td>
                <td>{t.category_name}</td>
                <td>
                  <span className={`pill pill-${t.status}`}>{t.status}</span>
                </td>
                <td>
                  <span className={`pill pill-priority-${t.priority}`}>{t.priority}</span>
                </td>
                <td>{t.regulatory_deadline ? new Date(t.regulatory_deadline).toLocaleDateString() : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
