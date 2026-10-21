import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { AgentStats } from "../api";
import { PageHeader, useDashboardStats } from "../components/AppShell";
import { BarList, ColumnChart, SegmentedBar } from "../components/charts";
import { Icon, type IconName } from "../components/Icon";
import { agentLabel, capitalize, deadlineInfo, formatNumber, statusLabel, timeAgo } from "../format";

const STATUS_ORDER = ["open", "in_review", "pending_approval", "escalated", "resolved"];
const PRIORITY_ORDER = ["critical", "high", "medium", "low"];
const PRIORITY_COLORS: Record<string, string> = {
  low: "var(--ordinal-1)",
  medium: "var(--ordinal-2)",
  high: "var(--ordinal-3)",
  critical: "var(--ordinal-4)",
};
const AGENT_BLURBS: Record<string, string> = {
  triage: "Classifies new complaints into the NCH taxonomy",
  follow_up: "Drafts updates as RBI deadlines approach",
  sales_copilot: "Flags retention risk and cross-sell openings",
};

function StatTile({
  icon,
  label,
  value,
  sub,
  tone,
  to,
}: {
  icon: IconName;
  label: string;
  value: string;
  sub: ReactNode;
  tone?: "danger" | "accent" | "success";
  to?: string;
}) {
  const body = (
    <>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        <span className={`stat-icon${tone ? ` tone-${tone}` : ""}`}>
          <Icon name={icon} />
        </span>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{sub}</div>
    </>
  );
  return to ? (
    <Link to={to} className="card stat-tile clickable">
      {body}
    </Link>
  ) : (
    <div className="card stat-tile">{body}</div>
  );
}

