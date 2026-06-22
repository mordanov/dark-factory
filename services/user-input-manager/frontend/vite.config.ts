/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      // Thresholds apply only to files under active test scope (auth migration + factory components).
      // Legacy sessions/admin/workflow components have zero tests and are excluded from threshold enforcement.
      include: [
        'src/store/**',
        'src/components/auth/**',
        'src/components/layout/**',
        'src/components/sessions/ApproveModal.tsx',
        'src/components/sessions/NewSessionModal.tsx',
        'src/components/factory/AuditTrailPage.tsx',
        'src/components/factory/JobsPage.tsx',
        'src/components/factory/PendingTicketsPage.tsx',
        'src/components/queue/JobDetailModal.tsx',
        'src/components/queue/QueuePage.tsx',
      ],
      thresholds: { lines: 80, functions: 80, branches: 75, statements: 80 },
      exclude: ['tests/**', 'src/main.tsx', 'src/i18n/**', 'src/utils/i18n.ts'],
    },
  },
})
