import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { QualityCard } from "./QualityCard";
import type { Asset, Spec } from "./types";

const SPEC: Spec = {
  idea: "A keeper watches the lighthouse beam.",
  kind: "clip",
  orientation: "portrait",
  target_seconds: 5,
  episodes: 1,
  backend: "demo",
  language: "English",
  style: "cinematic",
  idempotency_key: "test-idempotency",
};

const BASE_ASSET: Asset = {
  id: "sample-movie-asset-id",
  role: "export",
  sha256: "abc123sha",
  metadata: {
    episode: 1,
    is_mock: true,
    provider: "ffmpeg",
    width: 360,
    height: 640,
    duration: 5.0,
    dialogue_present: true,
    sound_effects_present: true,
    loudness: { status: "target_reached", method: "loudnorm" },
  },
};

describe("QualityCard component", () => {
  it("renders verified hard gates and local $0.00 cost transparency", () => {
    const movieWithEval: Asset = {
      ...BASE_ASSET,
      metadata: {
        ...BASE_ASSET.metadata,
        quality_evaluation: {
          schema_version: 1,
          evaluated_at: 1700000000,
          all_hard_gates_passed: true,
          hard_gates: [
            {
              name: "container_format",
              passed: true,
              measured: "MP4 (471613 bytes)",
              threshold: "valid MP4/MOV container > 0 bytes",
            },
            {
              name: "video_codec",
              passed: true,
              measured: "h264 (Constrained Baseline)",
              threshold: "h264",
            },
            {
              name: "pixel_format",
              passed: true,
              measured: "yuv420p",
              threshold: "yuv420p",
            },
          ],
          cinematic_review_status: "deterministic_passed",
          cinematic_review:
            "Deterministic hard gates passed; AI critic review not performed.",
          quality_tier: "mock_demo",
          cost_usd: 0.0,
          cloud_tokens_used: 0,
          warnings: ["Draft demo; abstract motion storyboard with MOCK watermark, not AI generated."],
        },
      },
    };

    const html = renderToStaticMarkup(
      createElement(QualityCard, { movie: movieWithEval, spec: SPEC }),
    );
    expect(html).toContain("Quality Inspection &amp; Hard Gates");
    expect(html).toContain("Hard gates verified");
    expect(html).toContain("$0.00");
    expect(html).toContain("100% local compute");
    expect(html).toContain("Pixel Format (YUV420p standard)");
    expect(html).toContain("Deterministic hard gates passed");
  });

  it("renders warnings and issues when hard gates fail", () => {
    const movieWithIssue: Asset = {
      ...BASE_ASSET,
      metadata: {
        ...BASE_ASSET.metadata,
        quality_evaluation: {
          schema_version: 1,
          evaluated_at: 1700000000,
          all_hard_gates_passed: false,
          hard_gates: [
            {
              name: "black_frame_check",
              passed: false,
              measured: "5.00s black",
              threshold: "< 4.80s black",
              error: "Entire movie export is solid black frames",
            },
          ],
          cinematic_review_status: "hard_gates_failed",
          cinematic_review: "Quality hard gate failed: black_frame_check",
          quality_tier: "mock_demo",
          cost_usd: 0.0,
          cloud_tokens_used: 0,
          warnings: [],
        },
      },
    };

    const html = renderToStaticMarkup(
      createElement(QualityCard, { movie: movieWithIssue, spec: SPEC }),
    );
    expect(html).toContain("Quality issue detected");
    expect(html).toContain("Entire movie export is solid black frames");
    expect(html).toContain("Video Blackout Check");
  });
});
