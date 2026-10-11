import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  timeout: 120000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8765",
    channel: "msedge",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  reporter: [
    ["list"],
    ["json", { outputFile: "../ops/evidence/browser-tests.json" }],
  ],
});
