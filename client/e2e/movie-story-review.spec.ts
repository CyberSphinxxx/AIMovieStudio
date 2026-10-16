import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

test("keeping a reviewed movie preserves its cut and refuses contradictory canon", async ({
  page,
  request,
}) => {
  const repo = resolve(process.cwd(), "..");
  const path = process.env.STUDIO_CHECKPOINT_FIXTURE;
  const sample = path
    ? JSON.parse(readFileSync(path, "utf8"))
    : JSON.parse(
        execFileSync(
          resolve(repo, "tools/app-test-env/Scripts/python.exe"),
          [
            "-s",
            "-c",
            "import os,json; from pathlib import Path; from scripts.checkpoint_browser_smoke import movie_review_fixture,ROOT; print(json.dumps(movie_review_fixture(Path(os.environ.get('STUDIO_DATA', ROOT/'data')))))",
          ],
          { cwd: repo, encoding: "utf8" },
        ),
      );
  const before = await (await request.get(`/api/projects/${sample.id}`)).json();
  const movie = before.assets
    .filter(
      (asset: { role: string; metadata: { episode: number } }) =>
        asset.role === "export" && asset.metadata.episode === 2,
    )
    .at(-1);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/project/${sample.id}`);
  await page.getByRole("tab", { name: "Episodes", exact: true }).click();
  await page
    .getByRole("button")
    .filter({ has: page.getByText(sample.second_title, { exact: true }) })
    .click();
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  const review = page.getByRole("region", {
    name: "Review episode 2 movie",
    exact: true,
  });
  await review
    .getByRole("button", { name: "Review existing movie", exact: true })
    .click();
  await expect(
    review.getByRole("button", {
      name: "Check continuity and keep movie",
      exact: true,
    }),
  ).toBeDisabled();
  await review.getByRole("checkbox").check();
  await review.screenshot({
    path: "../ops/evidence/movie-story-review-form-mobile.png",
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await review
    .getByRole("button", {
      name: "Check continuity and keep movie",
      exact: true,
    })
    .click();
  await expect(page.getByRole("status")).toHaveText(
    "Movie kept. Its original cut is unchanged.",
  );
  const kept = await (await request.get(`/api/projects/${sample.id}`)).json();
  expect(kept.episodes[1].status).toBe("COMPLETED");
  expect(kept.episodes[1].script).toEqual(before.episodes[1].script);
  expect(kept.canon).toEqual(before.canon);
  expect(kept.assets).toEqual(before.assets);
  const bytes = await (
    await request.get(`/api/assets/${movie.id}/content`)
  ).body();
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(movie.sha256);
  const changed = await request.post(`/api/projects/${sample.id}/canon`, {
    data: {
      revision: kept.revision,
      event: {
        episode: 1,
        entity_id: kept.plan.characters[0].id,
        field: "alive",
        value: "false",
        reason:
          "DEVELOPMENT contradiction: the keeper dies before the second episode.",
      },
    },
  });
  expect(changed.ok()).toBe(true);
  await review
    .getByRole("button", { name: "Review existing movie", exact: true })
    .click();
  await review.getByRole("checkbox").check();
  await review
    .getByRole("button", {
      name: "Check continuity and keep movie",
      exact: true,
    })
    .click();
  await expect(review.getByRole("alert")).toContainText(
    "This cut conflicts with saved story details",
  );
  await expect(review.getByRole("alert")).toContainText("Mara");
  await expect(review.getByRole("alert")).not.toContainText(before.plan.characters[0].id);
  await expect(
    review.getByText("Technical details", { exact: true }),
  ).toBeVisible();
  await expect(review.getByRole("alert")).toContainText("dead");
  await expect(
    page.getByRole("heading", { name: "Your scene, your words.", exact: true }),
  ).toHaveCount(1);
  await expect(
    page
      .getByRole("complementary", { name: "Production progress", exact: true })
      .getByRole("heading", { name: "Needs story review.", exact: true }),
  ).toBeVisible();
  const conflicted = await (
    await request.get(`/api/projects/${sample.id}`)
  ).json();
  expect(conflicted.revision).toBe(kept.revision + 1);
  expect(conflicted.episodes[1].status).toBe("REVIEW_REQUIRED");
  expect(
    (
      await request.post(`/api/projects/${sample.id}/produce`, {
        data: { episode: 3 },
      })
    ).status(),
  ).toBe(409);
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
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../ops/evidence/movie-story-review-conflict-mobile.png",
    fullPage: true,
  });
});
