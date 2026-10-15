import { test, expect } from "@playwright/test";

let defaults: Record<string, unknown> | undefined;
test.afterEach(async ({ request }) => {
  if (defaults) {
    expect(
      (await request.patch("/api/settings", { data: defaults })).ok(),
    ).toBe(true);
    defaults = undefined;
  }
});

test("balanced volume persists and preserves the downloadable original mix", async ({
  page,
  request,
}) => {
  defaults = await (await request.get("/api/settings")).json();
  await page.goto("/settings");
  await expect(
    page.getByRole("button", { name: "Save settings", exact: true }),
  ).toBeEnabled();
  const volume = page.getByRole("checkbox", {
    name: "Balance volume in new movies",
  });
  await volume.uncheck();
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.getByText("Settings saved.", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/settings")).json()).balanced_audio,
  ).toBe(false);
  await page.reload();
  await expect(volume).not.toBeChecked();
  await volume.check();
  await page
    .getByRole("combobox", { name: "Soundtrack", exact: true })
    .selectOption("none");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.getByText("Settings saved.", { exact: true }),
  ).toBeVisible();
  const created = await request.post("/api/projects", {
    data: {
      idea: "An explorer notices a light beyond a quiet harbor.",
      kind: "clip",
      target_seconds: 5,
      backend: "demo",
      orientation: "portrait",
      idempotency_key: `balanced-volume-browser-${Date.now()}`,
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
  const movie = completed.assets.find(
    (asset: { role: string }) => asset.role === "export",
  );
  const premix = completed.assets.find(
    (asset: { role: string }) => asset.role === "unbalanced-mix",
  );
  expect(movie.metadata.loudness.method).toBe("balanced-audio-v1");
  expect(movie.metadata.loudness.output.true_peak_dbtp).toBeLessThanOrEqual(
    -1.9,
  );
  expect(movie.metadata.is_mock).toBe(true);
  expect(premix.metadata.is_mock).toBe(false);
  await page.goto(`/project/${project.id}`);
  await page.getByRole("tab", { name: "Export", exact: true }).click();
  await expect(
    page.getByText("Volume balanced for playback.", { exact: false }),
  ).toBeVisible();
  await page.getByText("Audio stems for editing", { exact: true }).click();
  const downloading = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Mix before volume balancing · WAV" })
    .click();
  const download = await downloading;
  expect(download.suggestedFilename()).toMatch(/\.wav$/);
  expect(await download.failure()).toBeNull();
  expect(
    (await (await request.get(`/api/assets/${premix.id}/content`)).body())
      .subarray(0, 4)
      .toString(),
  ).toBe("RIFF");
});
