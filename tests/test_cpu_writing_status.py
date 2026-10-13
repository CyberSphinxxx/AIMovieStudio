import json
import sys

import pytest

from studio.setup_status import read_cpu_status, classify


def evidence(root):
    return {
        "installation": str(root / "tools/story"),
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",
        "code": "STRUCTURE_PASS_QUALITY_FAILED",
        "checked_at": 123,
        "elapsed_seconds": 172.625,
        "sampled_peak_server_rss_bytes": 2013237248,
    }


def test_observed_cpu_structure_does_not_become_a_quality_or_video_pass(tmp_path):
    path = tmp_path / "tools/story/cpu-writing-status.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(evidence(tmp_path)))
    record = read_cpu_status(tmp_path)
    result = classify(
        [{"id": "cpu-1-5b", "available": True, "is_mock": False, "message": "Experimental."}],
        {"available": True, "free_gb": 6},
        last_cpu=record,
    )[0]
    assert result["status"] == "Tested · writing needs work" and result["verified"] is False
    assert "manual writing quality failed" in result["message"] and "No image/video" in result["message"]
    busy = classify(
        [{"id": "cpu-1-5b", "available": True, "message": "Experimental."}],
        {"available": True, "free_gb": 2},
        last_cpu=record,
    )[0]
    assert busy["status"] == "Needs free RAM" and busy["last_check_at"] == 123


def test_4b_observation_is_separate_and_uses_seven_gib_guard(tmp_path):
    path = tmp_path / "tools/story/cpu-4b-writing-status.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(evidence(tmp_path) | {"model": "Qwen3-4B-Instruct-2507-Q4_K_M"}))
    assert read_cpu_status(tmp_path) is None
    record = read_cpu_status(tmp_path, "cpu_4b")
    provider = {"id": "cpu-4b", "available": True, "message": "Experimental."}
    busy = classify([provider.copy()], {"available": True, "free_gb": 6.99}, last_cpu_4b=record)[0]
    assert busy["status"] == "Needs free RAM" and "minimum 7 GiB" in busy["message"]
    untested = classify([provider.copy()], {"available": True, "free_gb": 8}, last_cpu=evidence(tmp_path))[0]
    assert untested["status"] == "Installed · untested" and "last_check_at" not in untested


@pytest.mark.parametrize(
    "change",
    [
        {"code": "PASS"},
        {"model": "another-model"},
        {"checked_at": float("nan")},
        {"installation": "another-folder"},
        {"sampled_peak_server_rss_bytes": 0},
    ],
)
def test_unmatched_or_unproven_cpu_summary_is_ignored(tmp_path, change):
    path = tmp_path / "tools/story/cpu-writing-status.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(evidence(tmp_path) | change))
    assert read_cpu_status(tmp_path) is None


@pytest.mark.parametrize("value", ["0", "601"])
def test_cpu_test_ceiling_is_bounded_before_project_or_model_creation(monkeypatch, value):
    from scripts import story_batch_smoke

    monkeypatch.setattr(sys, "argv", ["story_batch_smoke", "--max-seconds", value])
    monkeypatch.setattr(
        story_batch_smoke, "Store", lambda *_args: pytest.fail("Created project despite bad limit")
    )
    with pytest.raises(SystemExit) as error:
        story_batch_smoke.main()
    assert error.value.code == 2
