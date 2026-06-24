import { Outlet } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";

export function ProtectedRoute() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
