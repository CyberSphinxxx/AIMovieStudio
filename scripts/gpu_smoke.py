"""Real provider smoke only. Generated artifacts require recorded visual review before PASS."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from scripts.setup_gpu import ROOT
from studio import media
from studio.providers import WanGPConfig, WanGPProvider, require_resources
from studio.storage import atomic_json, digest
from studio.diagnostics import memory_status


def smoke_guard(report, started, max_seconds):
    last_sample = -2.0

    def check():
        nonlocal last_sample
        elapsed = time.monotonic() - started
        if elapsed > max_seconds:
            raise RuntimeError(f"TIMEOUT: GPU smoke reached its {max_seconds}-second ceiling")
        if elapsed - last_sample < 2:
            return
        last_sample = elapsed
        memory = memory_status()
        report.setdefault("parent_memory_samples", []).append({"seconds": round(elapsed, 3), **memory})
        if not memory.get("available"):
            raise RuntimeError("RESOURCE_UNKNOWN: GPU smoke lost its RAM counters")
        if memory["free_gb"] < 2:
            raise RuntimeError("RESOURCE_BUSY: GPU smoke stopped below 2 GiB free RAM")

    return check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["runtime", "image", "video"])
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--profile", choices=["4", "4.5", "5"], default="4")
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 3600:
        parser.error("GPU smoke ceiling must be between 1 and 3600 seconds")
    root = ROOT / "data/gpu-smoke"
    directory = root / str(uuid4())
    directory.mkdir(parents=True)
    report = {"phase": args.phase, "is_mock": False, "status": "STARTED", "directory": str(directory)}
    evidence = ROOT / f"ops/evidence/real-gpu-{args.phase}.json"
    started = time.monotonic()
    report["max_seconds"] = args.max_seconds
    check = smoke_guard(report, started, args.max_seconds)
    config = WanGPConfig(
        installation=str(ROOT / "tools/wan-gp"),
        python=str(ROOT / "tools/wan-gp/.venv/Scripts/python.exe"),
        image_model="flux2_klein_4b",
        video_model="ti2v_2_2",
        native_resolution="512x512",
        steps=4 if args.phase == "image" else 12,
        license_reviewed=True,
        memory_profile=float(args.profile),
    )
    provider = WanGPProvider(config, root)
    try:
        report["before"] = require_resources()
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
                ROOT / "tools/gpu/image-status.json",
                {
                    "code": code,
                    "checked_at": time.time(),
                    "installation": config.installation,
                    "model": config.image_model,
                    "memory_profile": config.memory_profile,
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
