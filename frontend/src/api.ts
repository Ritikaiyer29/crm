declare global {
  interface Window {
    __API_BASE_URL__?: string;
  }
}

// Runtime value (written by entrypoint.sh into /env.js at container start)
// wins over the build-time Vite value, so one built image can be pointed at
// a different API per deploy environment without rebuilding.
const API_BASE =
  window.__API_BASE_URL__ || import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";

export interface User {
  id: string;
  email: string;
  role: string;
}

export interface Ticket {
  id: string;
  narrative: string;
  category_name: string;
  status: string;
  priority: string;
  date_received: string;
  regulatory_deadline: string | null;
  contact_name: string;
}

export interface AgentAction {
  id: string;
  agent_name: string;
  action_type: string;
  input_summary: string | null;
  proposed_output: string | null;
  final_output: string | null;
  confidence: string | null;
  approval_status: string;
  created_at: string;
  ticket_id: string | null;
  deal_id: string | null;
  ticket_narrative: string | null;
  contact_name: string | null;
  proposed_category_id: string | null;
  proposed_priority: string | null;
}

export interface TicketDetail extends Ticket {
  agent_actions: AgentAction[];
}

export interface Category {
  id: string;
  category_name: string;
}

export interface ComplaintSubmitResult {
  id: string;
  status: string;
  regulatory_deadline: string | null;
}

export interface ComplaintStatus {
  id: string;
  status: string;
  category_name: string;
  priority: string;
  date_received: string;
  regulatory_deadline: string | null;
  resolved_at: string | null;
}

export interface AgentStats {
  agent_name: string;
  pending: number;
  approved: number;
  edited: number;
  rejected: number;
  avg_confidence: number | null;
}

export interface DashboardStats {
  tickets: {
    total: number;
    open: number;
    resolved: number;
    overdue: number;
    due_7d: number;
    on_time_rate: number | null;
    by_status: Record<string, number>;
    by_priority: Record<string, number>;
  };
  weekly_volume: { week_start: string; count: number }[];
  top_categories: { id: string; category_name: string; count: number }[];
  agents: AgentStats[];
  pending_approvals: number;
  upcoming_deadlines: {
    id: string;
    contact_name: string;
    category_name: string;
    priority: string;
    status: string;
    regulatory_deadline: string;
  }[];
  recent_activity: {
    id: string;
    agent_name: string;
    action_type: string;
    approval_status: string;
    created_at: string;
    resolved_at: string | null;
    ticket_id: string | null;
    contact_name: string | null;
  }[];
}

function getToken(): string | null {
  return localStorage.getItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem("token");
    if (window.location.pathname !== "/login") window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function login(email: string, password: string): Promise<{ access_token: string; user: User }> {
  return request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function getMe(): Promise<User> {
  return request("/auth/me");
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") search.set(k, String(v));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function getTickets(
  params: { status?: string; priority?: string; category_id?: string; q?: string; limit?: number; offset?: number } = {},
): Promise<Ticket[]> {
  return request(`/tickets${query(params)}`);
}

export function getTicket(id: string): Promise<TicketDetail> {
  return request(`/tickets/${id}`);
}

export function getCategories(): Promise<Category[]> {
  return request("/categories");
}

export function getAgentActions(
  params: { status?: string; agent_name?: string; limit?: number; offset?: number } = {},
): Promise<AgentAction[]> {
  return request(`/agent-actions${query(params)}`);
}

export function getDashboardStats(): Promise<DashboardStats> {
  return request("/dashboard/stats");
}

export function approveAction(id: string): Promise<AgentAction> {
  return request(`/agent-actions/${id}/approve`, { method: "POST" });
}

export function rejectAction(id: string): Promise<AgentAction> {
  return request(`/agent-actions/${id}/reject`, { method: "POST" });
}

export function editAction(
  id: string,
  body: { category_id?: string; priority?: string; text?: string },
): Promise<AgentAction> {
  return request(`/agent-actions/${id}/edit`, { method: "POST", body: JSON.stringify(body) });
}

// Public, unauthenticated -- no Bearer token is attached (none exists yet
// for a customer who hasn't logged in), and a 401 here can't happen since
// these routes don't require one.
export function submitComplaint(body: {
  full_name: string;
  email?: string;
  phone?: string;
  narrative: string;
}): Promise<ComplaintSubmitResult> {
  return request("/complaints", { method: "POST", body: JSON.stringify(body) });
}

export function getComplaintStatus(id: string): Promise<ComplaintStatus> {
  return request(`/complaints/${encodeURIComponent(id)}`);
}
