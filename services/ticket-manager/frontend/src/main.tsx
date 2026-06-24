import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { router } from "./router";
import { useAuthStore } from "./store/auth";
import { LoadingScreen } from "./components/layout/LoadingScreen";
import { AuthErrorScreen } from "./components/layout/AuthErrorScreen";
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

function AppRoot() {
  useTheme();
  const initialized = useAuthStore((s) => s.initialized);
  const initError = useAuthStore((s) => s.initError);
  const initialize = useAuthStore((s) => s.initialize);

  useEffect(() => {
    initialize();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (initError) return <AuthErrorScreen onRetry={() => void initialize()} />;
  if (!initialized) return <LoadingScreen />;

  return <RouterProvider router={router} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <AppRoot />
      </QueryClientProvider>
    </I18nextProvider>
  </StrictMode>
);
