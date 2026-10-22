import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import * as api from "../api";
import type { ConversationDetail, ConversationItem } from "../api";
import { PageHeader, useDashboardStats } from "../components/AppShell";
import { Icon } from "../components/Icon";
import { RichText } from "../components/RichText";
import { timeAgo } from "../format";

const FLAG_LABELS: Record<string, { label: string; tone: "danger" | "warn" | "neutral" }> = {
  fraud: { label: "Possible fraud", tone: "danger" },
  large_amount: { label: "Large amount", tone: "danger" },
  legal_threat: { label: "Legal threat", tone: "danger" },
  critical_urgency: { label: "Critical", tone: "danger" },
  regulator_threat: { label: "Regulator mentioned", tone: "warn" },
  distress: { label: "Distressed", tone: "warn" },
  human_request: { label: "Asked for a person", tone: "neutral" },
  no_answer: { label: "No answer found", tone: "neutral" },
  repeated_fallback: { label: "Assistant stuck", tone: "neutral" },
  assistant_error: { label: "Assistant error", tone: "warn" },
};

const TABS = [
  { key: "escalated", label: "Needs a person" },
  { key: "resolved", label: "Resolved" },
  { key: "bot", label: "Bot only" },
];

function FlagChips({ flags, fallback }: { flags: string[]; fallback?: string | null }) {
  const known = flags.map((f) => FLAG_LABELS[f]).filter(Boolean);
  if (known.length === 0 && fallback) return <span className="flag flag-neutral">{fallback}</span>;
  return (
    <>
      {known.map((f) => (
        <span key={f.label} className={`flag flag-${f.tone}`}>
          {f.label}
        </span>
      ))}
    </>
  );
}

