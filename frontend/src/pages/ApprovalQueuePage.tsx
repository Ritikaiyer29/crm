import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import * as api from "../api";
import type { AgentAction, Category } from "../api";
import { PageHeader, useDashboardStats } from "../components/AppShell";
import { Icon } from "../components/Icon";
import { agentLabel, capitalize, formatNumber, parseTriage, timeAgo } from "../format";

const PRIORITIES = ["low", "medium", "high", "critical"];
const PAGE_SIZE = 50;
const AGENT_TABS = ["triage", "follow_up", "sales_copilot"];

interface Toast {
  id: number;
  tone: "success" | "danger";
  text: string;
}

export function ApprovalQueuePage() {
  const { stats, reload: reloadStats } = useDashboardStats();
  const [params, setParams] = useSearchParams();
  const agent = params.get("agent") ?? "";
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const categoryNames = useMemo(() => new Map(categories.map((c) => [c.id, c.category_name])), [categories]);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getAgentActions({ status: "pending", agent_name: agent || undefined, limit: PAGE_SIZE })
      .then((a) => {
        if (cancelled) return;
        setActions(a);
        setHasMore(a.length === PAGE_SIZE);
        setError(null);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [agent]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const more = await api.getAgentActions({
        status: "pending",
        agent_name: agent || undefined,
        limit: PAGE_SIZE,
        offset: actions.length,
      });
      setActions((prev) => [...prev, ...more]);
      setHasMore(more.length === PAGE_SIZE);
    } finally {
      setLoadingMore(false);
    }
  }

  function pushToast(tone: Toast["tone"], text: string) {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, tone, text }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }

  async function decide(action: AgentAction, verb: string, fn: () => Promise<unknown>) {
    setBusyId(action.id);
    try {
      await fn();
      setActions((prev) => prev.filter((a) => a.id !== action.id));
      setEditingId(null);
      pushToast("success", `${agentLabel(action.agent_name)} proposal ${verb}`);
      reloadStats();
    } catch (err) {
      pushToast("danger", err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  const pendingByAgent = new Map(stats?.agents.map((a) => [a.agent_name, a.pending]) ?? []);
  const tabs = [
    { key: "", label: "All agents", count: stats?.pending_approvals },
    ...AGENT_TABS.map((a) => ({ key: a, label: agentLabel(a), count: pendingByAgent.get(a) })),
  ];

  return (
    <div className="page">
      <PageHeader
        title="Approval queue"
        description="Every agent proposal waits here. Approving applies it to the real ticket or deal; rejecting discards it. Newest first."
      />

      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key || "all"}
            role="tab"
            aria-selected={agent === t.key}
            className={`tab${agent === t.key ? " active" : ""}`}
            onClick={() => setParams(t.key ? { agent: t.key } : {})}
          >
            {t.label}
            {t.count !== undefined && <span className="tab-count">{formatNumber(t.count)}</span>}
          </button>
        ))}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="queue">
          {[0, 1, 2].map((i) => (
            <div key={i} className="card proposal">
              <div className="skeleton" style={{ width: "30%", height: 14 }} />
              <div className="skeleton" style={{ height: 56, marginTop: 14 }} />
              <div className="skeleton" style={{ width: "60%", height: 14, marginTop: 14 }} />
            </div>
          ))}
        </div>
      ) : actions.length === 0 ? (
        <div className="card empty-card">
          <span className="empty-icon">
            <Icon name="check" size={22} />
          </span>
          <h2>Queue is clear</h2>
          <p>No pending proposals{agent ? ` from the ${agentLabel(agent)} agent` : ""}. New complaints are triaged automatically.</p>
        </div>
      ) : (
        <div className="queue">
          {actions.map((action) => (
            <ProposalCard
              key={action.id}
              action={action}
              categories={categories}
              categoryName={action.proposed_category_id ? categoryNames.get(action.proposed_category_id) : undefined}
              isEditing={editingId === action.id}
              isBusy={busyId === action.id}
              onStartEdit={() => setEditingId(action.id)}
              onCancelEdit={() => setEditingId(null)}
              onApprove={() => decide(action, "approved", () => api.approveAction(action.id))}
              onReject={() => decide(action, "rejected", () => api.rejectAction(action.id))}
              onEditSubmit={(body) => decide(action, "edited and applied", () => api.editAction(action.id, body))}
            />
          ))}
          {hasMore && (
            <button className="btn btn-ghost load-more" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          )}
        </div>
      )}

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <Icon name={t.tone === "success" ? "check" : "alert"} />
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}

