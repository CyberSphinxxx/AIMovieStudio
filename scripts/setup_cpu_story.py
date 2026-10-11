"""Prepare the separately approved1.5B CPU writing experiment; never overwrite files."""

import argparse
import json
import os
import shutil
import urllib.request
from pathlib import Path

from studio.storage import atomic_json, digest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/story"
PROPOSAL = ROOT / "ops/evidence/cpu-story-download-proposal.json"


def fetch(url, destination, size, sha, ledger_path, cap):
    if size <= 0 or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("CPU artifacts require exact positive size and SHA256")
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    if destination.exists():
        if destination.stat().st_size == size and digest(destination) == sha:
            return
        raise RuntimeError("Existing CPU model/notice differs; inspect before replacing")
    partial = destination.with_name(destination.name + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset == size:
        if digest(partial) != sha:
            raise RuntimeError("Completed CPU partial has a different SHA256; inspect before retrying")
        os.link(partial, destination)
        partial.unlink()
        data["completed"][destination.name] = {"bytes": size, "sha256": sha, "url": url}
        atomic_json(ledger_path, data)
        return
    remaining = cap - data["received_bytes"]
    reserve = 5_000_000_000
    if (
        offset > size
        or size - offset > remaining
        or shutil.disk_usage(destination.parent).free < size - offset + reserve
    ):
        raise RuntimeError("CPU download exceeds its approved cumulative budget or disk reserve")
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"})
    with urllib.request.urlopen(request, timeout=90) as response:
        append = offset > 0 and response.status == 206
        if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise RuntimeError("Server returned an incorrect CPU resume offset")
        if offset and not append and size > remaining:
            raise RuntimeError("Server refused resume; full restart exceeds CPU download cap")
        total = offset if append else 0
        with partial.open("ab" if append else "wb") as output:
            while chunk := response.read(4 * 1024**2):
                total += len(chunk)
                data["received_bytes"] += len(chunk)
                atomic_json(ledger_path, data)
                if (
                    total > size
                    or data["received_bytes"] > cap
                    or shutil.disk_usage(destination.parent).free < reserve
                ):
                    raise RuntimeError("CPU download stopped at approved size/network/disk boundary")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    if total != size or digest(partial) != sha:
        raise RuntimeError("CPU artifact length or SHA256 differs from reviewed official metadata")
    os.link(partial, destination)
    partial.unlink()
    data["completed"][destination.name] = {"bytes": size, "sha256": sha, "url": url}
    atomic_json(ledger_path, data)
    print(f"Verified {destination.name}: {size}bytes", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args(argv)
    if not args.approved:
        parser.error("Separate human approval required: docs/CPU_STORY_INSTALL_PROPOSAL.md")
    if not (TARGET / "llama-server.exe").is_file():
        raise RuntimeError("Existing CPU runtime is required; this approval installs no executables")
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    ledger_path = TARGET / "qwen1.5b-download-ledger.json"
    if not ledger_path.exists():
        atomic_json(
            ledger_path, {"scope": "CPU_STORY_INSTALL_PROPOSAL.md", "received_bytes": 0, "completed": {}}
        )
    for item in proposal["files"]:
        scoped_names = [entry.get("destination", entry["file"]) for entry in proposal["files"]]
        scoped_names += [name + ".partial" for name in scoped_names] + [ledger_path.name]
        used = sum((TARGET / name).stat().st_size for name in scoped_names if (TARGET / name).is_file())
        if used > proposal["additional_disk_cap_bytes"]:
            raise RuntimeError("CPU artifact footprint exceeds the approved additional disk cap")
        url = f"https://huggingface.co/{proposal['repo']}/resolve/{proposal['revision']}/{item['file']}"
        fetch(
            url,
            TARGET / item.get("destination", item["file"]),
            item["bytes"],
            item["sha256"],
            ledger_path,
            proposal["download_cap_bytes"],
        )
    print("CPU experiment files verified. Writing quality remains unproven.")


if __name__ == "__main__":
    main()
