import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { ProtectedRoute } from "./ProtectedRoute";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ApprovalQueuePage } from "./pages/ApprovalQueuePage";
import { TicketsPage } from "./pages/TicketsPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { ChatPage } from "./pages/ChatPage";
import { SubmitComplaintPage } from "./pages/SubmitComplaintPage";
import { ComplaintStatusPage } from "./pages/ComplaintStatusPage";
import "./App.css";
import "./chat.css";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/submit-complaint" element={<SubmitComplaintPage />} />
          <Route path="/complaint-status" element={<ComplaintStatusPage />} />
          <Route path="/complaint-status/:id" element={<ComplaintStatusPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/approvals" element={<ApprovalQueuePage />} />
              <Route path="/conversations/:id?" element={<ConversationsPage />} />
              <Route path="/tickets" element={<TicketsPage />} />
              <Route path="/tickets/:id" element={<TicketDetailPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
