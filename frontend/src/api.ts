const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";

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

export function getTickets(status?: string): Promise<Ticket[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/tickets${q}`);
}

export function getTicket(id: string): Promise<TicketDetail> {
  return request(`/tickets/${id}`);
}

export function getCategories(): Promise<Category[]> {
  return request("/categories");
}

export function getAgentActions(params: { status?: string; agent_name?: string } = {}): Promise<AgentAction[]> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.agent_name) search.set("agent_name", params.agent_name);
  const qs = search.toString();
  return request(`/agent-actions${qs ? `?${qs}` : ""}`);
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
