import { useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Navbar } from "@/components/layout/Navbar";
import { PageTransition } from "@/components/layout/PageTransition";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-background focus:text-foreground focus:rounded focus:shadow"
      >
        Skip to content
      </a>
      <Navbar />
      <main id="main-content" className="container mx-auto max-w-7xl px-4 sm:px-6 py-6">
        <AnimatePresence mode="wait">
          <PageTransition key={location.key}>
            {children}
          </PageTransition>
        </AnimatePresence>
      </main>
      <div aria-live="polite" className="sr-only" id="status-announcer" />
    </div>
  );
}
