"""Tests for deterministic cinematic quality evaluation and media fault gates (F7.02)."""

import json
from pathlib import Path

import pytest

from studio import media
from studio.quality import evaluate_export
from studio.shot_revisions import RetakeRequest, enqueue_retake
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


def generate_pattern(
    output: Path,
    *,
    video_filter: str = "testsrc=s=360x640:d=5:r=24",
    audio_filter: str = "sine=f=440:d=5:r=48000",
    pix_fmt: str = "yuv420p",
    duration: float = 5.0,
):
    args = [
        media.binary("ffmpeg"),
        "-y",
        "-f",
        "lavfi",
        "-i",
        video_filter,
    ]
    if audio_filter:
        args.extend(["-f", "lavfi", "-i", audio_filter])
    args.extend([
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        pix_fmt,
        "-t",
        str(duration),
    ])
    if audio_filter:
        args.extend(["-c:a", "aac"])
    args.append(str(output))
    media.run(args)


def test_evaluate_export_blackout_and_silence_failure(tmp_path):
    black_path = tmp_path / "all_black_silent.mp4"
    generate_pattern(
        black_path,
        video_filter="color=c=black:s=360x640:d=5:r=24",
        audio_filter="anullsrc=r=48000:cl=mono",
        duration=5.0,
    )

    evaluation = evaluate_export(
        path=black_path,
        size=(360, 640),
        target_duration=5.0,
        audio_expected=True,
        is_mock=True,
    )

    assert evaluation.all_hard_gates_passed is False
    assert evaluation.cinematic_review_status == "hard_gates_failed"

    gates = {g.name: g for g in evaluation.hard_gates}
    assert gates["black_frame_check"].passed is False
    assert "solid black" in gates["black_frame_check"].error
    assert gates["audio_levels"].passed is False
    assert "silent" in gates["audio_levels"].error.lower()


def test_evaluate_export_wrong_pixel_format_and_validate_video(tmp_path):
    yuv444_path = tmp_path / "wrong_pix_fmt.mp4"
    generate_pattern(
        yuv444_path,
        video_filter="testsrc=s=360x640:d=5:r=24",
        audio_filter="sine=f=440:d=5:r=48000",
        pix_fmt="yuv444p",
        duration=5.0,
    )

    evaluation = evaluate_export(
        path=yuv444_path,
        size=(360, 640),
        target_duration=5.0,
        audio_expected=True,
        is_mock=True,
    )

    gates = {g.name: g for g in evaluation.hard_gates}
    assert gates["pixel_format"].passed is False
    assert "yuv444p" in gates["pixel_format"].measured
    assert evaluation.all_hard_gates_passed is False

    with pytest.raises(RuntimeError, match="yuv420p"):
        media.validate_video(yuv444_path, (360, 640), 5.0, audio=True)


def test_evaluate_export_dimension_and_duration_discrepancy(tmp_path):
    wrong_dim_path = tmp_path / "wrong_dim.mp4"
    generate_pattern(
        wrong_dim_path,
        video_filter="testsrc=s=640x360:d=7:r=24",
        audio_filter="sine=f=440:d=7:r=48000",
        duration=7.0,
    )

    evaluation = evaluate_export(
        path=wrong_dim_path,
        size=(360, 640),  # Target is portrait, but video is landscape
        target_duration=5.0,  # Target is 5s, but video is 7s
        audio_expected=True,
        is_mock=True,
    )

    gates = {g.name: g for g in evaluation.hard_gates}
    assert gates["dimensions"].passed is False
    assert gates["duration"].passed is False
    assert evaluation.all_hard_gates_passed is False


def test_evaluate_export_manifest_edl_and_asset_lineage(tmp_path, store, spec):
    valid_path = tmp_path / "valid_sample.mp4"
    generate_pattern(valid_path, duration=5.0)

    # 1. Manifest EDL mismatch: script has 3 shots, but only 2 clips passed
    script = {
        "shots": [
            {"id": "s1", "duration": 2.0},
            {"id": "s2", "duration": 2.0},
            {"id": "s3", "duration": 1.0},
        ]
    }
    clips = [{"id": "clip1"}, {"id": "clip2"}]

    evaluation = evaluate_export(
        path=valid_path,
        size=(360, 640),
        target_duration=5.0,
        audio_expected=True,
        is_mock=True,
        script=script,
        clips=clips,
        store=store,
    )

    gates = {g.name: g for g in evaluation.hard_gates}
    assert gates["manifest_edl"].passed is False
    assert "2 clips" in gates["manifest_edl"].measured
    assert gates["asset_lineage"].passed is False  # clips don't exist in store


def test_pipeline_export_and_recut_includes_quality_evaluation(store, spec):
    spec.target_seconds = 5
    spec.kind = "drama"
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)

    worker = Worker(store)
    project = produce_until(store, worker, pid)
    assert project["status"] == "COMPLETED"

    # Verify export asset has quality evaluation metadata
    movie = next(a for a in project["assets"] if a["role"] == "export")
    meta = movie["metadata"]
    assert "quality_evaluation" in meta
    quality = meta["quality_evaluation"]
    assert quality["all_hard_gates_passed"] is True
    assert quality["cinematic_review_status"] == "deterministic_passed"
    assert quality["cost_usd"] == 0.0
    assert quality["cloud_tokens_used"] == 0
    assert meta["cinematic_review"] == quality["cinematic_review"]

    # Verify manifest.json on disk includes quality evaluation
    manifest_asset = next(a for a in project["assets"] if a["role"] == "manifest")
    manifest_path = store.asset_path(manifest_asset["id"])[0]
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "quality_evaluation" in manifest_data
    assert manifest_data["quality_evaluation"]["all_hard_gates_passed"] is True

    # Test that a retake (RECUT) also evaluates quality and updates metadata
    shot_id = project["episodes"][0]["script"]["shots"][0]["id"]
    retake_req = RetakeRequest(
        source_export_id=movie["id"],
        revision=project["revision"],
        idempotency_key="quality-eval-retake-key-1",
        seed=12345,
    )
    enqueue_retake(store, pid, 1, shot_id, retake_req)
    recut_project = produce_until(store, worker, pid)

    recut_movie = next(
        a for a in reversed(recut_project["assets"]) if a["role"] == "export-edition"
    )
    recut_meta = recut_movie["metadata"]
    assert "quality_evaluation" in recut_meta
    assert recut_meta["quality_evaluation"]["all_hard_gates_passed"] is True
    assert recut_meta["cinematic_review_status"] == "deterministic_passed"
    assert recut_meta["edition"] == 2
