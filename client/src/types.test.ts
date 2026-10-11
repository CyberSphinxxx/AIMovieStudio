import { describe, it, expect, vi, afterEach } from "vitest";
import { api, stageLabel, assetUrl } from "./types";
import type { Asset } from "./types";
afterEach(() => vi.unstubAllGlobals());
describe("client API boundaries", () => {
  it("surfaces actionable server errors without masking them", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          json: async () => ({ message: "Video model missing" }),
        }),
    );
    await expect(api("/projects")).rejects.toThrow("Video model missing");
  });
  it("reports measured stages and uses asset IDs for downloads", () => {
    expect(stageLabel("FAILED")).toBe("Needs attention");
    expect(assetUrl({ id: "stable-id" } as Asset, true)).toBe(
      "/api/assets/stable-id/content?download=true",
    );
  });
});
