import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  use: { viewport: { width: 1440, height: 900 }, baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080', trace: 'off' },
  reporter: [['list']],
});
