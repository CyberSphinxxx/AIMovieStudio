import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("home is usable at target viewports and keyboard focus is visible", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Every movie starts with one idea." }),
  ).toBeVisible();
  for (const [width, height] of [
    [320, 800],
    [360, 800],
    [390, 844],
    [768, 1024],
    [1366, 768],
    [1920, 1080],
  ]) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `../ops/evidence/home-${width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to workspace" }),
  ).toBeFocused();
  await page
    .getByLabel("What’s your movie about?")
    .fill("A keeper follows a strange signal across the sea.");
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("one idea to playable demo MP4, persisted story, shots, and downloads", async ({
  page,
  request,
}) => {
  await request.patch("/api/settings", {
    data: { story_model: "", speech: "none", reserve_mb: 1024 },
  });
  await page.goto("/");
  await page
    .getByLabel("What’s your movie about?")
    .fill(
      `A lighthouse keeper discovers a message from the future. Test ${Date.now()}.`,
    );
  await page.getByRole("button", { name: "Create movie", exact: true }).click();
  await expect(page).toHaveURL(/\/project\//);
  await expect(
    page.getByText("Development demo", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "That’s a wrap." }),
  ).toBeVisible({ timeout: 90000 });
  const video = page.getByLabel("Movie preview");
  await expect(video).toBeVisible();
  await video.evaluate((e: HTMLVideoElement) => e.play());
  await expect.poll(() => video.evaluate((e: HTMLVideoElement) => e.currentTime)).toBeGreaterThan(1);
  await video.evaluate((e: HTMLVideoElement) => e.pause());
  await expect
    .poll(() => video.evaluate((e: HTMLVideoElement) => e.duration))
    .toBeCloseTo(30, 0);
  await page.screenshot({
    path: "../ops/evidence/studio-export-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "The story bible" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Episode 1 · The secret is resolved and the travelers return home.",
    ),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Cast & World" }).click();
  await expect(
    page.getByRole("heading", { name: "Mara", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Shots", exact: true }).click();
  await expect(page.getByLabel("Shot 1", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Export", exact: true }).click();
  await expect(page.getByRole("link", { name: "Download MP4" })).toBeVisible();
  const response = await request.get(
    (await page
      .getByRole("link", { name: "Download MP4" })
      .getAttribute("href")) || "",
  );
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toBe("video/mp4");
  await page.reload();
  await expect(page.getByLabel("Movie preview")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../ops/evidence/studio-export-mobile.png",
    fullPage: true,
  });
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});

test("real request fails honestly and settings are actionable", async ({
  page,
  request,
}) => {
  await request.patch("/api/settings", {
    data: { story_model: "", speech: "none", reserve_mb: 1024 },
  });
  await page.goto("/");
  await page
    .getByLabel("What’s your movie about?")
    .fill("A traveler searches for the last surviving garden.");
  await page.getByRole("button", { name: "Creative settings" }).click();
  await page.getByLabel("Production backend").selectOption("local");
  await page.getByRole("button", { name: "Create movie", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("MISSING_MODEL");
  await expect(
    page.getByRole("button", { name: "Retry safely" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../ops/evidence/missing-model.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "The studio behind the scenes." }),
  ).toBeVisible();
  await page.getByLabel("Soundtrack", { exact: true }).selectOption("windows");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved.");
});
