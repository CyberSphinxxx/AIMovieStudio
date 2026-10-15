import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("ZIP backup restores a playable project through Settings without replacing defaults", async ({
  page,
  request,
}) => {
  const repo = resolve(process.cwd(), "..");
  const fixture = JSON.parse(
    execFileSync(
      resolve(repo, ".venv/Scripts/python.exe"),
      ["-m", "scripts.backup_browser_fixture"],
      { cwd: repo, encoding: "utf8" },
    ),
  );
  const defaults = await (await request.get("/api/settings")).json();
  await page.goto("/settings");
  await page
    .getByLabel("Movie Studio backup · ZIP, up to 20 GB")
    .setInputFiles(fixture.archive);
  await page
    .getByRole("button", { name: "Restore backup", exact: true })
    .click();
  await expect(
    page.getByText("1 project restored.", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const restored = await (
    await request.get(`/api/projects/${fixture.id}`)
  ).json();
  expect(restored.status).toBe("COMPLETED");
  expect(
    Object.fromEntries(
      restored.assets.map((a: { id: string; sha256: string }) => [
        a.id,
        a.sha256,
      ]),
    ),
  ).toEqual(fixture.asset_hashes);
  expect(await (await request.get("/api/settings")).json()).toEqual(defaults);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Save settings", exact: true }),
  ).toBeEnabled({ timeout: 30000 });
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
    path: "../ops/evidence/backup-restore-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Open your Library", exact: true })
    .click();
  await page.getByLabel("Find a project").fill(fixture.title);
  await page
    .getByRole("button")
    .filter({
      has: page.getByRole("heading", { name: fixture.title, exact: true }),
    })
    .click();
  const video = page.getByLabel("Movie preview");
  await expect(video).toBeVisible();
  await video.evaluate((e: HTMLVideoElement) => e.play());
  await expect
    .poll(() => video.evaluate((e: HTMLVideoElement) => e.currentTime))
    .toBeGreaterThan(0.3);
  await video.evaluate((e: HTMLVideoElement) => e.pause());
  await page.goto("/settings");
  await page
    .getByLabel("Movie Studio backup · ZIP, up to 20 GB")
    .setInputFiles(fixture.archive);
  await page
    .getByRole("button", { name: "Restore backup", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "already exists" }),
  ).toBeVisible();
  const pending = JSON.parse(
    execFileSync(
      resolve(repo, ".venv/Scripts/python.exe"),
      ["-m", "scripts.backup_browser_fixture", "--pending"],
      { cwd: repo, encoding: "utf8" },
    ),
  );
  await page.reload();
  const operation = page.locator(`[data-restore-id="${pending.operation_id}"]`);
  await expect(
    operation.getByText(pending.title, { exact: true }),
  ).toBeVisible();
  await operation
    .getByRole("button", { name: "Resume restore", exact: true })
    .click();
  await expect(
    page.getByText("1 project restored.", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  expect(
    (await (await request.get(`/api/projects/${pending.id}`)).json()).status,
  ).toBe("COMPLETED");
});