export function ConversationsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "escalated";
  const { reload: reloadStats } = useDashboardStats();
  const [items, setItems] = useState<ConversationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    try {
      setItems(await api.getConversations({ status: tab }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations");
    }
  }, [tab]);

  useEffect(() => {
    setItems(null);
    loadList();
    const timer = setInterval(loadList, 6000);
    return () => clearInterval(timer);
  }, [loadList]);

  function changed() {
    loadList();
    reloadStats();
  }

  return (
    <div className="page">
      <PageHeader
        title="Conversations"
        description="Chats the assistant passed to a person: possible fraud, large amounts, requests for a human, and questions it could not answer reliably."
      />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`tab${tab === t.key ? " active" : ""}`} onClick={() => setParams(t.key === "escalated" ? {} : { tab: t.key })}>
            {t.label}
          </button>
        ))}
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className={`inbox${id ? " has-thread" : ""}`}>
        <aside className="inbox-list card" aria-label="Conversations">
          {items === null ? (
            Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="inbox-item">
                <div className="skeleton" style={{ height: 14, width: "55%" }} />
                <div className="skeleton" style={{ height: 12, width: "90%", marginTop: 8 }} />
              </div>
            ))
          ) : items.length === 0 ? (
            <p className="empty">{tab === "escalated" ? "No chats are waiting for a person." : "Nothing here yet."}</p>
          ) : (
            items.map((c) => {
              const waiting = c.status === "escalated" && c.last_message_role !== "admin";
              return (
                <Link key={c.id} to={`/conversations/${c.id}${tab === "escalated" ? "" : `?tab=${tab}`}`} className={`inbox-item${c.id === id ? " active" : ""}`}>
                  <div className="inbox-item-top">
                    <span className="inbox-flags">
                      <FlagChips flags={c.flags} fallback={c.escalation_reason} />
                    </span>
                    <span className="cell-muted">{timeAgo(c.last_message_at)}</span>
                  </div>
                  <p className="inbox-preview">{c.summary ?? c.last_message_preview}</p>
                  <div className="inbox-item-bottom">
                    {waiting ? <span className="waiting">Waiting for reply</span> : <span className="cell-muted">{c.assigned_to_email ? `With ${c.assigned_to_email.split("@")[0]}` : `${c.message_count} messages`}</span>}
                  </div>
                </Link>
              );
            })
          )}
        </aside>

        <section className="inbox-thread card">
          {id ? (
            <Thread key={id} id={id} onChanged={changed} onClose={() => navigate(`/conversations${tab === "escalated" ? "" : `?tab=${tab}`}`)} />
          ) : (
            <div className="thread-empty">
              <span className="empty-icon">
                <Icon name="chat" size={22} />
              </span>
              <h2>Select a conversation</h2>
              <p>You'll see the whole chat, a summary of why it was passed over, and a drafted reply you can edit before sending.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Thread({ id, onChanged, onClose }: { id: string; onChanged: () => void; onClose: () => void }) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [composer, setComposer] = useState("");
  const [fromDraft, setFromDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const draftApplied = useRef(false);
  const count = useRef(0);

  const load = useCallback(async () => {
    try {
      const d = await api.getConversation(id);
      setDetail(d);
      setError(null);
      if (!draftApplied.current) {
        draftApplied.current = true;
        if (d.draft_reply) {
          setComposer(d.draft_reply);
          setFromDraft(true);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the conversation");
    }
  }, [id]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (detail && detail.messages.length !== count.current) {
      count.current = detail.messages.length;
      bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [detail]);

  async function send() {
    const text = composer.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await api.replyToConversation(id, text);
      setComposer("");
      setFromDraft(false);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the reply");
    } finally {
      setBusy(false);
    }
  }

  async function resolve() {
    setBusy(true);
    try {
      setDetail(await api.resolveConversation(id));
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resolve the conversation");
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      send();
    }
  }

  if (error && !detail) return <div className="thread-empty"><div className="alert alert-danger">{error}</div></div>;
  if (!detail) return <div className="thread-empty"><div className="skeleton" style={{ height: 120, width: "70%" }} /></div>;

  const resolved = detail.status === "resolved";

  return (
    <>
      <header className="thread-header">
        <button className="icon-btn thread-back" onClick={onClose} aria-label="Back to the list">
          <Icon name="arrowLeft" size={18} />
        </button>
        <div className="thread-title">
          <div className="inbox-flags">
            <FlagChips flags={detail.flags} fallback={detail.escalation_reason} />
            <span className={`pill status-${detail.status === "escalated" ? "pending" : detail.status === "resolved" ? "resolved" : "open"}`}>
              {detail.status === "escalated" ? "Needs a person" : detail.status === "resolved" ? "Resolved" : "Bot only"}
            </span>
          </div>
          <span className="cell-muted">
            Started {timeAgo(detail.created_at)}
            {detail.assigned_to_email ? ` · with ${detail.assigned_to_email}` : ""}
          </span>
        </div>
        {!resolved && (
          <button className="btn btn-ghost btn-sm" onClick={resolve} disabled={busy}>
            <Icon name="check" size={14} /> Mark resolved
          </button>
        )}
      </header>

      {detail.summary && (
        <div className="thread-summary">
          <div className="thread-summary-label">
            <Icon name="sparkles" size={14} /> Summary for you
          </div>
          <p>{detail.summary}</p>
          {detail.escalation_reason && <p className="cell-muted">Why it was passed over: {detail.escalation_reason}</p>}
        </div>
      )}

      <div className="thread-body" ref={bodyRef}>
        {detail.messages.map((m) =>
          m.role === "system" ? (
            <div key={m.id} className="chat-system">
              {m.content}
            </div>
          ) : (
            <div key={m.id} className={`msg msg-${m.role}`}>
              <div className="msg-meta">
                <strong>{m.role === "customer" ? "Customer" : m.role === "bot" ? "Assistant" : m.author_email ?? "Staff"}</strong>
                <span>{timeAgo(m.created_at)}</span>
              </div>
              <div className="msg-bubble">
                {m.role === "bot" ? <RichText text={m.content} /> : <p>{m.content}</p>}
                {m.role === "bot" && m.citations && m.citations.length > 0 && (
                  <div className="chat-sources">
                    <span>Sources</span>
                    {m.citations.map((c) => (
                      <em key={c.label}>{c.label}</em>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ),
        )}
      </div>

      <footer className="thread-composer">
        {error && <div className="alert alert-danger">{error}</div>}
        {fromDraft && (
          <div className="draft-note">
            <Icon name="sparkles" size={13} /> AI draft. Read it and edit it before you send; the customer sees exactly what is in the box.
          </div>
        )}
        <textarea
          id="staff-reply"
          value={composer}
          onChange={(e) => {
            setComposer(e.target.value);
            if (fromDraft && e.target.value !== detail.draft_reply) setFromDraft(false);
          }}
          onKeyDown={onKeyDown}
          rows={fromDraft ? 7 : 4}
          placeholder={resolved ? "Replying reopens this conversation..." : "Write a reply to the customer..."}
          aria-label="Reply to the customer"
        />
        <div className="thread-composer-actions">
          <span className="cell-muted">Ctrl+Enter to send</span>
          <button className="btn btn-primary" onClick={send} disabled={busy || !composer.trim()}>
            <Icon name="send" size={14} /> Send reply
          </button>
        </div>
      </footer>
    </>
  );
}
