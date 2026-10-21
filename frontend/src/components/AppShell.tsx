import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import * as api from "../api";
import type { DashboardStats } from "../api";
import { useAuth } from "../auth";
import { Icon, type IconName } from "./Icon";

interface StatsContextValue {
  stats: DashboardStats | null;
  error: string | null;
  reload: () => Promise<void>;
}

const StatsContext = createContext<StatsContextValue | undefined>(undefined);

export function useDashboardStats(): StatsContextValue {
  const ctx = useContext(StatsContext);
  if (!ctx) throw new Error("useDashboardStats must be used within AppShell");
  return ctx;
}

function NavItem({ to, icon, label, count, end }: { to: string; icon: IconName; label: string; count?: number; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
      <Icon name={icon} />
      <span>{label}</span>
      {count !== undefined && count > 0 && <span className="nav-count">{count}</span>}
    </NavLink>
  );
}

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      setStats(await api.getDashboardStats());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => setMenuOpen(false), [location.pathname]);

  const initials = (user?.email ?? "?").slice(0, 2).toUpperCase();

  return (
    <StatsContext.Provider value={{ stats, error, reload }}>
      <div className={`shell${menuOpen ? " menu-open" : ""}`}>
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">N</div>
            <div>
              <div className="brand-name">NovaPay</div>
              <div className="brand-sub">Complaint Ops</div>
            </div>
          </div>

          <nav className="nav">
            <div className="nav-section">Workspace</div>
            <NavItem to="/" end icon="grid" label="Overview" />
            <NavItem to="/approvals" icon="inbox" label="Approvals" count={stats?.pending_approvals} />
            <NavItem to="/tickets" icon="ticket" label="Tickets" />

            <div className="nav-section">Customer portal</div>
            <a className="nav-item" href="/submit-complaint" target="_blank" rel="noreferrer">
              <Icon name="external" />
              <span>Raise a complaint</span>
            </a>
            <a className="nav-item" href="/complaint-status" target="_blank" rel="noreferrer">
              <Icon name="external" />
              <span>Track a complaint</span>
            </a>
          </nav>

          <div className="sidebar-callout">
            <Icon name="shield" size={18} />
            <div>
              <strong>Human-in-the-loop</strong>
              <p>Agents only propose. Nothing touches a ticket until someone here approves it.</p>
            </div>
          </div>

          <div className="sidebar-user">
            <div className="avatar">{initials}</div>
            <div className="sidebar-user-text">
              <div className="sidebar-user-email">{user?.email}</div>
              <div className="sidebar-user-role">{user?.role}</div>
            </div>
            <button className="icon-btn" onClick={logout} title="Sign out" aria-label="Sign out">
              <Icon name="logout" />
            </button>
          </div>
        </aside>

        <div className="sidebar-scrim" onClick={() => setMenuOpen(false)} />

        <div className="main-col">
          <header className="mobile-bar">
            <button className="icon-btn" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <Icon name="menu" size={18} />
            </button>
            <div className="brand-mark small">N</div>
            <span className="brand-name">NovaPay</span>
          </header>
          <main className="content">
            <Outlet />
          </main>
        </div>
      </div>
    </StatsContext.Provider>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
