import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("legacy fact timing can be corrected without replacing saved scenes", async ({
  page,
  request,
}) => {
  const repo = resolve(process.cwd(), "..");
  const path = process.env.STUDIO_CHECKPOINT_FIXTURE;
  const fixture = path
    ? JSON.parse(readFileSync(path, "utf8"))
    : JSON.parse(
        execFileSync(
          resolve(repo, "tools/app-test-env/Scripts/python.exe"),
          [
            "-s",
            "-c",
            "import os,json; from pathlib import Path; from scripts.checkpoint_browser_smoke import fixture,ROOT; print(json.dumps(fixture(Path(os.environ.get('STUDIO_DATA', ROOT/'data')),legacy_timing=True)))",
          ],
          { cwd: repo, encoding: "utf8" },
        ),
      );
  const before = await (
    await request.get(`/api/projects/${fixture.id}`)
  ).json();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/project/${fixture.id}`);
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  const continuity = page.getByRole("region", {
    name: "Saved continuity",
    exact: true,
  });
  await expect(
    continuity.getByText("Timing not recorded", { exact: true }),
  ).toBeVisible();
  await continuity.getByText("Correct timing", { exact: true }).click();
  const form = continuity.getByRole("form");
  await form
    .getByLabel("When this happened", { exact: true })
    .selectOption("2");
  await form
    .getByLabel("Why this timing is correct", { exact: true })
    .fill("The keeper recognizes the ship after the second shot.");
  await form.screenshot({
    path: "../ops/evidence/canon-timing-form-mobile.png",
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await form.getByRole("button", { name: "Save timing", exact: true }).click();
  await expect(continuity.getByRole("status")).toHaveText(
    "Timing saved. Later episodes need story review.",
  );
  await expect(
    continuity.getByRole("paragraph").filter({ hasText: /^After shot 2$/ }),
  ).toBeVisible();
  const saved = await (await request.get(`/api/projects/${fixture.id}`)).json();
  expect(saved.canon[0]).toMatchObject({
    id: before.canon[0].id,
    entity_id: before.canon[0].entity_id,
    value: before.canon[0].value,
    reason: before.canon[0].reason,
    revision: 1,
    after_shot: 2,
  });
  expect(saved.episodes[0].script).toEqual(before.episodes[0].script);
  expect(saved.episodes[1].script).toEqual(before.episodes[1].script);
  expect(saved.episodes[1].status).toBe("REVIEW_REQUIRED");
  expect(saved.jobs).toEqual(before.jobs);
  await page.reload();
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  await continuity.getByText("Correct timing", { exact: true }).click();
  // An external edit while the form stays open must not refresh its captured revision.
  const external = await request.post(
    `/api/projects/${fixture.id}/canon/${saved.canon[0].id}/timing`,
    {
      data: {
        revision: saved.revision,
        after_shot: 0,
        reason: "The opening setup already establishes this recognition.",
      },
    },
  );
  expect(external.ok()).toBe(true);
  await expect(
    continuity
      .getByRole("paragraph")
      .filter({ hasText: /^Before the first shot, after setup$/ }),
  ).toBeVisible({ timeout: 10000 });
  await form
    .getByLabel("When this happened", { exact: true })
    .selectOption("1");
  await form
    .getByLabel("Why this timing is correct", { exact: true })
    .fill("This form still has the previous story revision.");
  await form.getByRole("button", { name: "Save timing", exact: true }).click();
  await expect(continuity.getByRole("alert")).toContainText(
    "Story changed in another window",
  );
  const final = await (await request.get(`/api/projects/${fixture.id}`)).json();
  expect(final.revision).toBe(3);
  expect(final.canon[0].after_shot).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../ops/evidence/canon-timing-conflict-mobile.png",
    fullPage: true,
  });
});
