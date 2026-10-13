import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";

test("another take publishes a playable cut with original downloads and pinned story", async ({
  page,
  request,
}) => {
  const defaults = await (await request.get("/api/settings")).json();
  try {
    await request.patch("/api/settings", { data: { speech: "none" } });
    const created = await request.post("/api/projects", {
      data: {
        idea: "A lighthouse keeps an old promise. Retake development test.",
        kind: "drama",
        orientation: "portrait",
        target_seconds: 10,
        episodes: 1,
        backend: "demo",
        language: "English",
        style: "Cinematic",
        idempotency_key: `retake-${Date.now()}`,
      },
    });
    expect(created.status()).toBe(201);
    const pid = (await created.json()).id;
    const read = async () => (await request.get(`/api/projects/${pid}`)).json();
    await page.goto(`/project/${pid}`);
    await expect(
      page.getByRole("heading", { name: "That’s a wrap." }),
    ).toBeVisible({ timeout: 90000 });
    const before = await read();
    const original = before.assets.find(
      (a: { role: string }) => a.role === "export",
    );
    await page.getByRole("tab", { name: "Export", exact: true }).click();
    await page
      .getByRole("button", { name: "Make Landscape · 16:9 copy", exact: true })
      .click();
    await expect(
      page.getByRole("link", {
        name: "Download Landscape · 16:9 · MP4",
        exact: true,
      }),
    ).toBeVisible({ timeout: 30000 });
    await page.getByRole("tab", { name: "Shots", exact: true }).click();
    await page
      .getByRole("button", { name: "Another take for shot 1", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (await read()).assets.filter(
            (a: { role: string }) => a.role === "export-edition",
          ).length,
        { timeout: 45000 },
      )
      .toBe(1);
    await expect(
      page.getByRole("button", {
        name: "Another take for shot 1",
        exact: true,
      }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Another take for shot 1", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (await read()).assets.filter(
            (a: { role: string }) => a.role === "export-edition",
          ).length,
        { timeout: 45000 },
      )
      .toBe(2);
    await expect(
      page.getByRole("button", {
        name: "Another take for shot 1",
        exact: true,
      }),
    ).toBeDisabled();
    const after = await read();
    expect(after.canon).toEqual(before.canon);
    expect(after.episodes).toEqual(before.episodes);
    expect(after.revision).toBe(before.revision);
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
    await page.screenshot({
      path: "../ops/evidence/retake-shots-mobile.png",
      fullPage: true,
    });
    await page.getByRole("tab", { name: "Overview", exact: true }).click();
    const movie = page.getByLabel("Movie preview");
    const latest = after.assets
      .filter((a: { role: string }) => a.role === "export-edition")
      .at(-1);
    await expect(movie).toHaveAttribute(
      "src",
      `/api/assets/${latest.id}/content`,
    );
    await movie.evaluate((v: HTMLVideoElement) => v.play());
    await expect
      .poll(() => movie.evaluate((v: HTMLVideoElement) => v.currentTime))
      .toBeGreaterThan(0.3);
    await movie.evaluate((v: HTMLVideoElement) => v.pause());
    await page.getByRole("tab", { name: "Export", exact: true }).click();
    await expect(
      page.getByText("Episode 1 · Cut 3 · MP4", { exact: true }),
    ).toBeVisible();
    await page.getByText("Earlier movie cuts", { exact: true }).click();
    const originalLink = page.getByRole("link", {
      name: "Download cut 1 · MP4",
      exact: true,
    });
    const response = await request.get(
      (await originalLink.getAttribute("href"))!,
    );
    expect(
      createHash("sha256")
        .update(await response.body())
        .digest("hex"),
    ).toBe(original.sha256);
    await expect(
      page.getByRole("link", { name: "Download cut 2 · MP4", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", {
        name: "Download cut 1 · landscape copy · MP4",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Make Landscape · 16:9 copy", exact: true })
      .click();
    await expect(
      page.getByRole("link", {
        name: "Download Landscape · 16:9 · MP4",
        exact: true,
      }),
    ).toBeVisible({ timeout: 30000 });
    const copied = await read();
    expect(
      copied.assets
        .filter((a: { role: string }) => a.role === "export-variant")
        .at(-1).metadata.parent_asset_ids,
    ).toEqual([latest.id]);
    await page.reload();
    await expect(page.getByLabel("Movie preview")).toHaveAttribute(
      "src",
      `/api/assets/${latest.id}/content`,
    );
  } finally {
    await request.patch("/api/settings", { data: defaults });
  }
});
