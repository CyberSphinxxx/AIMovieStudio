"""Provision the existing official FFmpeg bundle required by WanGP offline init."""

from __future__ import annotations

import shutil
import urllib.request
import zipfile

from scripts.setup_gpu import ROOT, TARGET, fetch


def main():
    import json

    with urllib.request.urlopen("https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/9.0.2", timeout=30) as response:
        release = json.load(response)
    asset = next(a for a in release["assets"] if a["name"] == "ffmpeg-9.0.2-essentials_build.zip")
    base = asset["browser_download_url"]
    sha = asset["digest"].removeprefix("sha256:")
    if len(sha) != 64:
        raise RuntimeError("Official FFmpeg checksum format changed")
    archive = TARGET / "ffmpeg.zip"
    # Existing observed bundle is ~115MB; approved hard maximum remains 256MB.
    fetch(base, archive, asset["size"], sha, reservation="runtime-and-resolution")
    from studio.storage import digest

    if digest(archive) != sha:
        raise RuntimeError("Official FFmpeg checksum differs from download")
    target = ROOT / "tools/wan-gp/ffmpeg_bins"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            name = item.filename.split("/")[-1]
            if name in {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe", "LICENSE"}:
                with source.open(item) as incoming, (target / name).open("wb") as output:
                    shutil.copyfileobj(incoming, output)
    print(f"Official FFmpeg binaries ready for offline WanGP init, SHA256 {sha}")


if __name__ == "__main__":
    main()
