const DAY = 86_400_000;

export const AGENT_LABELS: Record<string, string> = {
  triage: "Triage",
  follow_up: "Follow-up",
  sales_copilot: "Sales copilot",
  rag_answer: "Policy answer",
};

export const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_review: "In review",
  pending_approval: "Pending approval",
  escalated: "Escalated",
  resolved: "Resolved",
  pending: "Pending",
  approved: "Approved",
  edited: "Edited",
  rejected: "Rejected",
  auto_approved: "Auto-approved",
};

export function agentLabel(name: string): string {
  return AGENT_LABELS[name] ?? name.replace(/_/g, " ");
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatNumber(n: number): string {
  return n.toLocaleString("en-IN");
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function timeAgo(value: string): string {
  const diff = Date.now() - new Date(value).getTime();
  const mins = Math.round(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

// Triage writes proposed_output as "category='X' (matched: ...), priority=p, reasoning=...".
export function parseTriage(proposed: string | null): { category: string; priority: string; reasoning: string } | null {
  const m = proposed?.match(/^category='(.+?)'.*?, priority=(\w+), reasoning=([\s\S]*)$/);
  return m ? { category: m[1], priority: m[2], reasoning: m[3].trim() } : null;
}

export type DeadlineTone = "overdue" | "soon" | "ok" | "done";

export function deadlineInfo(deadline: string | null, status?: string): { label: string; tone: DeadlineTone } {
  if (status === "resolved") return { label: "Resolved", tone: "done" };
  if (!deadline) return { label: "No deadline", tone: "ok" };
  const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / DAY);
  if (days < 0) return { label: `${-days}d overdue`, tone: "overdue" };
  if (days === 0) return { label: "Due today", tone: "overdue" };
  if (days <= 7) return { label: `${days}d left`, tone: "soon" };
  return { label: `${days}d left`, tone: "ok" };
}
