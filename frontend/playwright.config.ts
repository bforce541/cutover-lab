import { defineConfig } from '@playwright/test';

const url = process.env.REHEARSAL_URL ?? 'http://127.0.0.1:8765';
export default defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 65_000 },
  use: { baseURL: url, browserName: 'chromium', viewport: { width: 1440, height: 900 } },
  webServer: process.env.REHEARSAL_URL ? undefined : {
    command: '.venv/bin/python -m uvicorn migration_rehearsal.api:app --host 127.0.0.1 --port 8765',
    cwd: '..',
    env: { REHEARSAL_DATA: process.env.REHEARSAL_BROWSER_DATA === 'full' ? 'full' : 'fixture', REHEARSAL_TARGET: 'local', REHEARSAL_SYSTEM_TRUST: '0' },
    url,
    timeout: 25_000,
  },
});
