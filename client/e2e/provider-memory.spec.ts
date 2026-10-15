import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Development UI-state fixture; this test never loads an AI model.
let defaults: object;
test.beforeEach(async ({ request }) => {
  defaults = await (await request.get("/api/settings")).json();
});
test.afterEach(async ({ request }) => {
  await request.patch("/api/settings", { data: defaults });
});
test("memory profile persists and image RAM failure remains explicit", async ({
  page,
  request,
}) => {
  test.setTimeout(30000);
  await page.route("**/api/providers", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.providers = data.providers.map((p: { id: string }) =>
      p.id === "local-video"
        ? {
            ...p,
            status: "Image test needs RAM",
            attention: true,
            verified: false,
            message:
              "The last real image load stopped below 2 GiB free RAM. No image was produced.",
          }
        : p,
    );
    await route.fulfill({ json: data });
  });
  await page.goto("/settings");
  await expect(
    page.getByRole("button", { name: "Save settings", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByText("Image test needs RAM", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/No image was produced/)).toBeVisible();
  await page
    .getByText("Connect an existing WanGP installation", { exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Memory use", exact: true })
    .selectOption("5");
  await page
    .getByRole("checkbox", { name: "Use smaller RAM transfer buffers" })
    .check();
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText("Settings saved.");
  expect(
    (await (await request.get("/api/settings")).json()).wangp.memory_profile,
  ).toBe(5);
  expect(
    (await (await request.get("/api/settings")).json()).wangp
      .smart_memory_pinning,
  ).toBe(false);
  await page.reload();
  await page
    .getByText("Connect an existing WanGP installation", { exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Memory use", exact: true }),
  ).toHaveValue("5");
  await expect(
    page.getByRole("checkbox", { name: "Use smaller RAM transfer buffers" }),
  ).toBeChecked();
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
  await page.getByRole("combobox", { name: "Memory use", exact: true }).focus();
  await page.screenshot({
    path: "../ops/evidence/provider-memory-mobile.png",
    fullPage: true,
  });
});
