import { createBrowserRouter, Navigate } from "react-router-dom";
import { useAuthStore } from "./store/auth";
import { ProtectedRoute } from "./components/common/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { ProjectPage } from "./pages/ProjectPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { ProjectListPage } from "./pages/ProjectListPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";

function AdminRoute() {
  const currentUser = useAuthStore((s) => s.currentUser);
  if (currentUser?.role !== "administrator") {
    return <Navigate to="/projects" replace />;
  }
  return <AdminUsersPage />;
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/projects", element: <ProjectListPage /> },
      { path: "/projects/:projectId", element: <ProjectPage /> },
      { path: "/tickets/:ticketId", element: <TicketDetailPage /> },
      { path: "/admin/users", element: <AdminRoute /> },
      { path: "/", element: <ProjectListPage /> },
    ],
  },
]);
