import { Link } from "react-router-dom";
import { ChatWidget } from "../components/ChatWidget";

export function ChatPage() {
  return (
    <div className="centered-page">
      <div className="chat-page">
        <div className="chat-page-intro">
          <h1>NovaPay Help</h1>
          <p className="subtitle">Ask about complaints, timelines and what to do next. A team member joins if your question needs one.</p>
          <p className="hint">
            Ready to file? <Link to="/submit-complaint">Raise a complaint</Link>. Already filed? <Link to="/complaint-status">Check status</Link>.
          </p>
        </div>
        <ChatWidget embedded />
      </div>
    </div>
  );
}
