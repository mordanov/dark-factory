import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { Sidebar } from '../components/layout/Sidebar'
import { LoginPage } from '../components/auth/LoginPage'
import { SessionListPage } from '../components/sessions/SessionListPage'
import { SessionDetailPage } from '../components/sessions/SessionDetailPage'
import { AdminUsersPage } from '../components/admin/AdminUsersPage'
import { QueuePage } from '../components/queue/QueuePage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.currentUser)
  const isRestoring = useAuthStore((s) => s.isRestoring)
  const location = useLocation()
  if (isRestoring) return <div style={{ padding: 32 }}><span className="spinner" /></div>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.currentUser)
  if (!user?.is_admin) return <Navigate to="/sessions" replace />
  return <>{children}</>
}

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
      <Route path="/login" element={<LoginPage />} />

      <Route path="/sessions" element={
        <RequireAuth><AppShell><SessionListPage /></AppShell></RequireAuth>
      } />
      <Route path="/sessions/:sessionId" element={
        <RequireAuth><AppShell><SessionDetailPage /></AppShell></RequireAuth>
      } />

      <Route path="/queue" element={
        <RequireAuth><AppShell><QueuePage /></AppShell></RequireAuth>
      } />

      <Route path="/admin" element={
        <RequireAuth>
          <RequireAdmin>
            <AppShell><AdminUsersPage /></AppShell>
          </RequireAdmin>
        </RequireAuth>
      } />

      <Route path="*" element={<Navigate to="/sessions" replace />} />
    </Routes>
  )
}
