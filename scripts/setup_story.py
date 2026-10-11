"""Optional small CPU story model; no GPU runtime or system-wide installer.

Downloads stay under the repository's 1 GB model threshold; checksum from the
official model hosting LFS metadata is verified before atomic publication.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def download(url, path, max_bytes, expected_hash=None):
    if path.exists() and (
        not expected_hash or hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    ):
        return
    if shutil.disk_usage(path.parent).free < max_bytes + 1024**3:
        raise RuntimeError("Not enough disk space for the download plus 1 GB reserve")
    temporary = path.with_suffix(path.suffix + ".partial")
    h = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError("Download exceeded its approved small-file limit")
            h.update(chunk)
            output.write(chunk)
    if expected_hash and h.hexdigest() != expected_hash:
        raise RuntimeError("Model checksum does not match official metadata")
    temporary.replace(path)
    print(f"Verified {path.name}: {total} bytes, SHA256 {h.hexdigest()}", flush=True)


def main():
    target = ROOT / "tools" / "story"
    target.mkdir(parents=True, exist_ok=True)
    model = fetch_json(f"https://huggingface.co/api/models/{MODEL_REPO}/revision/{MODEL_REVISION}?blobs=true")
    item = next(s for s in model["siblings"] if s["rfilename"] == MODEL_FILE)
    print(f"CPU-only story smoke model: {MODEL_REPO}, Apache-2.0, {item['size']} bytes", flush=True)
    if item["size"] > 800 * 1024 * 1024:
        raise RuntimeError("This model now exceeds the bounded small-download budget")
    download(
        f"https://huggingface.co/{MODEL_REPO}/resolve/{model['sha']}/{MODEL_FILE}",
        target / MODEL_FILE,
        800 * 1024 * 1024,
        item["lfs"]["sha256"],
    )
    release = fetch_json("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11558")
    matches = [
        a
        for a in release["assets"]
        if "win" in a["name"].lower()
        and "x64" in a["name"].lower()
        and "cpu" in a["name"].lower()
        and a["name"].endswith(".zip")
    ]
    if not matches:
        raise RuntimeError("Official Windows CPU binary asset changed; inspect release before downloading")
    asset = matches[0]
    download(
        asset["browser_download_url"],
        target / "runtime.zip",
        150 * 1024 * 1024,
        asset.get("digest", "").removeprefix("sha256:") or None,
    )
    with zipfile.ZipFile(target / "runtime.zip") as archive:
        for info in archive.infolist():
            base = Path(info.filename).name
            if base and (base.endswith((".exe", ".dll")) or base.lower() in {"license", "license.txt"}):
                (target / base).write_bytes(archive.read(info))
    (target / "source.json").write_text(
        json.dumps(
            {
                "model": MODEL_REPO,
                "revision": model["sha"],
                "model_file": MODEL_FILE,
                "model_sha256": item["lfs"]["sha256"],
                "license": "Apache-2.0",
                "runtime_release": release["tag_name"],
                "runtime_asset": asset["name"],
                "runtime_digest": asset.get("digest"),
                "runtime_license": "MIT",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Small local story runtime ready. This is a feasibility model, not a quality claim.", flush=True)


if __name__ == "__main__":
    main()
