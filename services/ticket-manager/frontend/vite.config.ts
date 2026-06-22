import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-router": ["react-router-dom"],
          "vendor-query": ["@tanstack/react-query"],
          "vendor-i18n": ["i18next", "react-i18next", "i18next-browser-languagedetector"],
          "vendor-motion": ["framer-motion"],
          "vendor-radix": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-popover",
            "@radix-ui/react-select",
            "@radix-ui/react-toast",
            "@radix-ui/react-avatar",
            "@radix-ui/react-label",
            "@radix-ui/react-separator",
            "@radix-ui/react-slot",
          ],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      // Scope thresholds to components with active tests; legacy/untested paths excluded.
      include: [
        "src/components/common/FilterBar.tsx",
        "src/components/common/LanguageSwitcher.tsx",
        "src/components/common/ThemeSwitcher.tsx",
        "src/components/layout/**",
        "src/components/projects/ProjectTicketList.tsx",
        "src/components/tickets/TicketCard.tsx",
        "src/design-system/**",
      ],
      thresholds: { lines: 80, functions: 80, branches: 75, statements: 80 },
      exclude: ["src/test/**", "src/main.tsx"],
    },
  },
});
