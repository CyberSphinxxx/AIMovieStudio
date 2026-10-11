"""Fetch a small, app-local FFmpeg tool bundle, never install system tools."""

import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def main():
    target = ROOT / "tools" / "ffmpeg"
    if (target / "ffprobe.exe").exists():
        print("FFmpeg tools already present")
        return
    print(f"Downloading app-local FFmpeg from {URL} (256 MB hard limit)")
    with urllib.request.urlopen(URL, timeout=60) as response:
        payload = response.read(256 * 1024 * 1024 + 1)
    if len(payload) > 256 * 1024 * 1024:
        raise RuntimeError("Bundle exceeded the small-download limit")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            base = Path(name).name
            if base in {"ffmpeg.exe", "ffprobe.exe", "LICENSE"}:
                (target / base).write_bytes(archive.read(name))
    if not (target / "ffprobe.exe").exists():
        raise RuntimeError("FFprobe absent from verified bundle layout")
    print(f"Stored {len(payload)} download bytes under {target}")


if __name__ == "__main__":
    main()
