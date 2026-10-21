import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Icon, type IconName } from "../components/Icon";

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "sparkles", title: "Triage in seconds", text: "New complaints are classified into the NCH banking taxonomy the moment they arrive." },
  { icon: "clock", title: "Never miss an RBI deadline", text: "A follow-up agent drafts updates as the 30-day resolution window closes." },
  { icon: "shield", title: "Humans stay in charge", text: "Agents only propose. Every change to a ticket goes through your approval." },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error && err.message !== "Unauthorized" ? err.message : "Incorrect email or password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <div className="brand-name">NovaPay</div>
            <div className="brand-sub">Complaint Ops</div>
          </div>
        </div>
        <div className="auth-hero-body">
          <h2>Agentic complaint resolution, with a human on every decision.</h2>
          <ul className="auth-features">
            {FEATURES.map((f) => (
              <li key={f.title}>
                <span className="auth-feature-icon">
                  <Icon name={f.icon} size={18} />
                </span>
                <div>
                  <strong>{f.title}</strong>
                  <p>{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="auth-foot">Demo environment · synthetic customer data</p>
      </section>

      <section className="auth-form-wrap">
        <form onSubmit={handleSubmit} className="auth-form">
          <h1>Sign in</h1>
          <p className="page-description">Staff access to the complaint operations dashboard.</p>
          <label className="field">
            <span>Work email</span>
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus autoComplete="username" />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              required
              autoComplete="current-password"
            />
          </label>
          {error && <div className="alert alert-danger">{error}</div>}
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
          <div className="auth-customer">
            <span>Are you a customer?</span>
            <Link to="/submit-complaint">Raise a complaint</Link>
            <span>·</span>
            <Link to="/complaint-status">Track one</Link>
          </div>
        </form>
      </section>
    </div>
  );
}
