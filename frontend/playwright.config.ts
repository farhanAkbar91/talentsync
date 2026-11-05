import { defineConfig } from "@playwright/test";

/**
 * E2E browser TalentSync AI (dua alur: HR & Kandidat).
 * Menjalankan dua server nyata: backend (uvicorn + SQLite E2E) dan frontend (Vite dev).
 * Kompatibilitas PostgreSQL tetap diverifikasi CI — jalur SQLite hanya untuk
 * memungkinkan E2E browser di mesin tanpa Docker/PostgreSQL (lihat ADR 0003).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    locale: "id-ID",
  },
  webServer: [
    {
      // Windows: cmd.exe memerlukan backslash untuk path venv lokal.
      command:
        ".venv\\Scripts\\python.exe -m scripts.bootstrap_e2e && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 --log-level warning",
      url: "http://localhost:8000/api/v1/health",
      reuseExistingServer: false,
      cwd: "../backend",
      timeout: 90_000,
      env: {
        DATABASE_URL: "sqlite:///e2e.db",
        APP_ENV: "dev",
        LOG_LEVEL: "WARNING",
        SECRET_KEY: "e2e-secret-key-0123456789abcdef0123456789abcdef",
      },
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: false,
      timeout: 90_000,
    },
  ],
});
