/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    // e2e/ holds Playwright specs (run via `npm run test:e2e`), not Vitest ones.
    exclude: ['node_modules/**', 'e2e/**'],
  },
})
