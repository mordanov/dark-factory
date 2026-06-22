import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      coverage: {
        provider: "v8",
        reporter: ["text", "lcov"],
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
  }),
);
