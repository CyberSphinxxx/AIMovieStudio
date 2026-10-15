import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const scenario of [
  {
    name: "memory",
    code: "MEMORY_BUSY",
    message: "Waiting for at least 7 GB of free memory.",
  },
  {
    name: "shared AI engine",
    code: "INFERENCE_BUSY",
    message:
      "Waiting for another Studio process to finish using the local AI engine.",
  },
]) {
  test(`waiting for ${scenario.name} explains automatic continuation and Pause stays authoritative`, async ({
    page,
    request,
  }) => {
    // Explicit UI-state fixture. The real waiting-worker/API/MP4/kill tests are
    // in test_resource_wait.py; this projection never claims native model fit.
    const created = await request.post("/api/projects", {
      data: {
        idea: "A lighthouse receives a quiet message across the harbor.",
        target_seconds: 5,
        backend: "demo",
        review_story: true,
        idempotency_key: `resource-wait-ui-${Date.now()}`,
      },
    });
    expect(created.status()).toBe(201);
    const project = await created.json();
    expect((await request.post(`/api/projects/${project.id}/pause`)).ok()).toBe(
      true,
    );
    let waiting = true;
    await page.route(`**/api/projects/${project.id}`, async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      if (waiting) {
        const job = data.jobs[0];
        const now = Date.now() / 1000;
        data.status = job.state = "WAITING_RESOURCES";
        job.error = null;
        job.resource_wait = {
          code: scenario.code,
          message: scenario.message,
          stage: "PLAN",
          since: now,
          deadline: now + 86400,
        };
      }
      await route.fulfill({ json: data });
    });
    await page.route(
      `**/api/projects/${project.id}/episodes/1/pause`,
      async (route) => {
        waiting = false;
        await route.continue();
      },
    );
    try {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`/project/${project.id}`);
      await expect(
        page.getByRole("heading", {
          name: "Waiting for your computer.",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByText(/Studio will continue automatically/),
      ).toBeVisible();
      await expect(
        page.getByText(scenario.message, { exact: false }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await page.screenshot({
        path: `../ops/evidence/resource-wait-${scenario.code.toLowerCase()}-mobile.png`,
        fullPage: true,
      });
      await page.getByRole("button", { name: "Pause", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Resume movie", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", {
          name: "Waiting for your computer.",
          exact: true,
        }),
      ).not.toBeVisible();
      expect(
        (await (await request.get(`/api/projects/${project.id}`)).json())
          .jobs[0].state,
      ).toBe("PAUSED");
    } finally {
      await request.post(`/api/projects/${project.id}/cancel`);
    }
  });
}
