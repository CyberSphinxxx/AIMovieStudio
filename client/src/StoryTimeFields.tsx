import type { Episode, Shot } from "./types";

type StoryTime = Pick<
  Shot,
  "flashback_episode" | "flashback_after_shot" | "continuity_note"
>;

export function StoryTimeFields({
  shot,
  episode,
  episodes,
  onChange,
}: {
  shot: Shot;
  episode: number;
  episodes: Episode[];
  onChange: (fields: StoryTime) => void;
}) {
  const earlier = episodes.filter(
    (source) =>
      source.number < episode &&
      source.script &&
      ["COMPLETED", "DRAFTED", "SCRIPTED"].includes(source.status),
  );
  const source = earlier.find(
    (candidate) => candidate.number === shot.flashback_episode,
  );
  const count = source?.script?.shots.length ?? 0;
  const selected = shot.flashback_episode ?? null;
  return (
    <details className="draft-history">
      <summary>Story time for shot {shot.number}</summary>
      <p className="muted">
        Choose when this scene happens. Shot length stays fixed. Earlier scenes
        must agree with the saved story.
      </p>
      <label htmlFor={`time-episode-${shot.id}`}>
        Story episode {shot.number}
      </label>
      <select
        id={`time-episode-${shot.id}`}
        value={selected ?? "current"}
        onChange={(event) => {
          const number =
            event.target.value === "current"
              ? null
              : Number(event.target.value);
          onChange({
            flashback_episode: number,
            flashback_after_shot: null,
            continuity_note:
              number === null ? "" : (shot.continuity_note ?? ""),
          });
        }}
      >
        <option value="current">Current story</option>
        {selected !== null && !source && (
          <option value={selected} disabled>
            Episode {selected} · needs review
          </option>
        )}
        {earlier.map((candidate) => (
          <option key={candidate.id} value={candidate.number}>
            Flashback · Episode {candidate.number}
          </option>
        ))}
      </select>
      {selected !== null && (
        <>
          <label htmlFor={`time-moment-${shot.id}`}>
            Earlier moment {shot.number}
          </label>
          <select
            id={`time-moment-${shot.id}`}
            value={shot.flashback_after_shot ?? "start"}
            onChange={(event) =>
              onChange({
                flashback_episode: selected,
                flashback_after_shot:
                  event.target.value === "start"
                    ? null
                    : Number(event.target.value),
                continuity_note: shot.continuity_note ?? "",
              })
            }
          >
            <option value="start">Before the episode begins</option>
            {source && (
              <option value={0}>Before the first shot, after setup</option>
            )}
            {Array.from({ length: count }, (_, index) => (
              <option key={index + 1} value={index + 1}>
                After shot {index + 1}
              </option>
            ))}
            {shot.flashback_after_shot != null &&
              (!source || shot.flashback_after_shot > count) && (
                <option value={shot.flashback_after_shot} disabled>
                  After shot {shot.flashback_after_shot} · needs review
                </option>
              )}
          </select>
          <label htmlFor={`time-note-${shot.id}`}>
            Continuity explanation {shot.number}
          </label>
          <textarea
            id={`time-note-${shot.id}`}
            rows={2}
            minLength={8}
            maxLength={500}
            required
            value={shot.continuity_note ?? ""}
            onChange={(event) =>
              onChange({
                flashback_episode: selected,
                flashback_after_shot: shot.flashback_after_shot ?? null,
                continuity_note: event.target.value,
              })
            }
          />
        </>
      )}
    </details>
  );
}
