import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as api from "../api";
import type { Category, Ticket } from "../api";
import { PageHeader, useDashboardStats } from "../components/AppShell";
import { Icon } from "../components/Icon";
import { capitalize, deadlineInfo, formatDate, formatNumber, statusLabel } from "../format";

const PAGE_SIZE = 25;
const STATUSES = ["open", "in_review", "pending_approval", "escalated", "resolved"];

export function TicketsPage() {
  const { stats } = useDashboardStats();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const priority = params.get("priority") ?? "";
  const category = params.get("category") ?? "";
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? 1));

  const [search, setSearch] = useState(q);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    api
      .getCategories()
      .then((c) =>
        setCategories(
          [...c].sort((a, b) =>
            a.category_name === "Other" ? 1 : b.category_name === "Other" ? -1 : a.category_name.localeCompare(b.category_name),
          ),
        ),
      )
      .catch(() => undefined);
  }, []);

  // Read the live URL, not the render's `params` snapshot: quick successive filter changes and the
  // debounced search timer would otherwise overwrite each other with stale values.
  function update(next: Record<string, string>) {
    const merged = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v);
      else merged.delete(k);
    }
    if (!("page" in next)) merged.delete("page");
    setParams(merged);
  }

  useEffect(() => {
    if (search === q) return;
    const id = setTimeout(() => update({ q: search }), 300);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getTickets({ status, priority, category_id: category, q, limit: PAGE_SIZE + 1, offset: (page - 1) * PAGE_SIZE })
      .then((t) => {
        if (cancelled) return;
        setTickets(t);
        setError(null);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [status, priority, category, q, page]);

  const hasNext = tickets.length > PAGE_SIZE;
  const rows = tickets.slice(0, PAGE_SIZE);
  const counts = stats?.tickets.by_status;
  const hasFilters = Boolean(priority || category || q);

  return (
    <div className="page">
      <PageHeader
        title="Tickets"
        description={stats ? `${formatNumber(stats.tickets.total)} complaints · ${formatNumber(stats.tickets.open)} still open` : "All customer complaints"}
      />

      <div className="tabs">
        {[{ key: "", label: "All", count: stats?.tickets.total }, ...STATUSES.map((s) => ({ key: s, label: statusLabel(s), count: counts?.[s] }))].map(
          (t) => (
            <button key={t.key || "all"} className={`tab${status === t.key ? " active" : ""}`} onClick={() => update({ status: t.key })}>
              {t.label}
              {t.count !== undefined && <span className="tab-count">{formatNumber(t.count)}</span>}
            </button>
          ),
        )}
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by customer name or complaint text…"
            aria-label="Search tickets"
          />
          {search && (
            <button className="icon-btn" onClick={() => setSearch("")} aria-label="Clear search">
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
        <select className="select" value={priority} onChange={(e) => update({ priority: e.target.value })} aria-label="Priority">
          <option value="">All priorities</option>
          {["critical", "high", "medium", "low"].map((p) => (
            <option key={p} value={p}>
              {capitalize(p)}
            </option>
          ))}
        </select>
        <select
          className="select select-category"
          value={category}
          onChange={(e) => update({ category: e.target.value })}
          aria-label="Category"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.category_name}
            </option>
          ))}
        </select>
        {hasFilters && (
          <button
            className="btn btn-ghost"
            onClick={() => {
              setSearch("");
              update({ priority: "", category: "", q: "" });
            }}
          >
            <Icon name="x" size={14} /> Clear filters
          </button>
        )}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table data-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Category</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Received</th>
                <th>RBI deadline</th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 8 }, (_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 6 }, (_, j) => (
                        <td key={j}>
                          <div className="skeleton" style={{ height: 14, width: j === 0 ? "80%" : "60%" }} />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((t) => {
                    const info = deadlineInfo(t.regulatory_deadline, t.status);
                    return (
                      <tr key={t.id} className="clickable" onClick={() => navigate(`/tickets/${t.id}`)}>
                        <td className="cell-customer">
                          <a
                            href={`/tickets/${t.id}`}
                            className="cell-strong"
                            onClick={(e) => {
                              e.preventDefault();
                              navigate(`/tickets/${t.id}`);
                            }}
                          >
                            {t.contact_name}
                          </a>
                          <div className="cell-muted truncate">{t.narrative}</div>
                        </td>
                        <td className="cell-category">{t.category_name}</td>
                        <td>
                          <span className={`pill status-${t.status}`}>{statusLabel(t.status)}</span>
                        </td>
                        <td>
                          <span className={`pill priority-${t.priority}`}>{capitalize(t.priority)}</span>
                        </td>
                        <td className="nowrap cell-muted">{formatDate(t.date_received)}</td>
                        <td className="nowrap">
                          <span className={`deadline tone-${info.tone}`}>
                            <Icon name="clock" size={13} /> {info.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
        </div>
        {!loading && rows.length === 0 && <p className="empty">No tickets match these filters.</p>}
        <footer className="table-footer">
          <span className="cell-muted">
            {rows.length ? `Showing ${(page - 1) * PAGE_SIZE + 1}–${(page - 1) * PAGE_SIZE + rows.length}` : ""}
          </span>
          <div className="pager">
            <button className="btn btn-ghost btn-sm" disabled={page <= 1 || loading} onClick={() => update({ page: String(page - 1) })}>
              Previous
            </button>
            <span className="cell-muted">Page {page}</span>
            <button className="btn btn-ghost btn-sm" disabled={!hasNext || loading} onClick={() => update({ page: String(page + 1) })}>
              Next
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
