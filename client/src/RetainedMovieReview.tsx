import { useState } from "react";
import { api } from "./types";
import type { Asset, Episode, Project } from "./types";
import { reviewError } from "./reviewError";

export function RetainedMovieReview({
  project,
  episode,
  movie,
  onSaved,
}: {
  project: Project;
  episode: Episode;
  movie: Asset;
  onSaved: () => Promise<unknown>;
}) {
  const [opened, setOpened] = useState<{
    revision: number;
    source: string;
  } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  if (saved && episode.status === "COMPLETED")
    return <p role="status">Movie kept. Its original cut is unchanged.</p>;
  if (
    episode.status !== "REVIEW_REQUIRED" ||
    !project.jobs.some(
      (job) => job.episode === episode.number && job.state === "SUCCEEDED",
    )
  )
    return null;
  const running = project.jobs.some(
    (job) =>
      ["QUEUED", "RUNNING", "PAUSED", "WAITING_RESOURCES"].includes(
        job.state,
      ) || job.steps.some((step) => step.state === "RUNNING"),
  );
  async function keep(event: React.FormEvent) {
    event.preventDefault();
    if (!opened || !confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api(
        `/projects/${project.id}/episodes/${episode.number}/review-movie`,
        {
          method: "POST",
          body: JSON.stringify({
            revision: opened.revision,
            source_export_id: opened.source,
            reviewed_movie: true,
          }),
        },
      );
      await onSaved();
      setSaved(true);
      setOpened(null);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Movie review could not be saved",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="draft-editor"
      aria-label={`Review episode ${episode.number} movie`}
    >
      <h3>Keep this cut after a story change?</h3>
      <p className="muted">
        Watch the existing movie and read its screenplay. Studio checks declared
        continuity and the saved media before keeping it. Your original movie
        stays available if a check fails.
      </p>
      {!opened ? (
        <button
          className="secondary"
          disabled={running}
          onClick={() => {
            setOpened({ revision: project.revision, source: movie.id });
            setConfirmed(false);
            setError("");
            setSaved(false);
          }}
        >
          Review existing movie
        </button>
      ) : (
        <form onSubmit={(event) => void keep(event)}>
          <fieldset disabled={busy || running}>
            <legend>Keep episode {episode.number}</legend>
            <label className="check-label">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />{" "}
              I reviewed this movie and its screenplay, and want to keep this
              cut.
            </label>
            <div className="draft-actions">
              <button className="primary" type="submit" disabled={!confirmed}>
                {busy ? "Checking movie…" : "Check continuity and keep movie"}
              </button>
              <button
                className="secondary"
                type="button"
                onClick={() => {
                  setOpened(null);
                  setError("");
                }}
              >
                Close review
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {running && (
        <p className="muted">
          Finish or cancel the active production before reviewing this cut.
        </p>
      )}
      {error && (
        <>
          <p role="alert" className="error">
            {reviewError(error, project.plan)}
          </p>
          <details>
            <summary>Technical details</summary>
            <p className="muted">{error}</p>
          </details>
        </>
      )}
    </section>
  );
}
