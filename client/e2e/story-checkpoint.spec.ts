import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("saved flashback checkpoints remain clear while editing a mobile draft", async ({
  page,
  request,
}) => {
  const path = process.env.STUDIO_CHECKPOINT_FIXTURE;
  const repo = resolve(process.cwd(), "..");
  const fixture = path
    ? JSON.parse(readFileSync(path, "utf8"))
    : JSON.parse(
        execFileSync(
          resolve(repo, "tools/app-test-env/Scripts/python.exe"),
          [
            "-s",
            "-c",
            "import os,json; from pathlib import Path; from scripts.checkpoint_browser_smoke import fixture,ROOT; print(json.dumps(fixture(Path(os.environ.get('STUDIO_DATA', ROOT/'data')))))",
          ],
          { cwd: repo, encoding: "utf8" },
        ),
      );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/project/${fixture.id}`);
  await expect(
    page.getByText("Development demo", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Episodes", exact: true }).click();
  await page
    .getByRole("button")
    .filter({ has: page.getByText(fixture.second_title, { exact: true }) })
    .click();
  await page.getByRole("tab", { name: "Shots", exact: true }).click();
  for (const moment of [
    "before the episode begins",
    "before the first shot, after setup",
    "after shot 1",
  ]) {
    await expect(
      page.getByText(`Flashback · Episode 1 · ${moment}`, { exact: true }),
    ).toBeVisible();
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(
    page.getByRole("link", { name: "Skip to workspace", exact: true }),
  ).not.toBeFocused();
  await page.screenshot({
    path: "../ops/evidence/story-time-shots-mobile.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  await page
    .getByRole("button", { name: "Edit saved draft", exact: true })
    .click();
  await expect(
    page.getByText("Flashback · Episode 1 · after shot 1", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Spoken line 3", { exact: true })
    .fill("I remember the door opening.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Draft saved. Previous text is retained in story history.",
  );
  const saved = await (await request.get(`/api/projects/${fixture.id}`)).json();
  expect(saved.episodes[0].script).toEqual(fixture.first_script);
  expect(saved.episodes[1].script.shots[2].flashback_after_shot).toBe(1);
  expect(saved.episodes[1].script.screenplay).toContain(
    "Flashback — Episode 1, after shot 1.",
  );
  await page
    .getByRole("button", { name: "Edit saved draft", exact: true })
    .click();
  await page.getByText("Story time for shot 3", { exact: true }).click();
  await page.getByLabel("Earlier moment 3", { exact: true }).selectOption("0");
  await page
    .getByLabel("Continuity explanation 3", { exact: true })
    .fill("Remembering the setup before the keeper opens the door.");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../ops/evidence/story-time-controls-mobile.png",
    fullPage: true,
  });
  await page.getByText("Story time for shot 3", { exact: true }).locator("..").screenshot({ path: "../ops/evidence/story-time-controls-detail.png" });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Draft saved. Previous text is retained in story history.",
  );
  const setup = await (await request.get(`/api/projects/${fixture.id}`)).json();
  expect(setup.episodes[1].script.shots[2].flashback_after_shot).toBe(0);
  expect(setup.episodes[1].script.screenplay).toContain(
    "before the first shot, after setup",
  );
  await page
    .getByRole("button", { name: "Edit saved draft", exact: true })
    .click();
  await page.getByText("Story time for shot 3", { exact: true }).click();
  await page
    .getByLabel("Story episode 3", { exact: true })
    .selectOption("current");
  await expect(
    page.getByLabel("Earlier moment 3", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Draft saved. Previous text is retained in story history.",
  );
  const current = await (
    await request.get(`/api/projects/${fixture.id}`)
  ).json();
  expect(current.episodes[0].script).toEqual(fixture.first_script);
  expect(current.episodes[1].script.shots[2]).toMatchObject({
    flashback_episode: null,
    flashback_after_shot: null,
    continuity_note: "",
  });
  expect(
    current.episodes[1].script.shots.map(
      (shot: { id: string; duration: number }) => ({
        id: shot.id,
        duration: shot.duration,
      }),
    ),
  ).toEqual(
    saved.episodes[1].script.shots.map(
      (shot: { id: string; duration: number }) => ({
        id: shot.id,
        duration: shot.duration,
      }),
    ),
  );
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
    path: "../ops/evidence/story-time-edited-mobile.png",
    fullPage: true,
  });
});
