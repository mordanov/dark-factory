import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { router } from "./router";
import { useAuthStore } from "./store/auth";
import { refresh } from "./api/auth";
import { useTheme } from "./hooks/useTheme";
import i18n from "./i18n";
import "./styles/themes.css";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function parseJwtPayload(token: string): Record<string, unknown> {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function SessionRestorer({ children }: { children: React.ReactNode }) {
  const { isRestoring, refreshToken, login, logout } = useAuthStore((s) => ({
    isRestoring: s.isRestoring,
    refreshToken: s.refreshToken,
    login: s.login,
    logout: s.logout,
  }));

  useEffect(() => {
    if (!isRestoring || !refreshToken) {
      if (isRestoring) logout();
      return;
    }
    refresh(refreshToken)
      .then((accessToken) => {
        const payload = parseJwtPayload(accessToken);
        login(accessToken, refreshToken, {
          id: payload.sub as string,
          email: payload.email as string,
          role: payload.role as "administrator" | "user",
        });
      })
      .catch(() => logout());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (isRestoring) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
        Loading…
      </div>
    );
  }

  return <>{children}</>;
}

function AppRoot() {
  useTheme();
  return <RouterProvider router={router} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <SessionRestorer>
          <AppRoot />
        </SessionRestorer>
      </QueryClientProvider>
    </I18nextProvider>
  </StrictMode>
);
