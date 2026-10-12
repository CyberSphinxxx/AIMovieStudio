import { useCallback, useEffect, useState } from "react";
import { api } from "./types";

type Operation = {
  id: string;
  state: "PREPARED" | "PUBLISHING" | "INCOMPLETE_UPLOAD";
  created: number;
  project_count: number;
  titles?: string[];
};
type Result = {
  project_ids: string[];
  project_count: number;
  paused_jobs: number;
};

export function BackupRestore() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const refresh = useCallback(async () => {
    try {
      const response = await api<{ operations: Operation[] }>(
        "/backup/restores",
      );
      setOperations(response.operations);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Unfinished restores could not be read.",
      );
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function restore(identity?: string) {
    if (!identity && !file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      let restored: Result;
      if (identity) {
        restored = await api<Result>(`/backup/restores/${identity}/resume`, {
          method: "POST",
          body: "{}",
        });
      } else {
        if (file!.size > 20 * 1024 ** 3)
          throw new Error("Choose a ZIP smaller than 20 GB.");
        const response = await fetch("/api/backup/restore", {
          method: "POST",
          headers: { "Content-Type": "application/zip" },
          body: file,
        });
        const data = await response.json().catch(() => ({
          message:
            "Studio could not be reached. Return to Settings to check the restore.",
        }));
        if (!response.ok) throw new Error(data.message);
        restored = data as Result;
      }
      setResult(restored);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Restore could not finish. Keep your original ZIP.",
      );
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  async function discard(identity: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/backup/restores/${identity}/discard`, {
        method: "POST",
        body: "{}",
      });
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Partial upload could not be discarded.",
      );
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  return (
    <div className="provider-config">
      <h3>Restore projects from a backup</h3>
      <p className="muted">
        Adds missing projects to your Library. Existing projects and defaults
        stay intact. Unfinished productions stay paused until you review
        Settings and resume them. Keep your original ZIP.
      </p>
      <label htmlFor="studio-backup-file">
        Movie Studio backup · ZIP, up to 20 GB
      </label>
      <input
        id="studio-backup-file"
        type="file"
        accept=".zip,application/zip"
        disabled={busy}
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null);
          setResult(null);
          setError("");
        }}
      />
      <button
        type="button"
        className="secondary"
        disabled={busy || !file}
        onClick={() => void restore()}
      >
        {busy ? "Restoring…" : "Restore backup"}
      </button>
      {busy && (
        <p role="status">
          Copying and checking saved projects. Large backups take longer. If
          this page closes, return to Settings to check or resume.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div role="status">
          <p>
            {result.project_count}{" "}
            {result.project_count === 1
              ? "project restored"
              : "projects restored"}
            .
            {result.paused_jobs > 0 &&
              ` ${result.paused_jobs} unfinished ${result.paused_jobs === 1 ? "production stays" : "productions stay"} paused.`}
          </p>
          <a href="/projects">Open your Library</a>
        </div>
      )}
      {operations.length > 0 && (
        <div>
          <h4>Unfinished restores</h4>
          {operations.map((operation) => (
            <div key={operation.id} data-restore-id={operation.id}>
              {operation.titles?.length ? (
                <p>{operation.titles.join(" · ")}</p>
              ) : null}
              <p>
                {operation.state === "INCOMPLETE_UPLOAD"
                  ? "Upload interrupted. Choose the original ZIP again."
                  : `${operation.project_count} saved ${operation.project_count === 1 ? "project" : "projects"} ready to restore.`}
              </p>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() =>
                  void (operation.state === "INCOMPLETE_UPLOAD"
                    ? discard(operation.id)
                    : restore(operation.id))
                }
              >
                {operation.state === "INCOMPLETE_UPLOAD"
                  ? "Discard partial upload"
                  : "Resume restore"}
              </button>
              {operation.state === "PREPARED" && (
                <button
                  type="button"
                  className="text-button"
                  disabled={busy}
                  onClick={() => void discard(operation.id)}
                >
                  Discard staged copy
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