function Card({ title, subtitle, action, children, className = "" }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card panel ${className}`}>
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="panel-subtitle">{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function acceptance(a: AgentStats): number | null {
  const reviewed = a.approved + a.edited + a.rejected;
  return reviewed ? (a.approved + a.edited) / reviewed : null;
}

function weekLabel(iso: string, long = false): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", long ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
}

export function OverviewPage() {
  const { stats, error, reload } = useDashboardStats();
  const navigate = useNavigate();
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    setRefreshing(true);
    await reload();
    setRefreshing(false);
  }

  if (error && !stats) return <div className="alert alert-danger">{error}</div>;
  if (!stats) return <OverviewSkeleton />;

  const t = stats.tickets;
  const weeklyTotal = stats.weekly_volume.reduce((s, w) => s + w.count, 0);
  const busiest = stats.weekly_volume.reduce((a, b) => (b.count > a.count ? b : a), stats.weekly_volume[0]);
  const categorised = stats.top_categories.reduce((s, c) => s + c.count, 0);
  const otherCount = t.total - categorised;

  return (
    <div className="page">
      <PageHeader
        title="Overview"
        description="Complaint operations for NovaPay Bank — volumes, SLA exposure and how the agents are performing."
        actions={
          <>
            <button className="btn btn-ghost" onClick={refresh} disabled={refreshing}>
              <Icon name="refresh" className={refreshing ? "spin" : undefined} /> Refresh
            </button>
            <Link to="/approvals" className="btn btn-primary">
              <Icon name="inbox" /> Review queue
              <span className="btn-count">{formatNumber(stats.pending_approvals)}</span>
            </Link>
          </>
        }
      />

      <div className="stat-grid">
        <StatTile
          icon="ticket"
          label="Open complaints"
          value={formatNumber(t.open)}
          sub={`of ${formatNumber(t.total)} received`}
          to="/tickets"
        />
        <StatTile
          icon="inbox"
          label="Awaiting approval"
          value={formatNumber(stats.pending_approvals)}
          sub="agent proposals to review"
          tone="accent"
          to="/approvals"
        />
        <StatTile
          icon="alert"
          label="Past RBI deadline"
          value={formatNumber(t.overdue)}
          sub={
            <>
              <strong>{formatNumber(t.due_7d)}</strong> more due within 7 days
            </>
          }
          tone="danger"
        />
        <StatTile
          icon="check"
          label="Resolved on time"
          value={t.on_time_rate === null ? "—" : `${Math.round(t.on_time_rate * 100)}%`}
          sub={`${formatNumber(t.resolved)} complaints resolved`}
          tone="success"
        />
      </div>

      <div className="dash-grid">
        <Card
          className="span-8"
          title="Complaint volume"
          subtitle={`${formatNumber(weeklyTotal)} complaints in the last ${stats.weekly_volume.length} weeks`}
          action={
            busiest && (
              <span className="delta">
                Busiest week: <strong>{formatNumber(busiest.count)}</strong> · {weekLabel(busiest.week_start)}
              </span>
            )
          }
        >
          <ColumnChart
            height={372}
            valueLabel="Complaints"
            data={stats.weekly_volume.map((w) => ({
              key: w.week_start,
              label: weekLabel(w.week_start),
              tooltip: `Week of ${weekLabel(w.week_start, true)}`,
              value: w.count,
            }))}
          />
        </Card>

        <Card className="span-4" title="Pipeline" subtitle="Every complaint by current status">
          <SegmentedBar
            data={STATUS_ORDER.map((s, i) => ({
              key: s,
              label: statusLabel(s),
              value: t.by_status[s] ?? 0,
              color: `var(--series-${i + 1})`,
              onClick: () => navigate(`/tickets?status=${s}`),
            }))}
          />
          <div className="panel-divider" />
          <h3 className="mini-heading">By priority</h3>
          <BarList
            data={PRIORITY_ORDER.map((p) => ({
              key: p,
              label: capitalize(p),
              value: t.by_priority[p] ?? 0,
              color: PRIORITY_COLORS[p],
              onClick: () => navigate(`/tickets?priority=${p}`),
            }))}
          />
        </Card>

        <Card className="span-5" title="Top complaint categories" subtitle="National Consumer Helpline banking taxonomy">
          <BarList
            total={t.total}
            data={stats.top_categories.map((c) => ({
              key: c.id,
              label: c.category_name,
              value: c.count,
              onClick: () => navigate(`/tickets?category=${c.id}`),
            }))}
          />
          {otherCount > 0 && (
            <p className="panel-note">
              + {formatNumber(otherCount)} complaints across the remaining categories
            </p>
          )}
        </Card>

        <Card
          className="span-7"
          title="Agent performance"
          subtitle="How often reviewers accept what each agent proposes"
          action={
            <Link to="/approvals" className="link-subtle">
              Open queue <Icon name="chevronRight" size={14} />
            </Link>
          }
        >
          <div className="table-scroll">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th className="num">Pending</th>
                  <th className="num">Approved</th>
                  <th className="num">Edited</th>
                  <th className="num">Rejected</th>
                  <th className="num">Acceptance</th>
                  <th className="num" title="Average model-reported confidence">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {stats.agents.map((a) => {
                  const acc = acceptance(a);
                  return (
                    <tr key={a.agent_name} className="clickable" onClick={() => navigate(`/approvals?agent=${a.agent_name}`)}>
                      <td>
                        <div className="agent-cell">
                          <span className={`agent-avatar agent-${a.agent_name}`}>
                            <Icon name="bot" size={14} />
                          </span>
                          <div>
                            <div className="cell-strong">{agentLabel(a.agent_name)}</div>
                            <div className="cell-muted">{AGENT_BLURBS[a.agent_name] ?? ""}</div>
                          </div>
                        </div>
                      </td>
                      <td className="num cell-strong">{formatNumber(a.pending)}</td>
                      <td className="num">{formatNumber(a.approved)}</td>
                      <td className="num">{formatNumber(a.edited)}</td>
                      <td className="num">{formatNumber(a.rejected)}</td>
                      <td className="num">{acc === null ? <span className="cell-muted">—</span> : `${Math.round(acc * 100)}%`}</td>
                      <td className="num">
                        {a.avg_confidence === null ? <span className="cell-muted">—</span> : `${Math.round(a.avg_confidence * 100)}%`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="span-5" title="Due soonest" subtitle="Open complaints closest to their RBI deadline">
          {stats.upcoming_deadlines.length === 0 ? (
            <p className="empty">No upcoming deadlines.</p>
          ) : (
            <ul className="list">
              {stats.upcoming_deadlines.map((d) => {
                const info = deadlineInfo(d.regulatory_deadline, d.status);
                return (
                  <li key={d.id}>
                    <Link to={`/tickets/${d.id}`} className="list-row">
                      <div className="list-main">
                        <div className="cell-strong">{d.contact_name}</div>
                        <div className="cell-muted truncate">{d.category_name}</div>
                      </div>
                      <span className={`pill priority-${d.priority}`}>{capitalize(d.priority)}</span>
                      <span className={`deadline tone-${info.tone}`}>
                        <Icon name="clock" size={13} /> {info.label}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card className="span-7" title="Recent agent activity" subtitle="Latest proposals and reviewer decisions">
          <ul className="feed">
            {stats.recent_activity.map((a) => (
              <li key={a.id}>
                <span className={`feed-dot status-${a.approval_status}`} />
                <div className="feed-body">
                  <div>
                    <strong>{agentLabel(a.agent_name)}</strong> {a.approval_status === "pending" ? "proposed" : "proposal"}{" "}
                    <span className="code">{a.action_type.replace(/_/g, " ")}</span>
                    {a.contact_name && (
                      <>
                        {" "}for{" "}
                        {a.ticket_id ? <Link to={`/tickets/${a.ticket_id}`}>{a.contact_name}</Link> : a.contact_name}
                      </>
                    )}
                    {a.approval_status !== "pending" && <> was <strong>{statusLabel(a.approval_status).toLowerCase()}</strong></>}
                  </div>
                  <div className="cell-muted">{timeAgo(a.resolved_at ?? a.created_at)}</div>
                </div>
                <span className={`pill status-${a.approval_status}`}>{statusLabel(a.approval_status)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="skeleton" style={{ width: 160, height: 28 }} />
          <div className="skeleton" style={{ width: 380, height: 14, marginTop: 10 }} />
        </div>
      </div>
      <div className="stat-grid">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card stat-tile">
            <div className="skeleton" style={{ width: "50%", height: 12 }} />
            <div className="skeleton" style={{ width: "40%", height: 30, marginTop: 14 }} />
            <div className="skeleton" style={{ width: "70%", height: 12, marginTop: 10 }} />
          </div>
        ))}
      </div>
      <div className="dash-grid">
        <div className="card panel span-8">
          <div className="skeleton" style={{ height: 260 }} />
        </div>
        <div className="card panel span-4">
          <div className="skeleton" style={{ height: 260 }} />
        </div>
      </div>
    </div>
  );
}
