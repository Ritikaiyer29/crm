import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { submitComplaint, type ComplaintSubmitResult } from "../api";
import { ChatWidget } from "../components/ChatWidget";

export function SubmitComplaintPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [narrative, setNarrative] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ComplaintSubmitResult | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await submitComplaint({
        full_name: fullName,
        email: email || undefined,
        phone: phone || undefined,
        narrative,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit your complaint");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    const deadline = result.regulatory_deadline
      ? new Date(result.regulatory_deadline).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        })
      : null;
    return (
      <div className="centered-page">
        <div className="card login-card">
          <h1>Complaint received</h1>
          <p className="subtitle">NovaPay Bank -- complaint operations</p>
          <p>Your reference number is:</p>
          <p className="reference-id">{result.id}</p>
          <p className="hint">
            Save this -- you'll need it to check your complaint's status. Under the RBI's Integrated
            Ombudsman Scheme, we're required to resolve this by <b>{deadline ?? "the regulatory deadline"}</b>.
          </p>
          <Link to={`/complaint-status/${result.id}`}>
            <button type="button">Check status now</button>
          </Link>
        </div>
        <ChatWidget />
      </div>
    );
  }

  return (
    <div className="centered-page">
      <form onSubmit={handleSubmit} className="card login-card">
        <h1>Raise a complaint</h1>
        <p className="subtitle">NovaPay Bank -- complaint operations</p>
        <label>
          Your name
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} required autoFocus />
        </label>
        <label>
          Email (optional)
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
        </label>
        <label>
          Phone (optional)
          <input value={phone} onChange={(e) => setPhone(e.target.value)} type="tel" />
        </label>
        <label>
          What happened?
          <textarea
            value={narrative}
            onChange={(e) => setNarrative(e.target.value)}
            required
            minLength={20}
            maxLength={5000}
            rows={6}
            placeholder="Describe your complaint in as much detail as you can -- amounts, dates, what you expected to happen."
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Submitting..." : "Submit complaint"}
        </button>
        <p className="hint" style={{ marginTop: 8, marginBottom: 0 }}>
          Already have a reference number? <Link to="/complaint-status">Check status</Link>.
          Bank staff: <Link to="/login">sign in</Link>.
        </p>
      </form>
      <ChatWidget />
    </div>
  );
}
