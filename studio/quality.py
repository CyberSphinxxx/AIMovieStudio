"""Deterministic cinematic quality evaluation and media fault gates.

Discriminate syntactic container success from media and film quality according
to docs/13_QUALITY_EVAL.md. Evaluates hard machine-checkable gates (container,
codecs, yuv420p pixel format, duration, frame counts, blackouts, silence,
and manifest/EDL alignment) without inventing heuristic AI scores.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from pydantic import Field

from studio import media
from studio.domain import StrictModel
from studio.storage import Store, digest


class HardGateCheck(StrictModel):
    name: str
    passed: bool
    measured: str
    threshold: str
    error: str | None = None


class QualityEvaluation(StrictModel):
    schema_version: int = 1
    evaluated_at: float
    all_hard_gates_passed: bool
    hard_gates: list[HardGateCheck]
    cinematic_review_status: str
    cinematic_review: str
    quality_tier: str
    cost_usd: float = 0.0
    cloud_tokens_used: int = 0
    warnings: list[str] = Field(default_factory=list)


def run_media_fault_detect(
    path: Path,
    has_audio: bool,
    check: Callable[[], None] = lambda: None,
) -> tuple[float, float | None, float | None]:
    """Run blackdetect and volumedetect in a single ffmpeg decode pass."""
    args = [
        media.binary("ffmpeg"),
        "-v",
        "info",
        "-i",
        str(path),
        "-vf",
        "blackdetect=d=0.5:pix_th=0.10",
    ]
    if has_audio:
        args.extend(["-af", "volumedetect"])
    args.extend(["-f", "null", "-"])

    stderr_raw = media.run(args, check, timeout=120, capture_stderr=True)
    text = stderr_raw.decode("utf-8", errors="replace")

    black_durations = [float(val) for val in re.findall(r"black_duration:([0-9.]+)", text)]
    total_black = sum(black_durations)

    mean_vol, max_vol = None, None
    if has_audio:
        m_mean = re.search(r"mean_volume:\s*(-?[0-9.]+|-\s*inf)\s*dB", text)
        m_max = re.search(r"max_volume:\s*(-?[0-9.]+|-\s*inf)\s*dB", text)
        if m_mean:
            val = m_mean.group(1).replace(" ", "")
            mean_vol = -100.0 if "-inf" in val else float(val)
        if m_max:
            val = m_max.group(1).replace(" ", "")
            max_vol = -100.0 if "-inf" in val else float(val)

    return total_black, mean_vol, max_vol


def evaluate_export(
    path: Path,
    size: tuple[int, int],
    target_duration: float,
    audio_expected: bool = True,
    is_mock: bool = True,
    script: dict | None = None,
    clips: list[dict] | None = None,
    store: Store | None = None,
    check: Callable[[], None] = lambda: None,
) -> QualityEvaluation:
    """Evaluate machine-checkable hard gates on exported media."""
    evaluated_at = time.time()
    gates: list[HardGateCheck] = []
    warnings: list[str] = []

    if is_mock:
        warnings.append("Draft demo; abstract motion storyboard with MOCK watermark, not AI generated.")

    # 1. Container & Probe
    probe_result = None
    try:
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("Export file is missing or 0 bytes.")
        probe_result = media.probe(path)
        format_info = probe_result.get("format", {})
        fmt_name = format_info.get("format_name", "")
        if "mp4" not in fmt_name and "mov" not in fmt_name:
            raise RuntimeError(f"Unexpected format: {fmt_name}")
        gates.append(
            HardGateCheck(
                name="container_format",
                passed=True,
                measured=f"MP4 ({path.stat().st_size} bytes)",
                threshold="valid MP4/MOV container > 0 bytes",
            )
        )
    except Exception as exc:
        gates.append(
            HardGateCheck(
                name="container_format",
                passed=False,
                measured="missing or unreadable",
                threshold="valid MP4/MOV container > 0 bytes",
                error=str(exc),
            )
        )
        return QualityEvaluation(
            evaluated_at=evaluated_at,
            all_hard_gates_passed=False,
            hard_gates=gates,
            cinematic_review_status="hard_gates_failed",
            cinematic_review=f"Failed hard container gate: {exc}",
            quality_tier="mock_demo" if is_mock else "local_ai_draft",
            warnings=warnings,
        )

    streams = probe_result.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    # 2. Video Codec
    if video and video.get("codec_name") == "h264":
        gates.append(
            HardGateCheck(
                name="video_codec",
                passed=True,
                measured=f"h264 ({video.get('profile', 'default')})",
                threshold="h264",
            )
        )
    else:
        v_codec = video.get("codec_name") if video else "none"
        gates.append(
            HardGateCheck(
                name="video_codec",
                passed=False,
                measured=str(v_codec),
                threshold="h264",
                error="Video stream missing or codec is not h264",
            )
        )

    # 3. Pixel Format (must be yuv420p for standard browser playback)
    pix_fmt = video.get("pix_fmt") if video else None
    if pix_fmt == "yuv420p":
        gates.append(
            HardGateCheck(
                name="pixel_format",
                passed=True,
                measured=pix_fmt,
                threshold="yuv420p",
            )
        )
    else:
        gates.append(
            HardGateCheck(
                name="pixel_format",
                passed=False,
                measured=str(pix_fmt),
                threshold="yuv420p",
                error=f"Pixel format {pix_fmt} does not match required browser standard yuv420p",
            )
        )

    # 4. Dimensions
    v_width = video.get("width") if video else None
    v_height = video.get("height") if video else None
    if (v_width, v_height) == size:
        gates.append(
            HardGateCheck(
                name="dimensions",
                passed=True,
                measured=f"{v_width}x{v_height}",
                threshold=f"{size[0]}x{size[1]}",
            )
        )
    else:
        gates.append(
            HardGateCheck(
                name="dimensions",
                passed=False,
                measured=f"{v_width}x{v_height}",
                threshold=f"{size[0]}x{size[1]}",
                error=f"Dimensions {v_width}x{v_height} do not match target {size[0]}x{size[1]}",
            )
        )

    # 5. Duration & Tolerance
    probed_duration = float(format_info.get("duration", 0))
    duration_diff = abs(probed_duration - target_duration)
    if duration_diff <= 0.15:
        gates.append(
            HardGateCheck(
                name="duration",
                passed=True,
                measured=f"{probed_duration:.2f}s",
                threshold=f"{target_duration:.2f}s (±0.15s)",
            )
        )
    else:
        gates.append(
            HardGateCheck(
                name="duration",
                passed=False,
                measured=f"{probed_duration:.2f}s",
                threshold=f"{target_duration:.2f}s (±0.15s)",
                error=f"Export duration discrepancy {duration_diff:.2f}s exceeds 0.15s tolerance",
            )
        )

    # 6. Frame Count & FPS
    r_frame_rate = video.get("r_frame_rate", "24/1") if video else "24/1"
    nb_frames_str = video.get("nb_frames") if video else None
    nb_frames = int(nb_frames_str) if nb_frames_str and nb_frames_str.isdigit() else None
    expected_frames = round(target_duration * 24)
    if nb_frames is not None:
        frame_diff = abs(nb_frames - expected_frames)
        if frame_diff <= 4:
            gates.append(
                HardGateCheck(
                    name="frame_count",
                    passed=True,
                    measured=f"{nb_frames} frames @ {r_frame_rate}",
                    threshold=f"~{expected_frames} frames (24 fps)",
                )
            )
        else:
            gates.append(
                HardGateCheck(
                    name="frame_count",
                    passed=False,
                    measured=f"{nb_frames} frames",
                    threshold=f"~{expected_frames} frames (24 fps)",
                    error=f"Frame count {nb_frames} deviates from expected {expected_frames}",
                )
            )
    else:
        gates.append(
            HardGateCheck(
                name="frame_count",
                passed=True,
                measured=f"rate {r_frame_rate}",
                threshold="24 fps nominal",
            )
        )

    # 7. Audio Stream & Codec
    if audio_expected:
        a_codec = audio.get("codec_name") if audio else None
        sample_rate = int(audio.get("sample_rate", 0)) if audio else 0
        if a_codec == "aac" and sample_rate >= 16000:
            gates.append(
                HardGateCheck(
                    name="audio_codec",
                    passed=True,
                    measured=f"aac ({sample_rate} Hz, {audio.get('channels', 1)}ch)",
                    threshold="aac (>=16000 Hz)",
                )
            )
        else:
            gates.append(
                HardGateCheck(
                    name="audio_codec",
                    passed=False,
                    measured=f"{a_codec} ({sample_rate} Hz)",
                    threshold="aac (>=16000 Hz)",
                    error="Expected AAC audio soundtrack with sample rate >= 16 kHz",
                )
            )

    # 8. Decode & Content Fault Checks (Black frame detect & Volume detect)
    try:
        total_black, mean_vol, max_vol = run_media_fault_detect(path, has_audio=audio is not None, check=check)

        # Black frames check
        if probed_duration > 0 and total_black >= (probed_duration - 0.2):
            gates.append(
                HardGateCheck(
                    name="black_frame_check",
                    passed=False,
                    measured=f"{total_black:.2f}s black",
                    threshold=f"< {probed_duration - 0.2:.2f}s black",
                    error="Entire movie export is solid black frames",
                )
            )
        else:
            if total_black > probed_duration * 0.4:
                warnings.append(f"Notice: {total_black:.1f}s of video detected as dark/black.")
            gates.append(
                HardGateCheck(
                    name="black_frame_check",
                    passed=True,
                    measured=f"{total_black:.2f}s black duration",
                    threshold="no 100% blackout",
                )
            )

        # Silence check
        if audio_expected and max_vol is not None:
            if max_vol <= -85.0:
                warnings.append("Soundtrack is completely silent (max volume <= -85 dB).")
                gates.append(
                    HardGateCheck(
                        name="audio_levels",
                        passed=False,
                        measured=f"max {max_vol:.1f} dB, mean {mean_vol:.1f} dB",
                        threshold="> -85 dB for audible track",
                        error="Audio track is completely silent",
                    )
                )
            else:
                gates.append(
                    HardGateCheck(
                        name="audio_levels",
                        passed=True,
                        measured=f"max {max_vol:.1f} dB, mean {mean_vol:.1f} dB",
                        threshold="audible signal present",
                    )
                )
    except Exception as exc:
        gates.append(
            HardGateCheck(
                name="media_fault_detection",
                passed=False,
                measured="ffmpeg filter error",
                threshold="filters complete successfully",
                error=str(exc),
            )
        )

    # 9. Manifest & EDL alignment
    if script and "shots" in script:
        shots = script["shots"]
        shot_count = len(shots)
        if clips is not None:
            clip_count = len(clips)
            if shot_count == clip_count:
                gates.append(
                    HardGateCheck(
                        name="manifest_edl",
                        passed=True,
                        measured=f"{clip_count} clips match {shot_count} shots",
                        threshold=f"{shot_count} shots",
                    )
                )
            else:
                gates.append(
                    HardGateCheck(
                        name="manifest_edl",
                        passed=False,
                        measured=f"{clip_count} clips",
                        threshold=f"{shot_count} shots",
                        error=f"Clip count {clip_count} does not match script shot count {shot_count}",
                    )
                )

    # 10. Parent assets lineage & hashes
    if clips and store:
        missing_assets = []
        for clip in clips:
            try:
                asset_path = store.asset_path(clip["id"])[0]
                if not asset_path.exists():
                    missing_assets.append(clip["id"])
                elif clip.get("sha256") and digest(asset_path) != clip["sha256"]:
                    missing_assets.append(f"{clip['id']} (hash mismatch)")
            except Exception:
                missing_assets.append(clip["id"])
        if not missing_assets:
            gates.append(
                HardGateCheck(
                    name="asset_lineage",
                    passed=True,
                    measured=f"{len(clips)} source clips verified on disk",
                    threshold="all parent assets exist with valid sha256",
                )
            )
        else:
            gates.append(
                HardGateCheck(
                    name="asset_lineage",
                    passed=False,
                    measured=f"{len(missing_assets)} failed lineage checks",
                    threshold="all parent assets exist with valid sha256",
                    error=f"Lineage verification failed for: {', '.join(missing_assets)}",
                )
            )

    all_passed = all(g.passed for g in gates)
    status = "deterministic_passed" if all_passed else "hard_gates_failed"
    if all_passed:
        review_summary = (
            "Deterministic hard gates passed (container, H.264/AAC, YUV420p, frame count, "
            "media fault analysis); AI critic not performed."
        )
    else:
        failed_names = [g.name for g in gates if not g.passed]
        review_summary = f"Quality hard gate failed: {', '.join(failed_names)}"

    return QualityEvaluation(
        evaluated_at=evaluated_at,
        all_hard_gates_passed=all_passed,
        hard_gates=gates,
        cinematic_review_status=status,
        cinematic_review=review_summary,
        quality_tier="mock_demo" if is_mock else "local_ai_draft",
        cost_usd=0.0,
        cloud_tokens_used=0,
        warnings=warnings,
    )
