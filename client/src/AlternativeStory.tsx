import { useState } from "react";
import { api } from "./types";
import type { Project } from "./types";

export function AlternativeStory({
  project,
  onCreated,
}: {
  project: Project;
  onCreated: (id: string) => void;
}) {
  const [request, setRequest] = useState<{
    revision: number;
    idempotency_key: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!project.plan || !project.episodes.some((episode) => episode.script))
    return null;
  const active = project.jobs.some(
    (job) =>
      ["QUEUED", "RUNNING", "PAUSED", "WAITING_RESOURCES"].includes(
        job.state,
      ) || job.steps.some((step) => step.state === "RUNNING"),
  );
  async function create() {
    if (!request) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ project_id: string }>(
        `/projects/${project.id}/story-branch`,
        { method: "POST", body: JSON.stringify(request) },
      );
      onCreated(result.project_id);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Alternative story could not be saved",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details
      className="draft-editor"
      onToggle={(event) => {
        if (event.currentTarget.open) {
          setRequest(
            (previous) =>
              previous ?? {
                revision: project.revision,
                idempotency_key: crypto.randomUUID(),
              },
          );
        } else {
          setRequest(null);
          setError("");
        }
      }}
    >
      <summary>Make an alternative story</summary>
      <p>
        Open a separate draft to change a story that already has footage. Your
        original project and movies stay here.
      </p>
      <p className="muted">
        Copies the plan and saved screenplays. Existing footage, completed facts
        and manual continuity corrections are not copied. Review the new drafts;
        making footage starts again from episode 1. Nothing renders until you
        choose to produce it.
      </p>
      <button
        className="secondary"
        disabled={busy || active || !request}
        onClick={() => void create()}
      >
        {busy ? "Saving alternative…" : "Create alternative draft"}
      </button>
      {active && (
        <p className="muted">Finish or cancel active production first.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
