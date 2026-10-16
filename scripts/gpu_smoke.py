"""Real provider smoke only. Generated artifacts require recorded visual review before PASS."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from scripts.setup_gpu import ROOT
from scripts.encoder_experiment import (
    PROFILE as ENCODER_PROFILE,
    claim_image_test,
    claim_tied_head_test,
    verify_installed,
)
from studio import media
from studio.providers import (
    PARENT_MEMORY_CHECK_SECONDS,
    WanGPConfig,
    WanGPProvider,
    require_resources,
    runtime_memory_known,
)
from studio.storage import atomic_json, digest
from studio.diagnostics import memory_status
from studio.inference_lock import native_inference


def smoke_guard(report, started, max_seconds):
    last_sample = float("-inf")
    report["parent_memory_sample_interval_seconds"] = PARENT_MEMORY_CHECK_SECONDS

    def check():
        nonlocal last_sample
        elapsed = time.monotonic() - started
        if elapsed > max_seconds:
            raise RuntimeError(f"TIMEOUT: GPU smoke reached its {max_seconds}-second ceiling")
        if elapsed - last_sample < PARENT_MEMORY_CHECK_SECONDS:
            return
        last_sample = elapsed
        memory = memory_status()
        report.setdefault("parent_memory_samples", []).append({"seconds": round(elapsed, 3), **memory})
        if not runtime_memory_known(memory):
            raise RuntimeError("RESOURCE_UNKNOWN: GPU smoke lost its RAM counters")
        if memory["free_gb"] < 2:
            raise RuntimeError("RESOURCE_BUSY: GPU smoke stopped below 2 GiB free RAM")

    return check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["runtime", "image", "video"])
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--profile", choices=["4", "4.5", "5"], default="4")
    parser.add_argument(
        "--encoder-experiment",
        action="store_true",
        help="Image-only approved experimental Q4 encoder, profile 5/buffers off; preserves original evidence",
    )
    parser.add_argument(
        "--tied-head-retest",
        action="store_true",
        help="Separate proposed one-image test; requires explicit new approval after the original attempt",
    )
    parser.add_argument("--approved-tied-head-retest", action="store_true")
    parser.add_argument(
        "--disable-smart-pinning",
        action="store_true",
        help="Use a scoped engine config without extra transfer buffers; memory fit is unproven",
    )
    args = parser.parse_args()
    if args.tied_head_retest and (not args.encoder_experiment or not args.approved_tied_head_retest):
        parser.error(
            "Tied-head retest requires --encoder-experiment and explicit new approval of docs/ENCODER_TIED_HEAD_TEST_PROPOSAL.md"
        )
    if args.approved_tied_head_retest and not args.tied_head_retest:
        parser.error("Approval flag requires --tied-head-retest")
    if not 1 <= args.max_seconds <= 3600:
        parser.error("GPU smoke ceiling must be between 1 and 3600 seconds")
    if args.encoder_experiment and (args.phase != "image" or args.max_seconds > 300):
        parser.error("Encoder experiment supports only image with an explicit ceiling of at most 300 seconds")
    root = ROOT / ("data/gpu-encoder-smoke" if args.encoder_experiment else "data/gpu-smoke")
    directory = root / str(uuid4())
    directory.mkdir(parents=True)
    report = {"phase": args.phase, "is_mock": False, "status": "STARTED", "directory": str(directory)}
    evidence = ROOT / (
        f"ops/evidence/encoder-tied-head-image-{directory.name}.json"
        if args.tied_head_retest
        else f"ops/evidence/encoder-experiment-image-{directory.name}.json"
        if args.encoder_experiment
        else f"ops/evidence/real-gpu-{args.phase}.json"
    )
    started = time.monotonic()
    report["max_seconds"] = args.max_seconds
    check = smoke_guard(report, started, args.max_seconds)
    config = WanGPConfig(
        installation=str(ROOT / "tools/wan-gp"),
        python=str(ROOT / "tools/wan-gp/.venv/Scripts/python.exe"),
        image_model=ENCODER_PROFILE if args.encoder_experiment else "flux2_klein_4b",
        video_model="ti2v_2_2",
        native_resolution="512x512",
        steps=4 if args.phase == "image" else 12,
        license_reviewed=True,
        memory_profile=5 if args.encoder_experiment else float(args.profile),
        smart_memory_pinning=False if args.disable_smart_pinning or args.encoder_experiment else None,
    )
    provider = WanGPProvider(
        config, root, encoder_compatibility="qwen3_tied_head_v1" if args.tied_head_retest else None
    )
    ownership = ExitStack()
    try:
        # Own inference before reserving an attempt or validating large files.
        # The provider's nested lease remains held through child cleanup.
        ownership.enter_context(native_inference())
        report["before"] = require_resources()
        if args.encoder_experiment:
            report["encoder_setup"] = verify_installed(ROOT)
            if args.tied_head_retest:
                claim_tied_head_test(
                    ROOT, directory.name, args.max_seconds, approved=args.approved_tied_head_retest
                )
                report["encoder_compatibility"] = "qwen3_tied_head_v1"
            else:
                claim_image_test(ROOT, directory.name, args.max_seconds)
        if args.phase == "runtime":
            report["runtime_attempted"] = True
            result = provider.request("discover", "", directory, check)
            report.update(status="RUNTIME_DISCOVERED_NOT_INFERENCE", result=result)
        elif args.phase == "image":
            report["image_attempted"] = True
            path, metadata = provider.image(
                "Cinematic medium portrait of an adult fictional lighthouse keeper, short dark curly hair, ochre waterproof coat, silver compass in hand, blue dusk beside a stone lighthouse, subtle film grain, soft natural light, expressive face, realistic photograph.",
                directory,
                (512, 512),
                check,
                seed=42,
            )
            report.update(
                status="GENERATED_PENDING_VISUAL_REVIEW",
                output=str(path),
                sha256=digest(path),
                metadata=metadata,
            )
        else:
            image = json.loads((ROOT / "ops/evidence/real-gpu-image.json").read_text())
            if image["status"] != "PASS":
                raise RuntimeError("Video smoke requires reviewed image PASS")
            source = Path(image["output"]).resolve()
            if not source.is_relative_to(root) or digest(source) != image["sha256"]:
                raise RuntimeError("Image smoke source escaped storage or changed")
            outputs = []
            for index in range(2):
                report["before_next_clip"] = require_resources()
                target = directory / f"clip-{index + 1}"
                target.mkdir()
                path, metadata = provider.video(
                    "The lighthouse keeper turns slightly toward the sea, coat shifting in a light breeze. Slow cinematic camera push in. Preserve facial identity, ochre coat and stone lighthouse. Natural restrained motion.",
                    source,
                    target,
                    (512, 512),
                    3,
                    check,
                    seed=42 + index,
                )
                probe = media.validate_video(path, (512, 512), 3)
                outputs.append(
                    {"output": str(path), "sha256": digest(path), "metadata": metadata, "probe": probe}
                )
            report.update(status="GENERATED_PENDING_VISUAL_REVIEW", outputs=outputs)
        report["telemetry"] = [json.loads(p.read_text()) for p in directory.rglob("provider-telemetry.json")]
    except Exception as error:
        report.update(status="FAILED", error=str(error))
        report["telemetry"] = [json.loads(p.read_text()) for p in directory.rglob("provider-telemetry.json")]
        raise
    finally:
        ownership.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        atomic_json(evidence, report)
        if args.phase == "runtime" and report.get("runtime_attempted"):
            error = report.get("error", "")
            code = (
                "OS_POLICY_BLOCKED" if "4551" in error or "OS_POLICY_BLOCKED" in error else report["status"]
            )
            if code not in {"OS_POLICY_BLOCKED", "RUNTIME_DISCOVERED_NOT_INFERENCE"}:
                code = "FAILED"
            atomic_json(
                ROOT / "tools/gpu/runtime-status.json",
                {
                    "code": code,
                    "checked_at": time.time(),
                    "installation": config.installation,
                    "python": config.python,
                    "evidence_sha256": digest(evidence),
                },
            )
        if args.phase == "image" and report.get("image_attempted"):
            code = (
                "IMAGE_RAM_GUARD_STOP"
                if "stopped below 2 GiB free RAM" in report.get("error", "")
                else "GENERATED_PENDING_VISUAL_REVIEW"
                if report["status"] == "GENERATED_PENDING_VISUAL_REVIEW"
                else "FAILED"
            )
            atomic_json(
                ROOT
                / (
                    "tools/gpu/encoder-tied-head-status.json"
                    if args.tied_head_retest
                    else "tools/gpu/encoder-image-status.json"
                    if args.encoder_experiment
                    else "tools/gpu/image-status.json"
                ),
                {
                    "code": code,
                    "checked_at": time.time(),
                    "installation": config.installation,
                    "model": config.image_model,
                    "memory_profile": config.memory_profile,
                    "smart_memory_pinning": config.smart_memory_pinning,
                    "evidence_sha256": digest(evidence),
                },
            )
        print(
            json.dumps(
                {k: v for k, v in report.items() if k not in {"result", "outputs", "metadata", "telemetry"}},
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
