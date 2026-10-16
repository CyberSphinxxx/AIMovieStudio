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
  await expect(page.getByRole("link", { name: "Skip to workspace", exact: true })).not.toBeFocused();
  await page.screenshot({
    path: "../ops/evidence/story-checkpoint-shots-mobile.png",
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
    path: "../ops/evidence/story-checkpoint-edited-mobile.png",
    fullPage: true,
  });
});
