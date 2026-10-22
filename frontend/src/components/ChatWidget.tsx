import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import * as api from "../api";
import type { ChatMessage, ConversationStatus } from "../api";
import { Icon } from "./Icon";
import { RichText } from "./RichText";

const STORAGE_KEY = "novapay_chat_conversation";
const MAX_LENGTH = 1000;
const SUGGESTIONS = [
  "How long does the bank have to resolve my complaint?",
  "My UPI payment failed but money was debited",
  "The bank hasn't replied. What can I do?",
  "I want to talk to a person",
];

function loadId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function saveId(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: the chat still works for this visit */
  }
}

function time(value: string): string {
  return new Date(value).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

export function ChatWidget({ embedded = false }: { embedded?: boolean }) {
  const [open, setOpen] = useState(embedded);
  const [conversationId, setConversationId] = useState<string | null>(loadId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ConversationStatus>("bot");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const lastSeq = useRef(0);
  const openRef = useRef(open);
  useEffect(() => {
    openRef.current = open;
  }, [open]);

  const merge = useCallback((incoming: ChatMessage[]) => {
    if (incoming.length === 0) return;
    setMessages((prev) => {
      const seen = new Set(prev.map((m) => m.id));
      const fresh = incoming.filter((m) => !seen.has(m.id));
      return fresh.length ? [...prev, ...fresh].sort((a, b) => a.seq - b.seq) : prev;
    });
    lastSeq.current = Math.max(lastSeq.current, ...incoming.map((m) => m.seq));
  }, []);

  // Restore a saved conversation, and keep polling while a person has it so their replies show up.
  const poll = useCallback(async () => {
    if (!conversationId) return;
    try {
      const res = await api.pollChat(conversationId, lastSeq.current);
      setStatus(res.status);
      const staffMessages = res.messages.filter((m) => m.role === "admin" || m.role === "system");
      if (!openRef.current && staffMessages.length) setUnread((n) => n + staffMessages.length);
      merge(res.messages);
    } catch (err) {
      if (err instanceof Error && err.message === "Conversation not found") {
        saveId(null);
        setConversationId(null);
      }
    }
  }, [conversationId, merge]);

  const restored = useRef(false);
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (conversationId) poll();
  }, [conversationId, poll]);

  useEffect(() => {
    if (!conversationId || status !== "escalated") return;
    const id = setInterval(poll, open ? 4000 : 10000);
    return () => clearInterval(id);
  }, [conversationId, status, open, poll]);

  useEffect(() => {
    if (open) setUnread(0);
  }, [open]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending, open]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || sending) return;
    setSending(true);
    setError(null);
    setDraft("");
    const optimistic: ChatMessage = {
      id: `pending-${Date.now()}`,
      seq: Number.MAX_SAFE_INTEGER,
      role: "customer",
      content,
      citations: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    try {
      const res = await api.sendChatMessage(content, conversationId);
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      if (res.conversation_id !== conversationId) {
        saveId(res.conversation_id);
        lastSeq.current = 0;
        setConversationId(res.conversation_id);
      }
      setStatus(res.status);
      merge(res.messages);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setDraft(content);
      setError(err instanceof Error ? err.message : "Could not send your message");
    } finally {
      setSending(false);
    }
  }

  function startNewChat() {
    saveId(null);
    setConversationId(null);
    setMessages([]);
    setStatus("bot");
    setError(null);
    lastSeq.current = 0;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  }

  if (!open) {
    return (
      <button className="chat-launcher" onClick={() => setOpen(true)} aria-label="Open help chat">
        <Icon name="chat" size={22} />
        <span>Help</span>
        {unread > 0 && <span className="chat-unread">{unread}</span>}
      </button>
    );
  }

  const escalated = status === "escalated";
  const empty = messages.length === 0;

  return (
    <section className={`chat-panel${embedded ? " embedded" : ""}`} role="dialog" aria-label="NovaPay help chat">
      <header className="chat-header">
        <div className="chat-avatar">
          <Icon name={escalated ? "user" : "sparkles"} size={18} />
        </div>
        <div className="chat-title">
          <strong>NovaPay Help</strong>
          <span>{escalated ? "A team member will reply here" : "Complaints assistant"}</span>
        </div>
        {!empty && (
          <button className="chat-text-btn" onClick={startNewChat}>
            New chat
          </button>
        )}
        {!embedded && (
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Minimise chat">
            <Icon name="minus" size={18} />
          </button>
        )}
      </header>

      <div className="chat-messages" ref={listRef} aria-live="polite">
        <div className="chat-bubble bot">
          <RichText text="Hi, I'm NovaPay's help assistant. I can explain how complaints work and what to do in common situations. I can't see your account, and I'll pass anything serious to a team member." />
        </div>
        {empty && (
          <div className="chat-suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} disabled={sending}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) =>
          m.role === "system" ? (
            <div key={m.id} className="chat-system">
              {m.content}
            </div>
          ) : (
            <div key={m.id} className={`chat-row ${m.role === "customer" ? "mine" : "theirs"}`}>
              {m.role === "admin" && <span className="chat-sender">Support team</span>}
              <div className={`chat-bubble ${m.role}${m.id.startsWith("pending-") ? " pending" : ""}`}>
                <RichText text={m.content} />
              </div>
              {m.role === "bot" && m.citations && m.citations.length > 0 && (
                <div className="chat-sources">
                  <span>Sources</span>
                  {m.citations.map((c) => (
                    <em key={c.label}>{c.label}</em>
                  ))}
                </div>
              )}
              {!m.id.startsWith("pending-") && <span className="chat-time">{time(m.created_at)}</span>}
            </div>
          ),
        )}
        {sending && (
          <div className="chat-row theirs">
            <div className="chat-bubble bot typing" aria-label="Assistant is typing">
              <i />
              <i />
              <i />
            </div>
          </div>
        )}
      </div>

      {escalated && (
        <div className="chat-banner">
          A team member has been notified. You can close this page and come back; your reply will appear here.
        </div>
      )}
      {error && <div className="chat-error">{error}</div>}

      <form className="chat-composer" onSubmit={onSubmit}>
        <textarea
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, MAX_LENGTH))}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={escalated ? "Reply to the team member..." : "Ask about a complaint..."}
          aria-label="Your message"
        />
        <button type="submit" disabled={sending || !draft.trim()} aria-label="Send message">
          <Icon name="send" size={18} />
        </button>
      </form>
      <p className="chat-footnote">Never share an OTP, PIN, CVV or password in this chat.</p>
    </section>
  );
}
