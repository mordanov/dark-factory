import { Navigate, Route, Routes } from 'react-router-dom'
import { Sidebar } from '../components/layout/Sidebar'
import { SessionListPage } from '../components/sessions/SessionListPage'
import { SessionDetailPage } from '../components/sessions/SessionDetailPage'
import { QueuePage } from '../components/queue/QueuePage'

function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">{children}</main>
    </div>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/sessions" element={<AppShell><SessionListPage /></AppShell>} />
      <Route path="/sessions/:sessionId" element={<AppShell><SessionDetailPage /></AppShell>} />
      <Route path="/queue" element={<AppShell><QueuePage /></AppShell>} />
      <Route path="*" element={<Navigate to="/sessions" replace />} />
    </Routes>
  )
}