test("saved movie exports another aspect without rewriting its story", async ({
  page,
  request,
}) => {
  await request.patch("/api/settings", {
    data: { story_model: "", speech: "none", reserve_mb: 1024 },
  });
  const created = await request.post("/api/projects", {
    data: {
      idea: "An observatory finds an old signal. Export copy test.",
      kind: "clip",
      orientation: "portrait",
      target_seconds: 5,
      episodes: 1,
      backend: "demo",
      language: "English",
      style: "Cinematic",
      idempotency_key: `copy-${Date.now()}`,
    },
  });
  expect(created.status()).toBe(201);
  const pid = (await created.json()).id;
  await page.goto(`/project/${pid}`);
  await expect(
    page.getByRole("heading", { name: "That’s a wrap." }),
  ).toBeVisible({ timeout: 90000 });
  const before = await (await request.get(`/api/projects/${pid}`)).json();
  await page.getByRole("tab", { name: "Export", exact: true }).click();
  await page
    .getByRole("button", { name: "Make Landscape · 16:9 copy", exact: true })
    .click();
  const download = page.getByRole("link", {
    name: "Download Landscape · 16:9 · MP4",
    exact: true,
  });
  await expect(download).toBeVisible({ timeout: 30000 });
  const response = await request.get((await download.getAttribute("href"))!);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toBe("video/mp4");
  const after = await (await request.get(`/api/projects/${pid}`)).json();
  expect(after.canon).toEqual(before.canon);
  expect(after.episodes).toEqual(before.episodes);
  expect(
    after.assets.filter((a: { role: string }) => a.role === "export-variant"),
  ).toHaveLength(1);
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
    path: "../ops/evidence/export-copies-mobile.png",
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("tab", { name: "Export", exact: true }).click();
  await expect(download).toBeVisible();
});

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
  await expect
    .poll(() => video.evaluate((e: HTMLVideoElement) => e.currentTime))
    .toBeGreaterThan(1);
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
  await page.getByText("Audio stems for editing", { exact: true }).click();
  const stem = page.getByRole("link", {
    name: "Original ambience · WAV",
    exact: true,
  });
  const audio = await request.get((await stem.getAttribute("href"))!);
  expect(audio.headers()["content-type"]).toBe("audio/wav");
  expect((await audio.body()).subarray(0, 4).toString()).toBe("RIFF");
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
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await expect(
    page.getByRole("heading", { name: "The studio behind the scenes." }),
  ).toBeVisible();
  await page.getByLabel("Soundtrack", { exact: true }).selectOption("windows");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved.");
});

