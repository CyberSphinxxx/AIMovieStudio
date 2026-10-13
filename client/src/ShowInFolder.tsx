import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { api } from "./types";

export function ShowInFolder({ assetId }: { assetId: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function show() {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await api(`/assets/${assetId}/show-in-folder`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMessage("File Explorer requested for your saved MP4.");
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Folder could not be opened. Download the MP4 instead.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="show-in-folder">
      <button className="secondary" disabled={busy} onClick={() => void show()}>
        <FolderOpen size={16} /> {busy ? "Opening folder…" : "Show in folder"}
      </button>
      {message && (
        <p className="muted" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
