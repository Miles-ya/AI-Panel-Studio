import { defineConfig } from "@playwright/test";

const backendUrl = "http://127.0.0.1:8000";
const frontendUrl = "http://127.0.0.1:4173";
const e2eDatabaseUrl = "sqlite:////tmp/ai-panel-studio-e2e.sqlite3";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  workers: 1,
  webServer: [
    {
      command: "rm -f /tmp/ai-panel-studio-e2e.sqlite3 /tmp/ai-panel-studio-e2e.sqlite3-wal /tmp/ai-panel-studio-e2e.sqlite3-shm && ./backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000",
      url: `${backendUrl}/openapi.json`,
      reuseExistingServer: false,
      env: {
        DATABASE_URL: e2eDatabaseUrl,
        LLM_PROVIDER: "fake",
      },
    },
    {
      command: "npm run dev --workspace=frontend -- --host 127.0.0.1 --port 4173",
      url: frontendUrl,
      reuseExistingServer: false,
      env: {
        VITE_API_BASE_URL: backendUrl,
      },
    },
  ],
  use: {
    baseURL: frontendUrl,
    trace: "on-first-retry",
  },
});
