"""Measured, bounded linear gain. Preserve dynamics, original stems and timing."""

from __future__ import annotations

import json
import math
import os
import shutil
import wave
from pathlib import Path
from typing import Callable

from studio import media

VERSION = "balanced-audio-v1"
PEAK_CEILING = -2.0


def parse_measurement(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace")
    start, end = text.rfind("{"), text.rfind("}")
    try:
        data = json.loads(text[start : end + 1])
        result = {}
        for source, field in [
            ("input_i", "integrated_lufs"),
            ("input_tp", "true_peak_dbtp"),
            ("input_lra", "range_lu"),
        ]:
            value = data[source]
            if value == "-inf" and source in {"input_i", "input_tp"}:
                result[field] = None
                continue
            number = float(value)
            if not math.isfinite(number) or not -120 <= number <= 120:
                raise ValueError("Non-finite/out-of-range loudness")
            result[field] = number
        return result
    except (KeyError, ValueError, TypeError) as error:
        raise RuntimeError(
            "BAD_AUDIO: FFmpeg returned an invalid loudness measurement; original audio is preserved."
        ) from error


def measure(path: Path, check: Callable[[], None] = lambda: None) -> dict:
    raw = media.run(
        [
            media.binary("ffmpeg"),
            "-hide_banner",
            "-nostats",
            "-v",
            "info",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-af",
            "loudnorm=I=-16:TP=-2:LRA=11:dual_mono=true:print_format=json",
            "-f",
            "null",
            "-",
        ],
        check,
        timeout=180,
        capture_stderr=True,
    )
    return {
        **parse_measurement(raw),
        "measurement": "FFmpeg loudnorm/EBU R128; mono measured for stereo playback",
    }


def balance(source: Path, output: Path, dialogue: bool, check: Callable[[], None]) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("Balanced audio must preserve its original mix")
    with wave.open(str(source)) as wav:
        channels, rate, frames = wav.getnchannels(), wav.getframerate(), wav.getnframes()
    if channels != 1 or rate != 48000 or not 0 < frames <= 600 * rate:
        raise RuntimeError("BAD_AUDIO: Expected a bounded mono 48 kHz studio mix.")
    before = measure(source, check)
    requested, max_boost = (-16.0, 9.0) if dialogue else (-26.0, 6.0)
    integrated, peak = before["integrated_lufs"], before["true_peak_dbtp"]
    if integrated is None:
        # Silence/below-gate material never gets amplified; loud isolated peaks still reduce.
        gain = min(0.0, PEAK_CEILING - peak - 0.1) if peak is not None else 0.0
        status = "below_measurement_gate"
    else:
        if peak is None:
            raise RuntimeError("BAD_AUDIO: Audible material has no finite true-peak measurement.")
        desired = requested - integrated
        gain = min(desired, max_boost, PEAK_CEILING - peak - 0.1)
        status = (
            "target_reached" if gain == desired else "gain_limited" if gain == max_boost else "peak_limited"
        )
    temporary = output.with_suffix(".partial.wav")
    check()
    if abs(gain) < 0.001:
        shutil.copyfile(source, temporary)
    else:
        media.run(
            [
                media.binary("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-af",
                f"volume={gain:.6f}dB:precision=double",
                "-ar",
                str(rate),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(temporary),
            ],
            check,
            timeout=180,
        )
    check()
    with wave.open(str(temporary)) as wav:
        if (wav.getnchannels(), wav.getframerate(), wav.getnframes()) != (channels, rate, frames):
            raise RuntimeError("BAD_AUDIO: Volume processing changed soundtrack timing or format.")
    after = measure(temporary, check)
    if after["true_peak_dbtp"] is not None and after["true_peak_dbtp"] > PEAK_CEILING + 0.1:
        raise RuntimeError("BAD_AUDIO: Balanced soundtrack exceeded its measured true-peak ceiling.")
    if integrated is not None:
        if after["integrated_lufs"] is None:
            # A large peak reduction can intentionally put material below the gate.
            status = "below_measurement_gate"
        elif abs(after["integrated_lufs"] - requested) > 0.3 and status == "target_reached":
            raise RuntimeError("BAD_AUDIO: Balanced soundtrack missed its measured loudness target.")
    check()
    os.replace(temporary, output)
    return {
        "method": VERSION,
        "status": status,
        "scope": "PCM soundtrack; encoded AAC may differ",
        "requested_lufs": requested,
        "true_peak_ceiling_dbtp": PEAK_CEILING,
        "max_boost_db": max_boost,
        "applied_gain_db": round(gain, 6),
        "input": before,
        "output": after,
    }
