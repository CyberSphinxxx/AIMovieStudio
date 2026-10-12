import { useRef, useState } from "react";
import { api } from "./types";
import type { Episode, Project, Shot } from "./types";

export function DraftEditor({ project, episode, onSaved }: {
  project: Project;
  episode: Episode;
  onSaved: () => Promise<unknown>;
}) {
  const [draft, setDraft] = useState<Shot[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [history, setHistory] = useState<{ before_revision: number; screenplay: string }[] | null>(null);
  const [historyError, setHistoryError] = useState("");
  const original = useRef<Shot[]>([]);
  const revision = useRef(0);
  async function loadHistory() {
    setHistoryError("");
    try {
      const result = await api<{ revisions: { before_revision: number; screenplay: string }[] }>(`/projects/${project.id}/episodes/${episode.number}/draft-history`);
      setHistory(result.revisions);
    } catch (failure) {
      setHistoryError(failure instanceof Error ? failure.message : "History could not be loaded");
    }
  }
  const canEdit = !!episode.can_edit_draft;

  function begin() {
    original.current = episode.script!.shots;
    revision.current = project.revision;
    setDraft(episode.script!.shots.map((s) => ({ ...s })));
    setError("");
    setSaved(false);
  }

  function update(id: string, field: "action" | "camera" | "narration" | "speaker_id", value: string) {
    setDraft((current) => current!.map((s) => s.id === id ? { ...s, [field]: value } : s));
  }

  const edits = (draft || []).flatMap((s, index) => {
    const before = original.current[index];
    const changed = ["action", "camera", "narration", "speaker_id"].some((key) => s[key as keyof Shot] !== before[key as keyof Shot]);
    return changed ? [{ shot_id: s.id, action: s.action, camera: s.camera, narration: s.narration, speaker_id: s.speaker_id }] : [];
  });

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/projects/${project.id}/episodes/${episode.number}/draft`, {
        method: "PATCH",
        body: JSON.stringify({ revision: revision.current, edits }),
      });
      await onSaved();
      if (history !== null) await loadHistory();
      setDraft(null);
      setSaved(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Draft could not be saved");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="draft-editor" aria-label={`Edit episode ${episode.number} draft`}>
      <h3>Your scene, your words.</h3>
      <p className="muted">Revise a saved episode before production. Timing stays fixed; later drafts will be reviewed against your changes.</p>
      {saved && <p role="status">Draft saved. Previous text is retained in story history.</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {!draft ? (
        <>
          <button className="secondary" disabled={!canEdit} onClick={begin}>Edit saved draft</button>
          {!canEdit && <p className="muted">{episode.draft_edit_reason || "Wait for a stopped saved draft before editing."}</p>}
        </>
      ) : (
        <form onSubmit={(event) => void save(event)}>
          <fieldset disabled={busy}>
            <legend>Episode {episode.number} scenes</legend>
            {draft.map((shot) => (
              <div className="draft-scene" key={shot.id}>
                <h4>Shot {shot.number} · {shot.duration.toFixed(1)} seconds</h4>
                <label htmlFor={`action-${shot.id}`}>Scene action {shot.number}</label>
                <textarea id={`action-${shot.id}`} rows={3} required minLength={5} maxLength={1500} value={shot.action} onChange={(e) => update(shot.id, "action", e.target.value)} />
                <div className="draft-fields">
                  <div><label htmlFor={`camera-${shot.id}`}>Camera {shot.number}</label>
                    <input id={`camera-${shot.id}`} required minLength={3} maxLength={400} value={shot.camera} onChange={(e) => update(shot.id, "camera", e.target.value)} />
                  </div>
                  <div><label htmlFor={`speaker-${shot.id}`}>Speaker {shot.number}</label>
                    <select id={`speaker-${shot.id}`} value={shot.speaker_id} onChange={(e) => update(shot.id, "speaker_id", e.target.value)}>
                      {project.plan?.characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                </div>
                <label htmlFor={`spoken-${shot.id}`}>Spoken line {shot.number}</label>
                <textarea id={`spoken-${shot.id}`} rows={2} maxLength={600} value={shot.narration} onChange={(e) => update(shot.id, "narration", e.target.value)} />
                <small>Keep dialogue brief enough for this shot. Empty text creates atmosphere without speech.</small>
              </div>
            ))}
            <div className="draft-actions">
              <button className="primary" type="submit" disabled={!edits.length || !canEdit}>{busy ? "Saving…" : "Save draft"}</button>
              <button className="secondary" type="button" onClick={() => { setDraft(null); setError(""); }}>Discard edits</button>
            </div>
          </fieldset>
        </form>
      )}
      <details className="draft-history" onToggle={(event) => {
        if (event.currentTarget.open && history === null) void loadHistory();
      }}>
        <summary>Previous draft text</summary>
        {historyError ? <p role="alert">{historyError}</p> : history === null ? <p>Loading saved revisions…</p> : history.length ? history.map((item) => (
          <details key={item.before_revision}>
            <summary>Before revision {item.before_revision}</summary>
            <pre className="screenplay">{item.screenplay}</pre>
          </details>
        )) : <p className="muted">No earlier edits for this episode.</p>}
      </details>
    </section>
  );
}
