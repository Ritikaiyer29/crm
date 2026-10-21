import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, Link } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { ProtectedRoute } from "./ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { ApprovalQueuePage } from "./pages/ApprovalQueuePage";
import { TicketsPage } from "./pages/TicketsPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { SubmitComplaintPage } from "./pages/SubmitComplaintPage";
import { ComplaintStatusPage } from "./pages/ComplaintStatusPage";
import "./App.css";

function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <div className="app-shell">
      <nav>
        <span className="brand">Agentic CRM</span>
        <Link to="/">Approvals</Link>
        <Link to="/tickets">Tickets</Link>
        <span className="spacer" />
        <span className="nav-user">{user?.email}</span>
        <button className="secondary" onClick={logout}>
          Logout
        </button>
      </nav>
      <main>{children}</main>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/submit-complaint" element={<SubmitComplaintPage />} />
      <Route path="/complaint-status" element={<ComplaintStatusPage />} />
      <Route path="/complaint-status/:id" element={<ComplaintStatusPage />} />
      <Route element={<ProtectedRoute />}>
        <Route
          path="/"
          element={
            <Layout>
              <ApprovalQueuePage />
            </Layout>
          }
        />
        <Route
          path="/tickets"
          element={
            <Layout>
              <TicketsPage />
            </Layout>
          }
        />
        <Route
          path="/tickets/:id"
          element={
            <Layout>
              <TicketDetailPage />
            </Layout>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
