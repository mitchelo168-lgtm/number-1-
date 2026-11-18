import { defineConfig, devices } from '@playwright/test'

const API_PORT = 8010
const GUI_PORT = 5180

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${GUI_PORT}`,
    trace: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], launchOptions: { executablePath: '/opt/pw-browsers/chromium' } },
    },
  ],
  webServer: [
    {
      command: 'bash e2e/start-api.sh',
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `npm run dev -- --port ${GUI_PORT} --strictPort`,
      url: `http://127.0.0.1:${GUI_PORT}`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}`,
      },
    },
  ],
})
