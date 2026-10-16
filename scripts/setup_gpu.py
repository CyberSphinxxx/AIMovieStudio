"""Bounded, resumable approved GPU downloads. No system installers or UI server."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from studio.storage import atomic_json, digest
from studio.inference_lock import InferenceBusy, native_inference

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "gpu"
LIMIT = 32_000_000_000
RESERVE = 5_000_000_000
MIN_FREE = 8_315_691_008  # Proposal baseline minus the approved 40 GB growth ceiling.
UV_URL = "https://github.com/astral-sh/uv/releases/download/0.13.0/uv-x86_64-pc-windows-msvc.zip"
UV_SHA = "088962f9e7b7bd9ea740c04c650b2a21c8928c345bd99ac24350dc924dba656c"
SOURCE_BYTES = 61_784_271
SOURCE_SHA = "019b10a0d83dae9e72cb66493b0443f0b6fbdc7a101c31b7e76a270170018df5"


def ledger():
    path = TARGET / "download-ledger.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "approved": "Human reply 2026-10-12: Approve bounded installation and tests",
        "received_bytes": 0,
        "reservations": {},
        "completed": {},
    }


def save(data):
    atomic_json(TARGET / "download-ledger.json", data)


@contextmanager
def download_ownership():
    try:
        with native_inference(TARGET / "download.lock"):
            yield
    except InferenceBusy as error:
        raise RuntimeError("SETUP_BUSY: Another installer is using the GPU download ledger.") from error


def serialized_download(function):
    @wraps(function)
    def protected(*args, **kwargs):
        with download_ownership():
            return function(*args, **kwargs)

    return protected


@serialized_download
def reserve(label, amount):
    data = ledger()
    if label not in data["reservations"]:
        if data["received_bytes"] + sum(data["reservations"].values()) + amount > LIMIT:
            raise RuntimeError("Approved 32 GB download ceiling would be exceeded")
        data["reservations"][label] = amount
        save(data)


@serialized_download
def fetch(url, destination, size, sha, reservation=None):
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or any(c not in "0123456789abcdef" for c in sha)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
    ):
        raise ValueError("Every GPU artifact requires an exact size and SHA256")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == size and digest(destination) == sha:
        print(f"Already verified: {destination.name}", flush=True)
        return
    if destination.exists():
        raise RuntimeError("Existing GPU file has a different checksum; inspect before replacing")
    data = ledger()
    remaining = LIMIT - data["received_bytes"] - sum(data["reservations"].values())
    if reservation:
        remaining += data["reservations"].get(reservation, 0)
    temporary = destination.with_name(destination.name + ".partial")
    offset = temporary.stat().st_size if temporary.exists() else 0
    if offset == size:
        if digest(temporary) != sha:
            raise RuntimeError("Completed GPU partial checksum differs; inspect before retrying")
        os.link(temporary, destination)
        temporary.unlink()
        data["completed"][str(destination.relative_to(ROOT))] = {"bytes": size, "sha256": sha, "url": url}
        save(data)
        return
    if offset > size:
        raise RuntimeError("Existing partial artifact exceeds approved size")
    if size - offset > remaining or shutil.disk_usage(TARGET).free < size - offset + max(RESERVE, MIN_FREE):
        raise RuntimeError("Download exceeds approved budget or disk reserve")
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-", "User-Agent": "pip/26.2.1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        append = offset > 0 and response.status == 206
        if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise RuntimeError("Server returned a different resume offset")
        length = response.headers.get("Content-Length")
        expected_length = size - offset if append else size
        if length is not None and (not length.isdigit() or int(length) != expected_length):
            raise RuntimeError("Server payload length differs from the pinned artifact size")
        if (
            offset
            and not append
            and (size > remaining or shutil.disk_usage(TARGET).free < size + max(RESERVE, MIN_FREE))
        ):
            raise RuntimeError("Server refused resume; full restart exceeds budget or disk reserve")
        total = offset if append else 0
        started = time.monotonic()
        last_report = started
        with temporary.open("ab" if append else "wb") as output:
            # Never consume beyond the pinned payload, even if a server sends more.
            while total < size:
                chunk = response.read(min(4 * 1024**2, size - total))
                if not chunk:
                    break
                total += len(chunk)
                data["received_bytes"] += len(chunk)
                if reservation:
                    data["reservations"][reservation] -= len(chunk)
                    if data["reservations"][reservation] < 0:
                        raise RuntimeError("Runtime download allocation exceeded")
                save(data)
                if total > size or data["received_bytes"] + sum(data["reservations"].values()) > LIMIT:
                    raise RuntimeError("Download exceeded approved size/budget")
                if shutil.disk_usage(TARGET).free < max(RESERVE, MIN_FREE):
                    raise RuntimeError("Download stopped to preserve 5 GB disk reserve")
                output.write(chunk)
                if time.monotonic() - last_report > 10:
                    print(f"{destination.name}: {total / 1e9:.2f}/{size / 1e9:.2f} GB", flush=True)
                    last_report = time.monotonic()
            output.flush()
            os.fsync(output.fileno())
    if total != size:
        raise RuntimeError("Download length differs from approved metadata")
    actual = digest(temporary)
    if actual != sha:
        raise RuntimeError("Downloaded checksum differs from official hosting metadata")
    os.link(temporary, destination)
    temporary.unlink()
    data["completed"][str(destination.relative_to(ROOT))] = {"bytes": total, "sha256": actual, "url": url}
    save(data)
    print(f"Verified {destination.name}: {total} bytes, SHA256 {actual}", flush=True)


def extract_source(archive, revision):
    vendor = ROOT / "tools" / "wan-gp"
    if vendor.exists():
        if (
            not (vendor / ".studio-revision").exists()
            or (vendor / ".studio-revision").read_text() != revision
        ):
            raise RuntimeError("Existing vendor folder is not the approved revision")
        return
    with zipfile.ZipFile(archive) as source:
        prefix = source.namelist()[0].split("/")[0] + "/"
        if sum(i.file_size for i in source.infolist()) > 1_000_000_000:
            raise RuntimeError("Vendor source exceeds 1 GB extraction allowance")
        vendor.mkdir()
        for item in source.infolist():
            relative = item.filename.removeprefix(prefix)
            if not relative or item.is_dir():
                continue
            path = (vendor / relative).resolve()
            if not path.is_relative_to(vendor.resolve()):
                raise RuntimeError("Unsafe vendor archive path")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read(item))
    (vendor / ".studio-revision").write_text(revision)


def phase_plan(proposal, phase):
    """Offline whole-phase admission; no network, writes or reservation refunds."""
    if phase not in {"image", "video"}:
        raise ValueError("Only model image/video phases support offline preflight")
    state = ledger()
    counts = [state.get("received_bytes")] + list(state.get("reservations", {}).values())
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts):
        raise ValueError("INVALID_LEDGER: Download counts must be nonnegative integers")
    rows, seen, needed = [], set(), 0
    base = ROOT / "tools/wan-gp/ckpts"
    if not base.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("UNSAFE_PATH: Model folder escaped its installation")
    for item in proposal["files"]:
        image = item["repo"] in {"DeepBeepMeep/Flux2", "DeepBeepMeep/Z-Image"}
        if image != (phase == "image"):
            continue
        relative, size, sha = item["file"], item["bytes"], item.get("sha256")
        if not isinstance(relative, str) or any(c in relative for c in ("\\", ":", "\x00")):
            raise ValueError("UNSAFE_PATH: Expected a scoped forward-slash model filename")
        destination = base / relative
        if (
            ".." in Path(relative).parts
            or not destination.resolve().is_relative_to(base.resolve())
            or destination.resolve() in seen
        ):
            raise ValueError("UNSAFE_PATH: Duplicate or escaped model destination")
        seen.add(destination.resolve())
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("MISSING_CHECKSUM: Every phase file requires a positive size and SHA256")
        if sha is None:
            # Historical metadata had Git-blob IDs for small files. Only a matching
            # existing completed receipt and verified bytes can resolve those hashes.
            record = state.get("completed", {}).get(str(destination.relative_to(ROOT)), {})
            if record.get("url") == item["url"] and record.get("bytes") == size and destination.is_file():
                sha = record.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError(f"MISSING_CHECKSUM: Resolve the pinned SHA256 before downloading {relative}")
        present = destination.exists()
        if present and (
            not destination.is_file() or destination.stat().st_size != size or digest(destination) != sha
        ):
            raise RuntimeError(f"CHECKSUM_REQUIRED: Preserve and inspect existing {relative}; no overwrite")
        partial = destination.with_name(destination.name + ".partial")
        if not partial.resolve().is_relative_to(base.resolve()):
            raise ValueError("UNSAFE_PATH: Partial file escaped its installation")
        offset = partial.stat().st_size if partial.exists() else 0
        if partial.exists() and (not partial.is_file() or offset > size):
            raise RuntimeError(f"BAD_PARTIAL: Invalid existing partial for {relative}")
        if not present and offset == size and digest(partial) != sha:
            raise RuntimeError(f"CHECKSUM_REQUIRED: Preserve completed partial for {relative}")
        remaining = 0 if present else size - offset
        needed += remaining
        rows.append({**item, "sha256": sha, "destination": str(destination), "remaining_bytes": remaining})
    if not rows:
        raise ValueError("EMPTY_PHASE: No files selected for this model phase")
    if sum(counts) + needed > LIMIT:
        raise RuntimeError("BUDGET_EXCEEDED: Complete model phase exceeds the approved download budget")
    if needed and shutil.disk_usage(ROOT).free < needed + max(RESERVE, MIN_FREE):
        raise RuntimeError("DISK_RESERVE: Complete model phase would exhaust the installation reserve")
    return {
        "phase": phase,
        "status": "OFFLINE_PHASE_PLAN_NOT_INFERENCE",
        "files": rows,
        "remaining_download_bytes": needed,
        "accounted_bytes_after_phase": sum(counts) + needed,
        "download_ceiling_bytes": LIMIT,
        "resume_assumption": "Existing partial offsets; refusal to resume is rechecked before any full restart",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "image", "video"])
    parser.add_argument("--approved", action="store_true", help="Run only after explicit user approval")
    parser.add_argument(
        "--inspect", action="store_true", help="Offline model-phase preflight; no downloads or writes"
    )
    args = parser.parse_args()
    if args.inspect and args.phase == "prepare":
        parser.error("Offline inspection supports only image/video model phases")
    if not args.approved and not args.inspect:
        parser.error("Approval is required; see docs/GPU_INSTALL_PROPOSAL.md")
    proposal = json.loads((ROOT / "ops/evidence/gpu-download-proposal.json").read_text())
    if args.inspect:
        print(json.dumps(phase_plan(proposal, args.phase), indent=2))
        return
    TARGET.mkdir(parents=True, exist_ok=True)
    if args.phase == "prepare":
        uv_zip = TARGET / "uv.zip"
        fetch(UV_URL, uv_zip, 15_722_003, UV_SHA)
        with zipfile.ZipFile(uv_zip) as archive:
            (TARGET / "uv.exe").write_bytes(archive.read("uv.exe"))
        revision = proposal["wan_gp_revision"]
        source_zip = TARGET / "wan-gp-source.zip"
        fetch(
            f"https://codeload.github.com/deepbeepmeep/Wan2GP/zip/{revision}",
            source_zip,
            SOURCE_BYTES,
            SOURCE_SHA,
        )
        extract_source(source_zip, revision)
        reserve("portable-python", 100_000_000)
        env = os.environ | {
            "UV_PYTHON_INSTALL_DIR": str(TARGET / "python"),
            "UV_CACHE_DIR": str(TARGET / "cache"),
        }
        subprocess.run(
            [str(TARGET / "uv.exe"), "python", "install", "3.11.14", "--no-bin", "--no-registry"],
            env=env,
            check=True,
        )
        print(
            "Approved source and isolated Python prepared. Resolve runtime dependencies before model downloads."
        )
    else:
        if args.phase == "video":
            proof = ROOT / "ops/evidence/real-gpu-image.json"
            if not proof.exists() or json.loads(proof.read_text()).get("status") != "PASS":
                raise RuntimeError("Video weights require a measured passing image gate first")
        plan = phase_plan(proposal, args.phase)
        for item in plan["files"]:
            fetch(item["url"], Path(item["destination"]), item["bytes"], item["sha256"])


if __name__ == "__main__":
    main()
