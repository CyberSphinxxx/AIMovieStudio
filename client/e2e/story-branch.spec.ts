import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { createHash } from "node:crypto";

test("an alternative story edits and renders separately while the original cut stays intact", async ({
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
  let before = await (await request.get(`/api/projects/${sample.id}`)).json();
  const originalMovie = before.assets.find(
    (asset: { role: string }) => asset.role === "export",
  );
  const movieBytes = await (
    await request.get(`/api/assets/${originalMovie.id}/content`)
  ).body();
  const originalSha = createHash("sha256").update(movieBytes).digest("hex");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/project/${sample.id}`);
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  await page.getByText("Make an alternative story", { exact: true }).click();
  await expect(page.getByText(/Nothing renders until you/)).toBeVisible();
  const changed = await request.post(`/api/projects/${sample.id}/canon`, {
    data: {
      revision: before.revision,
      event: {
        episode: 1,
        entity_id: sample.id,
        field: "outcome",
        value: "The keeper answers a second distant signal.",
        reason: "Explicit sample edit while the alternative form is open.",
      },
    },
  });
  expect(changed.ok()).toBe(true);
  await expect(
    page
      .getByRole("region", { name: "Saved continuity", exact: true })
      .getByText("The keeper answers a second distant signal."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create alternative draft", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("another window");
  await expect(page).toHaveURL(new RegExp(`/project/${sample.id}$`));
  await page.getByText("Make an alternative story", { exact: true }).click();
  await page.getByText("Make an alternative story", { exact: true }).click();
  before = await (await request.get(`/api/projects/${sample.id}`)).json();
  await page
    .getByRole("button", { name: "Create alternative draft", exact: true })
    .click();
  await expect(page).not.toHaveURL(new RegExp(`/project/${sample.id}$`));
  const identity = new URL(page.url()).pathname.split("/")[2];
  const copied = await (await request.get(`/api/projects/${identity}`)).json();
  expect(copied.jobs).toEqual([]);
  expect(copied.assets).toEqual([]);
  expect(copied.canon).toEqual([]);
  expect(copied.plan.ending).toBe(before.plan.ending);
  const progress = page.getByRole("complementary", {
    name: "Production progress",
    exact: true,
  });
  await expect(
    progress.getByRole("heading", { name: "Draft ready.", exact: true }),
  ).toBeVisible();
  await expect(progress.getByRole("progressbar")).toHaveCount(0);
  await expect(progress).toContainText("Production has not started.");
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  const editor = page.getByRole("region", {
    name: "Edit episode 1 draft",
    exact: true,
  });
  await editor
    .getByRole("button", { name: "Edit saved draft", exact: true })
    .click();
  const action = editor.getByRole("textbox", {
    name: "Scene action 1",
    exact: true,
  });
  await action.fill(
    copied.episodes[0].script.shots[0].action +
      " The keeper closes a blue notebook.",
  );
  await editor.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(editor.getByRole("status")).toContainText("Draft saved");
  expect(
    (await (await request.get(`/api/projects/${identity}`)).json()).jobs,
  ).toEqual([]);
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
  expect(
    await page
      .locator(".skip")
      .evaluate((link) => link.getBoundingClientRect().bottom),
  ).toBeLessThan(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../ops/evidence/alternative-story-draft-mobile.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await page
    .getByRole("complementary", { name: "Production progress", exact: true })
    .getByRole("button", { name: "Produce episode 1", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${identity}`)).json())
          .episodes[0].status,
      { timeout: 30_000 },
    )
    .toBe("COMPLETED");
  const after = await (await request.get(`/api/projects/${sample.id}`)).json();
  expect(after).toEqual(before);
  const retained = await (
    await request.get(`/api/assets/${originalMovie.id}/content`)
  ).body();
  expect(createHash("sha256").update(retained).digest("hex")).toBe(originalSha);
  await expect(
    page
      .getByRole("complementary", { name: "Production progress", exact: true })
      .getByRole("heading", { name: "That’s a wrap.", exact: true }),
  ).toBeVisible();
  const player = page.locator("video").first();
  await expect
    .poll(() =>
      player.evaluate((video) => (video as HTMLVideoElement).readyState),
    )
    .toBeGreaterThanOrEqual(2);
  await player.evaluate(async (video) => {
    const movie = video as HTMLVideoElement;
    movie.muted = true;
    await movie.play();
  });
  await expect
    .poll(() =>
      player.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeGreaterThan(0.2);
  await player.evaluate((video) => (video as HTMLVideoElement).pause());
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../ops/evidence/alternative-story-movie-mobile.png",
    fullPage: true,
  });
});
