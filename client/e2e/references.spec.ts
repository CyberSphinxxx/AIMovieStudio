import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";

test("reference views retain originals and pin the chosen view only in new episode shots", async ({
  page,
  request,
}) => {
  const defaults = await (await request.get("/api/settings")).json();
  try {
    await request.patch("/api/settings", { data: { speech: "none" } });
    const response = await request.post("/api/projects", {
      data: {
        idea: "A lighthouse discovers a new shore. Reference continuity development test.",
        kind: "series",
        orientation: "portrait",
        target_seconds: 5,
        episodes: 2,
        backend: "demo",
        language: "English",
        style: "Cinematic",
        idempotency_key: `ref-${Date.now()}`,
      },
    });
    expect(response.status()).toBe(201);
    const pid = (await response.json()).id;
    const read = async () => (await request.get(`/api/projects/${pid}`)).json();
    await page.goto(`/project/${pid}`);
    await expect(
      page.getByRole("heading", { name: "That’s a wrap." }),
    ).toBeVisible({ timeout: 90000 });
    const before = await read();
    const entity = before.plan.characters[0];
    const original = before.assets.find(
      (a: { role: string; metadata: { entity_id?: string } }) =>
        a.role === "reference" && a.metadata.entity_id === entity.id,
    );
    await page.getByRole("tab", { name: "Cast & World", exact: true }).click();
    const card = page
      .locator("article.entity")
      .filter({
        has: page.getByRole("heading", { name: entity.name, exact: true }),
      });
    await card.getByText("Reference views", { exact: true }).click();
    await card
      .getByRole("button", {
        name: `Create Side profile reference for ${entity.name}`,
        exact: true,
      })
      .click();
    const candidateButton = card.getByRole("button", {
      name: `Use Side profile · 2 reference for ${entity.name}`,
      exact: true,
    });
    await expect(candidateButton).toBeEnabled({ timeout: 30000 });
    const generated = await read();
    const candidate = generated.assets.find(
      (a: { role: string; metadata: { entity_id?: string } }) =>
        a.role === "reference-variant" && a.metadata.entity_id === entity.id,
    );
    expect(generated.reference_choices[entity.id].asset_id).toBe(original.id);
    await candidateButton.click();
    await expect(
      card.getByRole("button", {
        name: `Current Side profile · 2 reference for ${entity.name}`,
        exact: true,
      }),
    ).toBeDisabled();
    const chosen = await read();
    expect(chosen.reference_choices[entity.id].asset_id).toBe(candidate.id);
    expect(chosen.canon).toEqual(before.canon);
    expect(chosen.episodes).toEqual(before.episodes);
    expect(chosen.revision).toBe(before.revision);
    expect(
      chosen.assets.find((a: { role: string }) => a.role === "export").sha256,
    ).toBe(
      before.assets.find((a: { role: string }) => a.role === "export").sha256,
    );
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
    await page.getByRole("heading", { name: "Cast & world", exact: true }).click();
    await page.screenshot({
      path: "../ops/evidence/reference-views-mobile.png",
      fullPage: true,
    });
    const originalResponse = await request.get(
      `/api/assets/${original.id}/content`,
    );
    expect(
      createHash("sha256")
        .update(await originalResponse.body())
        .digest("hex"),
    ).toBe(original.sha256);
    await page.getByRole("tab", { name: "Episodes", exact: true }).click();
    await page.locator(".episode-list button").nth(1).click();
    await page
      .getByRole("button", { name: "Produce episode 2", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "That’s a wrap." }),
    ).toBeVisible({ timeout: 60000 });
    const second = await read();
    const frames = second.assets.filter(
      (a: { role: string; metadata: { episode: number } }) =>
        a.role === "keyframe" && a.metadata.episode === 2,
    );
    expect(frames[0].metadata.parent_asset_ids).toContain(candidate.id);
    expect(frames[0].metadata.parent_asset_ids).not.toContain(original.id);
    expect(second.canon.slice(0, before.canon.length)).toEqual(before.canon);
    await page.reload();
    await page.getByRole("tab", { name: "Cast & World", exact: true }).click();
    await card.getByText("Reference views", { exact: true }).click();
    await expect(
      card.getByRole("button", {
        name: `Current Side profile · 2 reference for ${entity.name}`,
        exact: true,
      }),
    ).toBeDisabled();
    // Requests made while looking at an earlier episode switch controls to the actual latest job.
    await card
      .getByRole("button", {
        name: `Create Full body reference for ${entity.name}`,
        exact: true,
      })
      .click();
    await expect(
      card.getByRole("button", {
        name: `Use Full body · 3 reference for ${entity.name}`,
        exact: true,
      }),
    ).toBeEnabled({ timeout: 30000 });
    await expect(
      page.getByText("5 SECONDS / EPISODE 2", { exact: false }),
    ).toBeVisible();
    expect((await read()).reference_choices[entity.id].asset_id).toBe(
      candidate.id,
    );
  } finally {
    await request.patch("/api/settings", { data: defaults });
  }
});
