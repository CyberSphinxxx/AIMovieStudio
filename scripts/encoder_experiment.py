"""Prepare or explicitly install one pinned experimental image encoder; never infer.

Inspect is offline/read-only apart from its new report. Install requires separate
human approval, keeps the original engine and Studio settings, and publishes the
named profile last. This does not establish model quality or hardware fit.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from scripts import setup_gpu as gpu
from studio.inference_lock import native_inference
from studio.storage import atomic_json, digest

ROOT = Path(__file__).resolve().parents[1]
ENGINE_REVISION = "6479db36bdc2619a904a852bba9c2d78e1a83f82"
PROFILE = "flux2_klein_4b_studio_q4"
REVISION = "bc640142c66e1fdd12af0bd68f40445458f3869b"
FILENAME = "Qwen3-4B-Q4_K_M.gguf"
SIZE = 2_497_280_256
SHA = "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
URL = f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{REVISION}/{FILENAME}"
LOCK_SHA = "f1bf412acd2fa12b323fdda96d78688bfc507592f505d8b51f2425d1366d7ae7"
ALLOWANCE = 2_600_000_000
RESEARCH_BYTES = 26_522  # Earlier 7402 metadata + 19120 pinned license/card capture.
RESERVATION = "qwen3-base-q4-image-experiment"


def scoped(base: Path, relative: str) -> Path:
    path = base / relative
    if not path.resolve().is_relative_to(base.resolve()):
        raise RuntimeError("UNSAFE_PATH: Experiment file escaped its owned folder.")
    return path


def verify(path: Path, size: int, sha: str):
    if not path.is_file() or path.stat().st_size != size or digest(path) != sha:
        raise RuntimeError(f"CHECKSUM_REQUIRED: Missing or changed experiment input: {path.name}")


def locked_inputs(root: Path):
    if root.resolve() != gpu.ROOT.resolve() or scoped(root, "tools/gpu").resolve() != gpu.TARGET.resolve():
        raise RuntimeError("INCOMPATIBLE: Experiment and download ledger must share their owned root.")
    path = root / "ops/evidence/encoder-experiment-lock.json"
    verify(path, path.stat().st_size if path.is_file() else 0, LOCK_SHA)
    lock = json.loads(path.read_bytes())
    engine = scoped(root, "tools/wan-gp")
    marker = scoped(engine, ".studio-revision")
    if not marker.is_file() or marker.read_text() != ENGINE_REVISION:
        raise RuntimeError("INCOMPATIBLE: Experiment requires the inspected pinned engine revision.")
    for item in lock["source_files"] + lock["reuse"]:
        verify(scoped(engine, item["file"]), item["bytes"], item["sha256"])
    for item in lock["notices"]:
        verify(
            scoped(root / "ops/evidence/encoder-candidate-notices", item["file"]),
            item["bytes"],
            item["sha256"],
        )
    config = json.loads(scoped(engine, "ckpts/Qwen3/config.json").read_bytes())
    if (config.get("model_type"), config.get("hidden_size"), config.get("num_hidden_layers")) != (
        "qwen3",
        2560,
        36,
    ):
        raise RuntimeError("INCOMPATIBLE: Existing Qwen3 tokenizer/configuration differs.")
    return engine, lock


def definition(engine: Path) -> dict:
    # A local-only path also prevents accidental downloads in the native engine.
    return {
        "model": {
            "name": "Flux Klein 4B — experimental Q4 encoder (unverified)",
            "architecture": "flux2_klein_4b",
            "URLs": "flux2_klein_4b",
            "text_encoder_URLs": [str(scoped(engine, f"ckpts/Qwen3/{FILENAME}").resolve())],
            "description": "Private image feasibility experiment. RAM fit, speed and quality are unverified.",
        },
        "resolution": "512x512",
        "batch_size": 1,
        "embedded_guidance_scale": 1,
        "num_inference_steps": 4,
    }


def encoded(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def check_existing(path: Path, content: bytes):
    if path.exists() and (not path.is_file() or path.read_bytes() != content):
        raise RuntimeError(f"EXISTING_FILE: Preserve and inspect the existing {path.name}; no overwrite.")


def publish(path: Path, content: bytes):
    """Publish a complete immutable file without replacing another file on races."""
    check_existing(path, content)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    created = False
    try:
        with temporary.open("xb") as stream:
            created = True
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            check_existing(path, content)
    finally:
        if created and temporary.exists():
            temporary.unlink()  # Only this operation's newly created owned temporary.


def inspect(root: Path) -> dict:
    engine, lock = locked_inputs(root)
    candidate = scoped(engine, f"ckpts/Qwen3/{FILENAME}")
    present = candidate.exists()
    if present:
        verify(candidate, SIZE, SHA)
    partial = scoped(engine, f"ckpts/Qwen3/{FILENAME}.partial")
    if partial.exists() and (not partial.is_file() or partial.stat().st_size > SIZE):
        raise RuntimeError("BAD_PARTIAL: Existing encoder partial exceeds the approved artifact.")
    profile = scoped(engine, f"finetunes/{PROFILE}.json")
    profile_bytes = encoded(definition(engine))
    check_existing(profile, profile_bytes)
    for item in lock["notices"]:
        source = scoped(root / "ops/evidence/encoder-candidate-notices", item["file"])
        check_existing(scoped(engine, f"ckpts/Qwen3/studio-q4-notices/{item['file']}"), source.read_bytes())
    state = gpu.ledger()
    counts = [state.get("received_bytes")] + list(state.get("reservations", {}).values())
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts):
        raise RuntimeError(
            "INVALID_LEDGER: Preserve the download ledger; counts must be nonnegative integers."
        )
    allocation = ALLOWANCE - RESEARCH_BYTES
    held = state.get("reservations", {}).get(RESERVATION)
    if held is not None and held > allocation:
        raise RuntimeError("INVALID_LEDGER: Experiment reservation exceeds its bounded allowance.")
    research = state.get("license_source_captures", {}).get("encoder-candidate-research", {})
    if research.get("received_bytes") != RESEARCH_BYTES:
        raise RuntimeError("INVALID_LEDGER: Record the already received research bytes before installation.")
    missing_allocation = allocation if held is None and not present else 0
    accounted = sum(counts) + missing_allocation
    remaining_bytes = 0 if present else SIZE - (partial.stat().st_size if partial.exists() else 0)
    if held is not None and remaining_bytes > held:
        raise RuntimeError("BUDGET_EXHAUSTED: Remaining experiment allowance cannot complete this artifact.")
    if accounted > gpu.LIMIT:
        raise RuntimeError("BUDGET_EXCEEDED: Image experiment would exceed the existing 32 GB ceiling.")
    if shutil.disk_usage(root).free < remaining_bytes + max(gpu.RESERVE, gpu.MIN_FREE) + 1_000_000:
        raise RuntimeError("DISK_RESERVE: Insufficient disk for encoder and preserved installation reserve.")
    report = {
        "status": "FILES_VERIFIED_NOT_INFERENCE" if present else "PREPARED_NOT_INSTALLED_NOT_INFERENCE",
        "profile": PROFILE,
        "profile_definition": definition(engine),
        "encoder": {"url": URL, "bytes": SIZE, "sha256": SHA, "installed": present},
        "lock_sha256": LOCK_SHA,
        "reused_files": lock["reuse"],
        "source_files": lock["source_files"],
        "notices": lock["notices"],
        "experiment_cumulative_download_limit": ALLOWANCE,
        "already_received_research_bytes": RESEARCH_BYTES,
        "accounted_gpu_bytes_including_new_reservation": accounted,
        "gpu_download_ceiling_bytes": gpu.LIMIT,
        "settings_changed": False,
        "hardware_fit": "NOT_TESTED",
        "video": "DEFERRED: separate image visual PASS and complete cumulative-budget review required",
    }
    check_existing(
        scoped(root, "tools/gpu/encoder-experiment-receipt.json"),
        encoded(receipt_for(report, hashlib_sha(profile_bytes))),
    )
    return report


def hashlib_sha(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def receipt_for(report: dict, profile_sha: str) -> dict:
    result = {key: report[key] for key in ("profile", "lock_sha256", "hardware_fit")}
    result.update(profile_sha256=profile_sha, encoder=report["encoder"] | {"installed": True})
    return result


def install(root: Path, *, approved: bool = False):
    if not approved:
        raise RuntimeError(
            "APPROVAL_REQUIRED: See docs/ENCODER_EXPERIMENT_PROPOSAL.md; original scope excludes this file."
        )
    with native_inference():
        report = inspect(root)
        engine = scoped(root, "tools/wan-gp")
        candidate = scoped(engine, f"ckpts/Qwen3/{FILENAME}")
        if not report["encoder"]["installed"]:
            gpu.reserve(RESERVATION, ALLOWANCE - RESEARCH_BYTES)
            gpu.fetch(URL, candidate, SIZE, SHA, reservation=RESERVATION)
        verify(candidate, SIZE, SHA)
        for item in report["notices"]:
            source = scoped(root / "ops/evidence/encoder-candidate-notices", item["file"])
            publish(scoped(engine, f"ckpts/Qwen3/studio-q4-notices/{item['file']}"), source.read_bytes())
        profile = scoped(engine, f"finetunes/{PROFILE}.json")
        publish(profile, encoded(report["profile_definition"]))
        report.update(status="INSTALLED_NOT_INFERENCE", profile_sha256=digest(profile))
        # The immutable receipt is required before the smoke harness may use it.
        publish(
            scoped(root, "tools/gpu/encoder-experiment-receipt.json"),
            encoded(receipt_for(report, report["profile_sha256"])),
        )
        return report


def verify_installed(root: Path):
    report = inspect(root)
    profile = scoped(root, f"tools/wan-gp/finetunes/{PROFILE}.json")
    receipt_path = scoped(root, "tools/gpu/encoder-experiment-receipt.json")
    if not report["encoder"]["installed"] or not profile.is_file() or not receipt_path.is_file():
        raise RuntimeError("MISSING_MODEL: Experimental profile has not completed its approved installation.")
    receipt = json.loads(receipt_path.read_bytes())
    expected = receipt_for(report, digest(profile))
    if receipt != expected:
        raise RuntimeError("CHECKSUM_REQUIRED: Experiment receipt differs from verified inputs.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["inspect", "install"])
    parser.add_argument(
        "--approved", action="store_true", help="Only after explicit approval of the new proposal"
    )
    args = parser.parse_args()
    report = install(ROOT, approved=args.approved) if args.mode == "install" else inspect(ROOT)
    path = ROOT / f"ops/evidence/encoder-experiment-{args.mode}-{uuid4().hex}.json"
    atomic_json(path, report)
    print(
        json.dumps({"status": report["status"], "report": str(path), "hardware_fit": report["hardware_fit"]})
    )


if __name__ == "__main__":
    main()
