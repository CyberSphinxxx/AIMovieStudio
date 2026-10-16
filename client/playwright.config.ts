import { defineConfig } from "@playwright/test";
const testURL = new URL(
  process.env.STUDIO_TEST_BASE_URL || "http://127.0.0.1:8765",
);
if (
  testURL.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(testURL.hostname) ||
  testURL.username ||
  testURL.password ||
  testURL.pathname !== "/" ||
  testURL.search ||
  testURL.hash
) {
  throw new Error("Studio browser tests require an HTTP loopback origin");
}
export default defineConfig({
  testDir: "e2e",
  timeout: 120000,
  workers: 1,
  use: {
    baseURL: testURL.origin,
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
