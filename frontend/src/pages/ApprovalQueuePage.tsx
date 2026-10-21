import { useEffect, useState } from "react";
import * as api from "../api";
import type { AgentAction, Category } from "../api";

const PRIORITIES = ["low", "medium", "high", "critical"];

export function ApprovalQueuePage() {
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [a, c] = await Promise.all([api.getAgentActions({ status: "pending" }), api.getCategories()]);
      setActions(a);
      setCategories(c);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function withBusy(id: string, fn: () => Promise<void>) {
    setBusyId(id);
    try {
      await fn();
      await load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <p className="centered-message">Loading...</p>;
  if (error) return <p className="error">{error}</p>;

  return (
    <div>
      <h1>Pending Approvals ({actions.length})</h1>
      <p className="hint">
        Every agent proposal sits here until a human approves, edits, or rejects it -- nothing below has touched a
        real ticket or deal yet.
      </p>
      {actions.length === 0 && <p className="empty-state">Nothing pending.</p>}
      {actions.map((action) => (
        <ActionCard
          key={action.id}
          action={action}
          categories={categories}
          isEditing={editingId === action.id}
          isBusy={busyId === action.id}
          onStartEdit={() => setEditingId(action.id)}
          onCancelEdit={() => setEditingId(null)}
          onApprove={() => withBusy(action.id, () => api.approveAction(action.id).then(() => undefined))}
          onReject={() => withBusy(action.id, () => api.rejectAction(action.id).then(() => undefined))}
          onEditSubmit={(body) =>
            withBusy(action.id, async () => {
              await api.editAction(action.id, body);
              setEditingId(null);
            })
          }
        />
      ))}
    </div>
  );
}

function ActionCard({
  action,
  categories,
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

  const context = action.ticket_narrative ?? action.contact_name ?? "";
  const canAutoApprove = action.agent_name !== "triage" || action.proposed_category_id !== null;

  return (
    <div className="card action-card">
      <div className="action-header">
        <span className="badge">{action.agent_name}</span>
        <span className="badge badge-muted">{action.action_type}</span>
        <span className="confidence">confidence: {action.confidence ?? "-"}</span>
      </div>
      {context && <p className="context">{context}</p>}
      <p className="proposed">{action.proposed_output}</p>

      {isEditing ? (
        <div className="edit-form">
          {action.agent_name === "triage" ? (
            <>
              <label>
                Category
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
              <label>
                Priority
                <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <div className="action-buttons">
                <button
                  className="approve"
                  disabled={isBusy || !categoryId}
                  onClick={() => onEditSubmit({ category_id: categoryId, priority })}
                >
                  Save
                </button>
                <button className="secondary" disabled={isBusy} onClick={onCancelEdit}>
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
              <div className="action-buttons">
                <button className="approve" disabled={isBusy} onClick={() => onEditSubmit({ text })}>
                  Save
                </button>
                <button className="secondary" disabled={isBusy} onClick={onCancelEdit}>
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="action-buttons">
          <button className="approve" disabled={isBusy || !canAutoApprove} onClick={onApprove}>
            {canAutoApprove ? "Approve" : "Approve (edit required)"}
          </button>
          <button className="edit" disabled={isBusy} onClick={onStartEdit}>
            Edit
          </button>
          <button className="reject" disabled={isBusy} onClick={onReject}>
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
