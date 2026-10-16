import type { Shot } from "./types";

const fields = [
  "action",
  "camera",
  "narration",
  "speaker_id",
  "flashback_episode",
  "flashback_after_shot",
  "continuity_note",
] as const;

function value(shot: Shot, field: (typeof fields)[number]) {
  if (field === "flashback_episode" || field === "flashback_after_shot")
    return shot[field] ?? null;
  if (field === "continuity_note") return shot[field] ?? "";
  return shot[field];
}

export function draftEdits(draft: Shot[], original: Shot[]) {
  const sources = new Map(original.map((shot) => [shot.id, shot]));
  return draft.flatMap((shot) => {
    const before = sources.get(shot.id);
    if (!before)
      throw new Error("The saved scenes changed. Reload before editing.");
    const edits = fields.filter(
      (field) => value(shot, field) !== value(before, field),
    );
    return edits.length
      ? [
          {
            shot_id: shot.id,
            ...Object.fromEntries(
              edits.map((field) => [field, value(shot, field)]),
            ),
          },
        ]
      : [];
  });
}
