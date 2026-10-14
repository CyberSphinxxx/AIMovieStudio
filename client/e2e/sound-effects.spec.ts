import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

let defaults: Record<string, unknown> | undefined;
test.afterEach(async ({ request }) => {
  if (defaults) {
    expect(
      (await request.patch("/api/settings", { data: defaults })).ok(),
    ).toBe(true);
    defaults = undefined;
  }
});

test("sound effects toggle persists and a demo movie downloads its original effects stem", async ({
  page,
  request,
}) => {
  defaults = await (await request.get("/api/settings")).json();
  await page.goto("/settings");
  const toggle = page.getByRole("checkbox", {
    name: "Add sound effects to new movies",
  });
  await expect(
    page.getByRole("button", { name: "Save settings", exact: true }),
  ).toBeEnabled();
  await toggle.uncheck();
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.getByText("Settings saved.", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/settings")).json()).sound_effects,
  ).toBe(false);
  await page.reload();
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.getByText("Settings saved.", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../ops/evidence/sound-effects-settings-mobile.png",
    fullPage: true,
  });

  // Explicit demo fixture; original synthesized sound does not certify AI visuals.
  const created = await request.post("/api/projects", {
    data: {
      idea: "A lighthouse keeper opens a door and hears an unexpected message.",
      kind: "drama",
      target_seconds: 20,
      orientation: "landscape",
      backend: "demo",
      idempotency_key: `sound-effects-browser-${Date.now()}`,
    },
  });
  expect(created.status()).toBe(201);
  const project = await created.json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${project.id}`)).json())
          .status,
      { timeout: 60000 },
    )
    .toBe("COMPLETED");
  const completed = await (
    await request.get(`/api/projects/${project.id}`)
  ).json();
  const stem = completed.assets.find(
    (a: { role: string }) => a.role === "sound-effects",
  );
  expect(stem.metadata.provider).toBe("procedural-effects-v1");
  expect(stem.metadata.is_mock).toBe(false);
  expect(
    completed.assets.find((a: { role: string }) => a.role === "export").metadata
      .is_mock,
  ).toBe(true);
  await page.goto(`/project/${project.id}`);
  const video = page.locator("video");
  await expect(video).toBeVisible();
  await expect
    .poll(async () =>
      video.evaluate((element: HTMLVideoElement) => element.readyState),
    )
    .toBeGreaterThan(0);
  await video.evaluate(async (element: HTMLVideoElement) => {
    element.muted = true;
    await element.play();
  });
  await expect
    .poll(async () =>
      video.evaluate((element: HTMLVideoElement) => element.currentTime),
    )
    .toBeGreaterThan(0.1);
  await video.evaluate((element: HTMLVideoElement) => element.pause());
  await page.getByRole("tab", { name: "Export", exact: true }).click();
  await expect(
    page.getByText("Original synthesized sound effects; no AI sound model.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByText("Audio stems for editing", { exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Original sound effects · WAV" })
    .click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toMatch(/\.wav$/);
  expect(await download.failure()).toBeNull();
  const bytes = await (
    await request.get(`/api/assets/${stem.id}/content`)
  ).body();
  expect(bytes.subarray(0, 4).toString()).toBe("RIFF");
  await page.getByRole("tab", { name: "Export", exact: true }).focus();
  await page.screenshot({
    path: "../ops/evidence/sound-effects-export-mobile.png",
    fullPage: true,
  });
});
