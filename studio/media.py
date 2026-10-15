from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import time
import wave
from contextlib import ExitStack
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont
from studio.processes import owned_process

ROOT = Path(__file__).resolve().parents[1]
SIZES = {"portrait": (360, 640), "landscape": (640, 360), "square": (480, 480)}
MAX_SPEECH_TEMPO = 1.15
DEMO_MAX_ZOOM = 1.06
DEMO_LAYOUT_VERSION = "zoom-safe-v2"


class Interrupted(Exception):
    pass


def binary(name: str) -> str:
    configured = os.environ.get(f"STUDIO_{name.upper()}")
    if configured:
        return configured
    local = ROOT / "tools" / "ffmpeg" / f"{name}.exe"
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    raise RuntimeError("MISSING_FFPROBE: Run python scripts/setup_media.py to install app-local media tools.")


def run(
    args: list[str],
    check: Callable[[], None] = lambda: None,
    timeout: float = 180,
    *,
    capture_stderr: bool = False,
) -> bytes:
    # File-backed stderr avoids pipe deadlocks during long inference/render jobs.
    import tempfile

    with tempfile.TemporaryFile() as errors, tempfile.TemporaryFile() as output, ExitStack() as ownership:
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=errors,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        leaf = Path(args[0]).name.lower() in {"ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"}
        ownership.enter_context(owned_process(process, completed_leaf=leaf))
        started = time.monotonic()
        try:
            while process.poll() is None:
                check()
                if time.monotonic() - started > timeout:
                    raise RuntimeError("TIMEOUT: Media operation exceeded its time limit.")
                time.sleep(0.1)
            errors.seek(0)
            if process.returncode:
                message = errors.read().decode("utf-8", errors="replace")[-2000:]
                raise RuntimeError(f"MEDIA_FAILED: {message}")
            if capture_stderr:
                errors.seek(max(0, errors.seek(0, os.SEEK_END) - 65536))
                return errors.read()[-65536:]
            output.seek(0)
            return output.read()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def probe(path: Path) -> dict:
    return json.loads(
        run(
            [binary("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            timeout=30,
        )
    )


def validate_video(
    path: Path,
    size: tuple[int, int],
    duration: float,
    audio: bool = False,
    check: Callable[[], None] = lambda: None,
) -> dict:
    result = probe(path)
    video = next((s for s in result["streams"] if s["codec_type"] == "video"), None)
    if not video or (video["width"], video["height"]) != size or video["codec_name"] != "h264":
        raise RuntimeError("BAD_OUTPUT: Video dimensions or codec do not match the export profile.")
    if abs(float(result["format"]["duration"]) - duration) > 0.15:
        raise RuntimeError("BAD_OUTPUT: Export runtime does not match the timeline.")
    if audio and not any(s["codec_type"] == "audio" and s["codec_name"] == "aac" for s in result["streams"]):
        raise RuntimeError("BAD_OUTPUT: AAC soundtrack is missing.")
    # Decode the whole tiny draft output; a parseable container alone is insufficient.
    run(
        [binary("ffmpeg"), "-v", "error", "-threads", "2", "-i", str(path), "-f", "null", "-"],
        check,
        timeout=120,
    )
    return result


def reformat(source: Path, output: Path, size: tuple[int, int], check):
    width, height = size
    # Preserve the whole composition, including development watermarks.
    filters = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )
    run(
        [
            binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-threads",
            "2",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-map",
            "0:s?",
            "-vf",
            filters,
            "-filter_threads",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-c:s",
            "copy",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(output),
        ],
        check,
    )


def font(size: int):
    for name in ["C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def preview_text(draw, value: str, face, width: int, max_lines: int):
    """A measured, explicitly shortened preview; full prompts stay in metadata."""
    remaining = " ".join(value.split())
    lines = []
    while remaining and len(lines) < max_lines:
        if draw.textlength(remaining, font=face) <= width:
            lines.append(remaining)
            remaining = ""
            break
        low, high = 0, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if draw.textlength(remaining[:middle], font=face) <= width:
                low = middle
            else:
                high = middle - 1
        cut = max(1, low)
        boundary = remaining.rfind(" ", 0, cut + 1)
        if boundary > 0:
            cut = boundary
        lines.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=face) > width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return "\n".join(lines)


def demo_image(path: Path, size: tuple[int, int], title: str, caption: str, seed: int):
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        draw.line((0, y, width, y), fill=(int(22 + 30 * t), int(31 + 17 * t), int(42 + 12 * t)))
    # Explicit abstract storyboard fixture, not fictional claims of photorealistic generation.
    x = width * (0.45 + 0.1 * (seed % 3))
    draw.ellipse((x - 32, height * 0.3, x + 32, height * 0.3 + 64), fill="#d1ac74")
    draw.polygon(
        [(x - 50, height * 0.65), (x - 30, height * 0.4), (x + 30, height * 0.4), (x + 50, height * 0.65)],
        fill="#ad7142",
    )
    draw.line((width * 0.1, height * 0.7, width * 0.9, height * 0.7), fill="#d1ac74", width=2)
    draw.text((24, 24), "MOCK / DEMO FOOTAGE", font=font(18), fill="#ffe0a5")
    # Keep lettering inside the smallest field of view used by the demo zoom.
    right, bottom = int(width / DEMO_MAX_ZOOM) - 24, int(height / DEMO_MAX_ZOOM) - 24
    title_face, caption_face = font(20 if height <= 384 else 24), font(12)
    title_position = (24, round(height * 0.72))
    chosen = None
    for heading_lines in (1,) if height <= 384 else (2, 1):
        heading = preview_text(draw, title, title_face, right - 24, heading_lines)
        bounds = draw.multiline_textbbox(title_position, heading, font=title_face, spacing=5)
        caption_position = (24, max(round(height * 0.82), bounds[3] + 10))
        for count in (3, 2, 1):
            preview = preview_text(draw, caption, caption_face, right - 24, count)
            box = draw.multiline_textbbox(caption_position, preview, font=caption_face)
            if box[3] <= bottom:
                chosen = (heading, caption_position, preview)
                break
        if chosen:
            break
    if chosen:
        heading, caption_position, preview = chosen
        draw.multiline_text(title_position, heading, font=title_face, fill="#fff5e7", spacing=5)
        draw.multiline_text(caption_position, preview, font=caption_face, fill="#dad6cd")
    image.save(path, format="PNG")


def demo_clip(frame: Path, output: Path, duration: float, size: tuple[int, int], check):
    width, height = size
    frames = round(duration * 24)
    filters = f"zoompan=z='min(zoom+0.0004,{DEMO_MAX_ZOOM})':d={frames}:s={width}x{height}:fps=24,fade=t=in:st=0:d=0.15,fade=t=out:st={max(0, duration - 0.2)}:d=0.2"
    run(
        [
            binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-threads",
            "2",
            "-i",
            str(frame),
            "-vf",
            filters,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "2",
            "-an",
            "-f",
            "mp4",
            str(output),
        ],
        check,
    )
    validate_video(output, size, duration)


def ambience(path: Path, duration: float):
    rate = 16000
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        for second in range(math.ceil(duration)):
            frames = min(rate, round(duration * rate) - second * rate)
            buffer = bytearray()
            for i in range(frames):
                t = second + i / rate
                envelope = min(1, t / 0.5, max(0, (duration - t) / 0.5))
                value = round(
                    450
                    * envelope
                    * (math.sin(2 * math.pi * 110 * t) + 0.35 * math.sin(2 * math.pi * 165 * t))
                )
                buffer.extend(struct.pack("<h", value))
            wav.writeframes(buffer)


def speech(text: str, voice: str, path: Path, check):
    if os.name != "nt":
        raise RuntimeError(
            "MISSING_VOICE: Windows speech is unavailable; select soundtrack-only in Settings."
        )
    textfile = path.with_suffix(".txt")
    textfile.write_text(text, encoding="utf-8")
    run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(ROOT / "scripts" / "speech.ps1"),
            "-TextFile",
            str(textfile),
            "-OutputFile",
            str(path),
            "-Voice",
            voice,
        ],
        check,
        timeout=30,
    )
    with wave.open(str(path)) as wav:
        return wav.getnframes() / wav.getframerate()


