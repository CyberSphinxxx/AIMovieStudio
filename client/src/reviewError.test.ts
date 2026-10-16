import { describe, expect, it } from "vitest";
import { reviewError } from "./reviewError";

describe("retained movie review errors", () => {
  it("names characters and locations while keeping the actual conflict", () => {
    const hero = "11111111-1111-1111-1111-111111111111";
    const room = "22222222-2222-2222-2222-222222222222";
    const message = `CANON_CONFLICT: Shot 1: ${hero} is dead at ${room}. Canon evidence: 33333333-3333-3333-3333-333333333333.`;
    expect(
      reviewError(message, {
        characters: [{ id: hero, name: "Mara" }],
        locations: [{ id: room, name: "Lighthouse" }],
      }),
    ).toBe(
      "This cut conflicts with saved story details. Shot 1: Mara is dead at Lighthouse.",
    );
    expect(message).toContain("CANON_CONFLICT");
  });

  it("keeps actionable non-continuity errors unchanged", () => {
    const message =
      "Story changed in another window. Reload before reviewing this movie.";
    expect(reviewError(message, null)).toBe(message);
  });

  it("does not expose unknown identity strings in the main message", () => {
    expect(
      reviewError(
        "Saved fact ABCDEF12-1111-1111-1111-111111111111 differs from this screenplay",
        null,
      ),
    ).toBe("Saved fact a saved story item differs from this screenplay");
  });
});
