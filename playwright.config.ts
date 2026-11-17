import { randomUUID } from "node:crypto";
import { defineConfig } from "@playwright/test";

const python =
  process.platform === "win32"
    ? ".venv\\Scripts\\python.exe"
    : ".venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  outputDir: "artifacts/browser-results",
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8001",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { channel: "msedge", viewport: { width: 1440, height: 1100 } },
    },
    {
      name: "mobile",
      use: {
        channel: "msedge",
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    command: `${python} -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001`,
    url: "http://127.0.0.1:8001/health",
    reuseExistingServer: false,
    env: {
      AI_PROVIDER: "demo",
      OPENAI_API_KEY: "",
      APP_NAME: "INBOX",
      APP_TITLE: "Knowledge inbox",
      ASSISTANT_NAME: "KIN",
      ASSISTANT_TITLE: "How can I help you today?",
      ASSISTANT_PLACEHOLDER: "Ask anything about your saved content…",
      ASSISTANT_SUGGESTIONS:
        '["What is my city?","What do you know about me?","Summarize my notes"]',
      DATABASE_PATH: `artifacts/e2e-${randomUUID()}.sqlite3`,
    },
  },
});
