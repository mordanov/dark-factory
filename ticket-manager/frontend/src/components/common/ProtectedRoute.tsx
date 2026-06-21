import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { AppShell } from "@/components/layout/AppShell";

export function ProtectedRoute() {
  const { accessToken, isRestoring } = useAuthStore((s) => ({
    accessToken: s.accessToken,
    isRestoring: s.isRestoring,
  }));

  if (isRestoring) return null;
  if (!accessToken) return <Navigate to="/login" replace />;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