test("season prewriting is saved and studio backup is downloadable", async ({
  page,
  request,
}) => {
  await request.patch("/api/settings", {
    data: { story_model: "", speech: "none", reserve_mb: 1024 },
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Series A complete season", exact: true })
    .click();
  await page.getByLabel("SECONDS / EPISODE").fill("5");
  await page.getByLabel("EPISODES", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Creative settings" }).click();
  await page.getByLabel("Prewrite every episode before making footage").check();
  await page
    .getByLabel("What’s your movie about?")
    .fill("Three travelers uncover a lighthouse secret over three chapters.");
  await page.getByRole("button", { name: "Create movie", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "That’s a wrap." }),
  ).toBeVisible({ timeout: 90000 });
  const id = page.url().split("/").pop();
  const result = await (await request.get(`/api/projects/${id}`)).json();
  expect(result.episodes.map((e: { script: unknown }) => !!e.script)).toEqual([
    true,
    true,
    true,
  ]);
  expect(result.canon).toHaveLength(1);
  await page.getByRole("tab", { name: "Episodes", exact: true }).click();
  await page.getByRole("button", { name: /03 Chapter 3/ }).click();
  await expect(
    page.getByRole("button", { name: "Produce episode 3" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: /02 Chapter 2/ }).click();
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  await expect(page.locator(".state-label")).toHaveText("Draft saved");
  await expect(page.locator(".screenplay").first()).not.toContainText("â");
  await page
    .getByRole("button", { name: "Edit saved draft", exact: true })
    .click();
  await page
    .getByLabel("Spoken line 1", { exact: true })
    .fill("We followed the signal home.");
  // Normal polling must preserve unsaved text.
  await page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/projects/${id}`) &&
      response.request().method() === "GET",
  );
  await page.getByRole("tab", { name: "Shots", exact: true }).click();
  await page.getByRole("tab", { name: "Story", exact: true }).click();
  await expect(page.getByLabel("Spoken line 1", { exact: true })).toHaveValue(
    "We followed the signal home.",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../ops/evidence/draft-editor-mobile.png",
    fullPage: true,
  });
  const editorA11y = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(editorA11y.violations).toEqual([]);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Draft saved. Previous text is retained in story history.",
  );
  await page.getByText("Previous draft text", { exact: true }).click();
  await page.getByText("Before revision 2", { exact: true }).click();
  await expect(page.getByText(/DEMO SCREENPLAY/).last()).toBeVisible();
  const edited = await (await request.get(`/api/projects/${id}`)).json();
  expect(edited.episodes[1].script.shots[0].narration).toBe(
    "We followed the signal home.",
  );
  expect(edited.episodes[2].status).toBe("REVIEW_REQUIRED");
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.reload();
  await page.getByRole("tab", { name: "Episodes", exact: true }).click();
  await page.getByRole("button", { name: /02 Chapter 2/ }).click();
  await page.getByRole("button", { name: "Produce episode 2" }).click();
  await expect(
    page.getByRole("heading", { name: "That’s a wrap." }),
  ).toBeVisible({ timeout: 90000 });
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByText("Graphics card", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save settings" }),
  ).toBeEnabled();
  const backup = await request.get(
    (await page
      .getByRole("link", { name: "Download studio backup" })
      .getAttribute("href"))!,
  );
  expect(backup.status()).toBe(200);
  expect(backup.headers()["content-type"]).toBe("application/zip");
  expect((await backup.body()).subarray(0, 2).toString()).toBe("PK");
  await page.screenshot({
    path: "../ops/evidence/settings-desktop.png",
    fullPage: true,
  });
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test("settings cannot overwrite saved configuration while it is loading", async ({
  page,
  request,
}) => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "GET") await gate;
    await route.continue();
  });
  await page.goto("/settings");
  await expect(
    page.getByRole("button", { name: "Save settings" }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Local story engine", { exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("Loading saved settings…", { exact: true }),
  ).toBeVisible();
  release();
  await expect(
    page.getByRole("button", { name: "Save settings" }),
  ).toBeEnabled();
  await expect(
    page.getByText("Checking your studio…", { exact: true }),
  ).toHaveCount(0);
  const saved = await (await request.get("/api/settings")).json();
  await page
    .getByLabel("Local story engine", { exact: true })
    .selectOption("cpu_1_5b");
  await page
    .getByRole("button", { name: "Refresh diagnostics", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Refresh diagnostics", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByLabel("Local story engine", { exact: true }),
  ).toHaveValue("cpu_1_5b");
  expect(await (await request.get("/api/settings")).json()).toEqual(saved);
});

for (const scenario of [
  { name: "spoken line", narration: "We reached home." },
  { name: "silent scene", narration: "" },
]) {
  test(`optional screenplay review edits a ${scenario.name} and resumes before any footage`, async ({
    page,
    request,
  }) => {
    await request.patch("/api/settings", { data: { speech: "none" } });
    await page.goto("/");
    await page.getByLabel("SECONDS", { exact: true }).fill("5");
    await page
      .getByRole("button", { name: "Creative settings", exact: true })
      .click();
    await page
      .getByLabel("Review the screenplay before making footage", {
        exact: true,
      })
      .check();
    await page
      .getByLabel("What’s your movie about?")
      .fill("A lighthouse keeper follows a signal and chooses to return home.");
    await page
      .getByRole("button", { name: "Create movie", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Resume movie", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    const id = page.url().split("/").pop();
    const paused = await (await request.get(`/api/projects/${id}`)).json();
    expect(paused.assets).toHaveLength(0);
    expect(paused.jobs[0].state).toBe("PAUSED");
    await page.getByRole("tab", { name: "Story", exact: true }).click();
    await page
      .getByRole("button", { name: "Edit saved draft", exact: true })
      .click();
    await page
      .getByLabel("Spoken line 1", { exact: true })
      .fill(scenario.narration);
    await page.getByRole("button", { name: "Save draft", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText(
      "Draft saved. Previous text is retained in story history.",
    );
    if (!scenario.narration) {
      await expect(page.getByText(/No spoken line\./)).toBeVisible();
      await page.setViewportSize({ width: 390, height: 844 });
      await expect(
        page.getByRole("link", { name: "Skip to workspace" }),
      ).not.toBeFocused();
      // A full-page capture must start at the top: a fixed offscreen skip link
      // otherwise appears inside the expanded image at the old scroll offset.
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: "../ops/evidence/silent-story-review-mobile.png",
        fullPage: true,
      });
    }
    await page
      .getByRole("button", { name: "Resume movie", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "That’s a wrap." }),
    ).toBeVisible({ timeout: 60000 });
    const finished = await (await request.get(`/api/projects/${id}`)).json();
    expect(finished.episodes[0].script.shots[0].narration).toBe(
      scenario.narration,
    );
    expect(
      finished.jobs[0].steps.some(
        (s: { state: string }) => s.state === "SUPERSEDED",
      ),
    ).toBe(true);
  });
}
