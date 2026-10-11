from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable
from pydantic import Field

from studio import media
from studio.domain import StrictModel
from studio.storage import atomic_json


class WanGPConfig(StrictModel):
    installation: str = Field(default="", max_length=500)
    python: str = Field(default="", max_length=500)
    image_model: str = Field(default="", max_length=100, pattern=r"^[\w.-]*$")
    video_model: str = Field(default="", max_length=100, pattern=r"^[\w.-]*$")
    license_reviewed: bool = False
    native_resolution: str = Field(default="480x832", pattern=r"^(480x832|832x480|512x512)$")
    steps: int = Field(default=12, ge=1, le=40)


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
        }
        req, res = directory / "provider-request.json", directory / "provider-result.json"
        atomic_json(req, request)
        try:
            media.run(
                [self.config.python, str(media.ROOT / "studio" / "vendor_bridge.py"), str(req), str(res)],
                check,
                timeout=3650,
            )
        except media.Interrupted:
            (directory / "native" / "cancel.request").touch()
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
        }
