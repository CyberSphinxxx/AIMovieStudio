import { describe, expect, it } from "vitest";
import type { Shot } from "./types";
import { draftEdits } from "./draftEdits";

const shot: Shot = {
  id: "scene",
  number: 1,
  duration: 5,
  action: "A keeper opens the door.",
  camera: "Close shot",
  narration: "I remember.",
  speaker_id: "keeper",
  character_ids: ["keeper"],
  location_id: "door",
  flashback_episode: 1,
  flashback_after_shot: 2,
  continuity_note: "Before the keeper leaves the lighthouse.",
};

describe("sparse draft changes", () => {
  it("retains explicit null when returning to the current story", () => {
    expect(
      draftEdits(
        [
          {
            ...shot,
            flashback_episode: null,
            flashback_after_shot: null,
            continuity_note: "",
          },
        ],
        [shot],
      ),
    ).toEqual([
      {
        shot_id: "scene",
        flashback_episode: null,
        flashback_after_shot: null,
        continuity_note: "",
      },
    ]);
  });
  it("does not resend unchanged story assertions on a dialogue edit", () => {
    expect(
      draftEdits([{ ...shot, narration: "The door was open." }], [shot]),
    ).toEqual([{ shot_id: "scene", narration: "The door was open." }]);
  });
  it("normalizes legacy absent optional fields without phantom edits", () => {
    const legacy = {
      ...shot,
      flashback_episode: undefined,
      flashback_after_shot: undefined,
      continuity_note: undefined,
    };
    expect(
      draftEdits(
        [
          {
            ...legacy,
            flashback_episode: null,
            flashback_after_shot: null,
            continuity_note: "",
          },
        ],
        [legacy],
      ),
    ).toEqual([]);
  });
  it("matches scene identities when order differs and preserves setup zero", () => {
    const other = { ...shot, id: "other" };
    expect(
      draftEdits([other, { ...shot, flashback_after_shot: 0 }], [shot, other]),
    ).toEqual([{ shot_id: "scene", flashback_after_shot: 0 }]);
  });
});