def soundtrack(
    script: dict, plan: dict, output: Path, directory: Path, enabled: bool, check, effects: Path | None = None
) -> list[dict]:
    timeline = []
    start = 0.0
    segments = []
    for shot in script["shots"]:
        check()
        narration = shot["narration"] if enabled else ""
        raw = directory / f"voice-{shot['number']}.wav"
        segment = directory / f"segment-{shot['number']}.wav"
        length = 0.0
        if narration:
            voice = next(c["voice"] for c in plan["characters"] if c["id"] == shot["speaker_id"])
            length = speech(narration, voice, raw, check)
            available = max(0.5, shot["duration"] - 0.25)
            speed = max(1.0, length / available)
            if speed > MAX_SPEECH_TEMPO:
                raise RuntimeError(
                    f"DIALOGUE_TOO_LONG: Shot {shot['number']} needs {length:.2f}s of speech "
                    f"but has {available:.2f}s available. Maximum tempo correction is 1.15x. "
                    "Create a project with a longer runtime and shorter lines, or select "
                    "ambience-only in Settings and retry to omit spoken dialogue. Raw voice is preserved."
                )
            normalized_length = min(length, available)
            filters = f"atempo={speed:.6f},apad,atrim=duration={shot['duration']}"
            run(
                [
                    binary("ffmpeg"),
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(raw),
                    "-af",
                    filters,
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(segment),
                ],
                check,
            )
            timeline.append(
                {
                    "start": start,
                    "end": start + normalized_length,
                    "text": narration,
                    "speaker_id": shot["speaker_id"],
                    "shot_number": shot["number"],
                    "raw_duration": length,
                    "tempo": speed,
                    "raw_voice_file": raw.name,
                }
            )
        else:
            ambience(segment, shot["duration"])
        segments.append(segment)
        start += shot["duration"]
    joined = directory / "dialogue.wav"
    listing = directory / "audio-concat.txt"
    listing.write_text("\n".join(f"file '{p.name}'" for p in segments), encoding="utf-8")
    run(
        [
            binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(joined),
        ],
        check,
    )
    bed = directory / "ambience.wav"
    ambience(bed, start)
    effect_input = ["-i", str(effects)] if effects else []
    mixing = (
        "[0:a]volume=0.9,asplit=2[d][key];[1:a]volume=0.3[b];[2:a]volume=0.6[s];"
        "[s][key]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=250[fx];"
        "[d][b][fx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[out]"
        if effects
        else "[0:a]volume=0.9[d];[1:a]volume=0.3[b];[d][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[out]"
    )
    run(
        [
            binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(joined),
            "-i",
            str(bed),
            *effect_input,
            "-filter_complex",
            mixing,
            "-map",
            "[out]",
            "-ar",
            "48000",
            str(output),
        ],
        check,
    )
    return timeline


def timestamp(t: float) -> str:
    milliseconds = round(t * 1000)
    return f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}"


def assemble(clips: list[Path], audio: Path, subtitle: Path, timeline: list[dict], output: Path, check):
    subtitle.write_text(
        "\n\n".join(
            f"{i + 1}\n{timestamp(t['start'])} --> {timestamp(t['end'])}\n{t['text']}"
            for i, t in enumerate(timeline)
        ),
        encoding="utf-8",
    )
    listing = output.parent / "video-concat.txt"
    # Relative generated names, scoped copies; no public filenames or URLs in concat files.
    for i, clip in enumerate(clips):
        shutil.copyfile(clip, output.parent / f"input-{i}.mp4")
    listing.write_text("\n".join(f"file 'input-{i}.mp4'" for i in range(len(clips))), encoding="utf-8")
    args = [
        binary("ffmpeg"),
        "-y",
        "-v",
        "error",
        "-f",
        "concat",
        "-safe",
        "1",
        "-i",
        str(listing),
        "-i",
        str(audio),
    ]
    if timeline:
        args += [
            "-i",
            str(subtitle),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
        ]
    else:
        args += ["-map", "0:v", "-map", "1:a"]
    args += [
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(output),
    ]
    run(args, check)
