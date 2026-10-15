"""Copy a private development build with no models, vendor engine or user data."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.prepare_app_runtime import ROOT, atomic_json, digest, load_manifest, plain_file

FILES = [
    "StartStudio.cmd",
    "README.md",
    "requirements.txt",
    "contracts/app-runtime-windows.json",
    "scripts/run.ps1",
    "scripts/stop.ps1",
    "scripts/runtime.ps1",
    "scripts/speech.ps1",
    "tools/ffmpeg/ffmpeg.exe",
    "tools/ffmpeg/ffprobe.exe",
    "tools/ffmpeg/LICENSE",
]
TREES = ["studio", "client/dist", "tools/app-runtime"]
NOTICE = """AI Movie Studio - PRIVATE DEVELOPMENT BUILD

Double-click StartStudio.cmd. Stop this copy using scripts/stop.ps1 before
opening another Studio folder. Projects are saved in this folder's data directory.

This folder includes its own CPU application runtime and built interface;
Python, Node and npm installation are not needed to run this prepared copy.
Windows speech uses the voices already installed in Windows.

Development demo visuals and story templates are explicitly simulated.
Real AI image/video generation and writing quality have NOT passed their gates.
No AI models, optional vendor engine, personal projects or settings are bundled.
Optional local engines require their own reviewed installation and configuration.

For private local testing only. Redistribution/license/security release gates
are unfinished. Keep bundled dependency and FFmpeg license notices intact.
"""


def build(root: Path = ROOT):
    root = root.resolve()
    runtime = root / "tools/app-runtime/studio-runtime.json"
    receipt = json.loads(runtime.read_text(encoding="utf-8"))
    pinned = load_manifest(root / "contracts/app-runtime-windows.json")
    if receipt.get("status") != "READY" or receipt.get("manifest_sha256") != digest(
        root / "contracts/app-runtime-windows.json"
    ):
        raise RuntimeError("Prepare and validate the private application runtime first")
    for row in pinned["base_files"]:
        if (
            row["path"] in {"python.exe", "python311.dll"}
            and digest(root / "tools/app-runtime" / row["path"]) != row["sha256"]
        ):
            raise RuntimeError("Private runtime executable changed; no build was created")
    inputs = [root / relative for relative in FILES]
    for relative in TREES:
        tree = root / relative
        if not tree.is_dir() or tree.resolve() != tree:
            raise ValueError("Private build inputs cannot be redirected or missing")
        for path in tree.rglob("*"):
            if path.is_dir():
                if path.resolve() != path:
                    raise ValueError("Private build cannot include directory links")
                continue
            if "__pycache__" not in path.parts and path.suffix != ".pyc":
                inputs.append(path)
    for path in inputs:
        if not path.resolve().is_relative_to(root):
            raise ValueError("Private build input escaped the application")
        plain_file(path)
    size = sum(path.stat().st_size for path in inputs)
    if size > 500_000_000:
        raise RuntimeError("Private build exceeds its reviewed 500 MB bound")
    builds = root / "tools/private-builds"
    if builds.resolve() != builds:
        raise ValueError("Private builds folder cannot be redirected")
    builds.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(builds).free < size + 2_000_000_000:
        raise RuntimeError("Private build needs 2 GB disk reserve plus its copy size")
    token = uuid4().hex[:12]
    stage = builds / f".building-{token}"
    stage.mkdir()
    records = []
    for original in inputs:
        relative = original.relative_to(root)
        output = stage / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        sha = digest(original)
        shutil.copyfile(original, output)
        if digest(output) != sha:
            raise RuntimeError("Private build copy failed checksum verification; partial retained")
        records.append({"path": relative.as_posix(), "sha256": sha, "bytes": output.stat().st_size})
    (stage / "PRIVATE_BUILD.txt").write_text(NOTICE, encoding="utf-8")
    manifest = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bytes": size,
        "files": records,
        "private_only": True,
        "models_included": False,
        "user_data_included": False,
        "native_generation_verified": False,
        "distribution_cleared": False,
    }
    atomic_json(stage / "private-build.json", manifest)
    target = builds / f"Studio-{token}"
    stage.rename(target)
    print(target)
    return target


if __name__ == "__main__":
    build()
