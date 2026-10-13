import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("finished export folder action has busy, launch and failure feedback", async ({
  page,
  request,
}) => {
  await request.patch("/api/settings", {
    data: { speech: "none", story_model: "", reserve_mb: 1024 },
  });
  const created = await request.post("/api/projects", {
    data: {
      idea: "A lighthouse finds a new shore.",
      kind: "clip",
      target_seconds: 5,
      orientation: "portrait",
      backend: "demo",
      idempotency_key: crypto.randomUUID(),
    },
  });
  const project = await created.json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${project.id}`)).json())
          .status,
    )
    .toBe("COMPLETED");
  await page.goto(`/project/${project.id}`);
  await page.getByRole("tab", { name: "Export", exact: true }).click();
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/assets/*/show-in-folder", async (route) => {
    await held;
    await route.fulfill({ json: { launch_requested: true } });
  });
  await page
    .getByRole("button", { name: "Show in folder", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Opening folder…", exact: true }),
  ).toBeDisabled();
  release();
  await expect(page.getByRole("status")).toContainText(
    "File Explorer requested",
  );
  await page.unroute("**/api/assets/*/show-in-folder");
  await page.route("**/api/assets/*/show-in-folder", (route) =>
    route.fulfill({
      status: 503,
      json: {
        code: "FOLDER_UNAVAILABLE",
        message: "Folder could not be opened. Download the MP4 instead.",
      },
    }),
  );
  await page
    .getByRole("button", { name: "Show in folder", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Download the MP4 instead",
  );
  await expect(
    page.getByRole("link", { name: "Download MP4", exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/assets/*/show-in-folder");
  await page
    .getByRole("button", { name: "Show in folder", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "File Explorer requested",
  );
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page
    .getByRole("button", { name: "Show in folder", exact: true })
    .focus();
  await page.screenshot({
    path: "../ops/evidence/export-folder-mobile.png",
    fullPage: true,
  });
});