function ProposalCard({
  action,
  categories,
  categoryName,
  isEditing,
  isBusy,
  onStartEdit,
  onCancelEdit,
  onApprove,
  onReject,
  onEditSubmit,
}: {
  action: AgentAction;
  categories: Category[];
  categoryName?: string;
  isEditing: boolean;
  isBusy: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onApprove: () => void;
  onReject: () => void;
  onEditSubmit: (body: { category_id?: string; priority?: string; text?: string }) => void;
}) {
  const [categoryId, setCategoryId] = useState(action.proposed_category_id ?? "");
  const [priority, setPriority] = useState(action.proposed_priority ?? "medium");
  const [text, setText] = useState(action.proposed_output ?? "");

  const isTriage = action.agent_name === "triage";
  const canApprove = !isTriage || action.proposed_category_id !== null;
  const confidence = action.confidence !== null ? Number(action.confidence) : null;
  const reasoning = isTriage ? parseTriage(action.proposed_output)?.reasoning : null;

  return (
    <article className="card proposal action-card">
      <header className="proposal-header">
        <span className={`agent-avatar agent-${action.agent_name}`}>
          <Icon name="bot" size={14} />
        </span>
        <div className="proposal-title">
          <strong>{agentLabel(action.agent_name)} agent</strong>
          <span className="chip">{action.action_type.replace(/_/g, " ")}</span>
          <span className="cell-muted">· {timeAgo(action.created_at)}</span>
        </div>
        {confidence !== null && (
          <div className="meter" title="Model-reported confidence">
            <span className="cell-muted">Confidence</span>
            <div className="meter-track">
              <div className="meter-fill" style={{ width: `${confidence * 100}%` }} />
            </div>
            <span>{Math.round(confidence * 100)}%</span>
          </div>
        )}
      </header>

      {action.ticket_narrative && (
        <blockquote className="quote">
          <p>{action.ticket_narrative}</p>
          {action.ticket_id && (
            <Link to={`/tickets/${action.ticket_id}`} className="link-subtle">
              Open ticket <Icon name="chevronRight" size={13} />
            </Link>
          )}
        </blockquote>
      )}
      {!action.ticket_narrative && action.contact_name && (
        <p className="proposal-context">
          <Icon name="user" size={14} /> Customer: <strong>{action.contact_name}</strong>
        </p>
      )}

      {isEditing ? (
        <div className="edit-panel">
          {isTriage ? (
            <div className="form-row">
              <label className="field">
                <span>Category</span>
                <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                  <option value="" disabled>
                    Select a category
                  </option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.category_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field narrow">
                <span>Priority</span>
                <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {capitalize(p)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            <label className="field">
              <span>Proposed text</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} />
            </label>
          )}
          <div className="proposal-actions">
            <button
              className="btn btn-primary"
              disabled={isBusy || (isTriage && !categoryId)}
              onClick={() => onEditSubmit(isTriage ? { category_id: categoryId, priority } : { text })}
            >
              <Icon name="check" /> Save &amp; apply
            </button>
            <button className="btn btn-ghost" disabled={isBusy} onClick={onCancelEdit}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="proposal-body">
            <div className="proposal-label">
              <Icon name="sparkles" size={14} /> Proposed
            </div>
            {isTriage ? (
              <div>
                <div className="proposal-fields">
                  <span className="chip chip-strong">{categoryName ?? "No matching category — edit required"}</span>
                  {action.proposed_priority && (
                    <span className={`pill priority-${action.proposed_priority}`}>{capitalize(action.proposed_priority)} priority</span>
                  )}
                </div>
                {reasoning && <p className="proposal-text muted">{reasoning}</p>}
              </div>
            ) : (
              <p className="proposal-text">{action.proposed_output}</p>
            )}
          </div>
          <div className="proposal-actions">
            <button className="btn btn-success approve" disabled={isBusy || !canApprove} onClick={onApprove}>
              <Icon name="check" /> {canApprove ? "Approve" : "Approve (edit required)"}
            </button>
            <button className="btn btn-ghost" disabled={isBusy} onClick={onStartEdit}>
              <Icon name="pencil" /> Edit
            </button>
            <button className="btn btn-ghost btn-danger-text" disabled={isBusy} onClick={onReject}>
              <Icon name="x" /> Reject
            </button>
          </div>
        </>
      )}
    </article>
  );
}
