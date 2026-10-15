from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Callable, Literal
from pydantic import Field

from studio import media
from studio.domain import StrictModel
from studio.storage import atomic_json

PARENT_MEMORY_CHECK_SECONDS = 0.5


def runtime_memory_known(memory: dict) -> bool:
    value = memory.get("free_gb")
    return (
        memory.get("available") is True
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def require_resources():
    from studio.diagnostics import hardware

    report = hardware(refresh=True)
    memory, gpu = report["memory"], report["gpu"]
    if not memory.get("available") or not gpu.get("available"):
        raise RuntimeError(
            "RESOURCE_UNKNOWN: Local RAM/GPU counters are unavailable; inspect diagnostics before inference."
        )
    if memory["free_gb"] < 5 or gpu["total_mb"] - gpu["used_mb"] < 4096:
        raise RuntimeError(
            f"RESOURCE_BUSY: Need 5 GB free RAM and 4 GB free VRAM for the initial smoke profile. "
            f"Currently {memory['free_gb']} GB RAM and {gpu['total_mb'] - gpu['used_mb']} MB VRAM free. Close heavy applications and retry."
        )
    if gpu["temperature_c"] >= 85:
        raise RuntimeError(
            "RESOURCE_HOT: GPU is at least 85°C before inference; wait for it to cool and retry."
        )
    return report


class WanGPConfig(StrictModel):
    installation: str = Field(default="", max_length=500)
    python: str = Field(default="", max_length=500)
    image_model: str = Field(default="", max_length=100, pattern=r"^[\w.-]*$")
    video_model: str = Field(default="", max_length=100, pattern=r"^[\w.-]*$")
    license_reviewed: bool = False
    native_resolution: str = Field(default="480x832", pattern=r"^(480x832|832x480|512x512)$")
    steps: int = Field(default=12, ge=1, le=40)
    memory_profile: Literal[4, 4.5, 5] = 4
    smart_memory_pinning: bool | None = None


class WanGPProvider:
    def __init__(self, config: WanGPConfig, data_root: Path):
        self.config = config
        self.data_root = data_root.resolve()

    def configured(self):
        return (
            self.config.license_reviewed
            and Path(self.config.python).is_file()
            and (Path(self.config.installation) / "shared" / "api.py").is_file()
        )

    def request(
        self,
        kind: str,
        prompt: str,
        directory: Path,
        check: Callable[[], None],
        seed: int = 42,
        references: list[Path] | None = None,
        start_image: Path | None = None,
        seconds: float = 5,
    ) -> dict:
        if not self.config.license_reviewed:
            raise RuntimeError(
                "LICENSE_REVIEW_REQUIRED: Review WanGP and selected model rights in Settings before running it."
            )
        if not self.configured():
            raise RuntimeError(
                "MISSING_PROVIDER: Choose an existing separate WanGP Python and installation in Settings."
            )
        if kind != "discover":
            require_resources()
        directory = directory.resolve()
        if not directory.is_relative_to(self.data_root):
            raise ValueError("Provider output outside storage root")
        request = {
            "kind": kind,
            "model": self.config.image_model if kind == "image" else self.config.video_model,
            "prompt": prompt,
            "resolution": self.config.native_resolution,
            "seed": seed,
            "steps": self.config.steps,
            "installation": self.config.installation,
            "output_dir": str(directory / "native"),
            "data_root": str(self.data_root),
            "references": [str(p) for p in references or []],
            "start_image": str(start_image) if start_image else None,
            "seconds": seconds,
            "timeout": 3600,
            "memory_profile": self.config.memory_profile,
            "smart_memory_pinning": self.config.smart_memory_pinning,
            "parent_memory_sample_interval_seconds": PARENT_MEMORY_CHECK_SECONDS,
        }
        req, res = directory / "provider-request.json", directory / "provider-result.json"
        atomic_json(req, request)
        last_memory_check = float("-inf")

        def guarded_check():
            nonlocal last_memory_check
            check()
            now = time.monotonic()
            if kind == "discover" or now - last_memory_check < PARENT_MEMORY_CHECK_SECONDS:
                return
            from studio.diagnostics import memory_status

            last_memory_check = now
            memory = memory_status()
            if not runtime_memory_known(memory):
                raise RuntimeError("RESOURCE_UNKNOWN: Generation lost its RAM counters")
            if memory["free_gb"] < 2:
                raise RuntimeError(
                    "RESOURCE_BUSY: Image/video generation stopped below 2 GiB free RAM. Saved checkpoints are preserved."
                )

        try:
            guarded_check()
            media.run(
                [self.config.python, str(media.ROOT / "studio" / "vendor_bridge.py"), str(req), str(res)],
                guarded_check,
                timeout=3650,
            )
        except media.Interrupted:
            (directory / "native" / "cancel.request").touch()
            raise
        except RuntimeError as error:
            message = str(error)
            if "4551" in message or "Application Control policy has blocked" in message:
                raise RuntimeError(
                    "OS_POLICY_BLOCKED: Windows Application Control blocked a provider dependency. "
                    "Generation did not start. Inspect Windows Code Integrity diagnostics; "
                    "the studio cannot change system security policy."
                ) from error
            raise
        return json.loads(res.read_text(encoding="utf-8"))

    def image(self, prompt, directory, size, check, references=None, seed=42):
        from PIL import Image, ImageOps

        result = self.request("image", prompt, directory, check, seed, references=references)
        source = next(
            (
                Path(p)
                for p in result["files"]
                if Path(p).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ),
            None,
        )
        if source is None:
            raise RuntimeError("BAD_OUTPUT: Provider returned no reference image")
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            native_size = image.size
            output = directory / "image.png"
            ImageOps.pad(image.convert("RGB"), size, color="#111212").save(output)
        return output, {
            "native_dimensions": native_size,
            "framing": "aspect-preserving letterbox",
            "model": result["model"],
            "parameters": result["parameters"],
            "memory_profile": result.get("memory_profile", self.config.memory_profile),
            "runtime_options": result.get("runtime_options"),
        }

    def video(self, prompt, frame, directory, size, seconds, check, seed=42):
        result = self.request("video", prompt, directory, check, seed, start_image=frame, seconds=seconds)
        source = next(
            (Path(p) for p in result["files"] if Path(p).suffix.lower() in {".mp4", ".mov", ".webm"}), None
        )
        if source is None:
            raise RuntimeError("BAD_OUTPUT: Provider returned no video clip")
        native = media.probe(source)
        if not any(s["codec_type"] == "video" for s in native["streams"]):
            raise RuntimeError("BAD_OUTPUT: Provider output has no video stream")
        width, height = size
        temporary = directory / "clip.partial.mp4"
        media.run(
            [
                media.binary("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=24,tpad=stop_mode=clone:stop_duration={seconds}",
                "-t",
                str(seconds),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-threads",
                "2",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-f",
                "mp4",
                str(temporary),
            ],
            check,
        )
        media.validate_video(temporary, size, seconds)
        final = directory / "clip.mp4"
        os.replace(temporary, final)
        return final, {
            "native_probe": native,
            "framing": "aspect-preserving letterbox; fixed timeline duration",
            "model": result["model"],
            "parameters": result["parameters"],
            "memory_profile": result.get("memory_profile", self.config.memory_profile),
            "runtime_options": result.get("runtime_options"),
        }
