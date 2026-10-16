import { useRef, useState } from "react";
import { api } from "./types";
import type { Project } from "./types";

type Fact = Project["canon"][number];

export function factDescription(project: Project, fact: Fact) {
  const character = (id: string) =>
    project.plan?.characters.find((item) => item.id === id)?.name ??
    "Unknown character";
  if (fact.field === "alive")
    return `${character(fact.entity_id)} · ${fact.value === "false" ? "died" : "alive"}`;
  if (fact.field === "knowledge")
    return `${character(fact.entity_id)} learned: ${fact.value}`;
  if (fact.field === "location")
    return `${character(fact.entity_id)} · ${project.plan?.locations.find((item) => item.id === fact.value)?.name ?? "Unknown location"}`;
  if (fact.field === "prop_owner")
    return `${project.plan?.props?.find((item) => item.id === fact.entity_id)?.name ?? "Story prop"} · held by ${character(fact.value)}`;
  return fact.value;
}

function momentValue(fact: Fact) {
  return fact.timing_status === "episode_end"
    ? "end"
    : fact.timing_status === "after_shot" && fact.after_shot != null
      ? String(fact.after_shot)
      : "unknown";
}

export function factMoment(fact: Fact) {
  const moment = momentValue(fact);
  return moment === "end"
    ? "At the episode end"
    : moment === "unknown"
      ? "Timing not recorded"
      : moment === "0"
        ? "Before the first shot, after setup"
        : `After shot ${moment}`;
}

function TimingEditor({
  project,
  fact,
  onSaved,
}: {
  project: Project;
  fact: Fact;
  onSaved: () => Promise<unknown>;
}) {
  const [moment, setMoment] = useState(momentValue(fact));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const revision = useRef(project.revision);
  const source = project.episodes.find(
    (episode) => episode.number === fact.episode,
  );
  const count = source?.script?.shots.length ?? 0;
  const running = project.jobs.some(
    (job) =>
      ["RUNNING", "QUEUED", "PAUSED", "WAITING_RESOURCES"].includes(
        job.state,
      ) || job.steps.some((step) => step.state === "RUNNING"),
  );
  const reviewed =
    source?.script &&
    ["COMPLETED", "DRAFTED", "SCRIPTED"].includes(source.status);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (moment === "unknown") return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await api(`/projects/${project.id}/canon/${fact.id}/timing`, {
        method: "POST",
        body: JSON.stringify({
          revision: revision.current,
          after_shot: moment === "end" ? null : Number(moment),
          reason,
        }),
      });
      await onSaved();
      setSaved(true);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Timing could not be saved",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details
      className="draft-history"
      onToggle={(event) => {
        if (event.currentTarget.open) {
          revision.current = project.revision;
          setMoment(momentValue(fact));
          setReason("");
          setError("");
          setSaved(false);
        }
      }}
    >
      <summary>Correct timing</summary>
      <p className="muted">
        The original fact and earlier movies are retained. Later episodes will
        need story review.
      </p>
      {!reviewed ? (
        <p>Review the source episode before assigning a moment.</p>
      ) : running ? (
        <p>Finish or cancel the active production before correcting timing.</p>
      ) : (
        <form
          aria-label={`Timing correction for ${factDescription(project, fact)}`}
          onSubmit={(event) => void save(event)}
        >
          <fieldset disabled={busy || saved}>
            <legend>Episode {fact.episode} timing</legend>
            <label htmlFor={`fact-moment-${fact.id}`}>When this happened</label>
            <select
              id={`fact-moment-${fact.id}`}
              required
              value={moment}
              onChange={(event) => setMoment(event.target.value)}
            >
              <option value="unknown" disabled>
                Choose a moment
              </option>
              <option value="0">Before the first shot, after setup</option>
              {Array.from({ length: count }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  After shot {index + 1}
                </option>
              ))}
              <option value="end">At the episode end</option>
            </select>
            <label htmlFor={`fact-reason-${fact.id}`}>
              Why this timing is correct
            </label>
            <textarea
              id={`fact-reason-${fact.id}`}
              required
              minLength={8}
              maxLength={500}
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <button
              className="secondary"
              type="submit"
              disabled={moment === "unknown" || reason.trim().length < 8}
            >
              {busy ? "Saving timing…" : "Save timing"}
            </button>
          </fieldset>
        </form>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status">Timing saved. Later episodes need story review.</p>
      )}
    </details>
  );
}

export function CanonTimeline({
  project,
  onSaved,
}: {
  project: Project;
  onSaved: () => Promise<unknown>;
}) {
  return (
    <section aria-label="Saved continuity">
      {!project.canon.length ? (
        <p className="muted">
          Episode outcomes commit after the export passes validation.
        </p>
      ) : (
        project.canon.map((fact) =>
          fact.field === "outcome" ? (
            <p key={fact.id}>
              Episode {fact.episode} · {fact.value}
            </p>
          ) : (
            <article className="draft-editor" key={fact.id}>
              <p>
                Episode {fact.episode} · {factDescription(project, fact)}
              </p>
              <p className="muted">{factMoment(fact)}</p>
              <small>{fact.reason}</small>
              <TimingEditor project={project} fact={fact} onSaved={onSaved} />
            </article>
          ),
        )
      )}
    </section>
  );
}
