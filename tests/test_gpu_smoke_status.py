"""Development-only smoke harness fixtures. No GPU/native runtime is launched."""

import json
import sys

import pytest

from scripts import gpu_smoke
from studio.storage import atomic_json


def test_encoder_experiment_preserves_original_reports_and_uses_verified_separate_profile(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", "image", "--encoder-experiment", "--max-seconds", "300"])
    monkeypatch.setattr(gpu_smoke, "require_resources", lambda: {"fixture": True})
    original_report = tmp_path / "ops/evidence/real-gpu-image.json"
    original_status = tmp_path / "tools/gpu/image-status.json"
    atomic_json(original_report, {"status": "FAILED", "preserve": "original real failure"})
    atomic_json(original_status, {"code": "IMAGE_RAM_GUARD_STOP"})
    before = (original_report.read_bytes(), original_status.read_bytes())
    verified = []
    monkeypatch.setattr(
        gpu_smoke, "verify_installed", lambda root: verified.append(root) or {"fixture": True}
    )
    seen = []

    def blocked(provider, *args, **kwargs):
        seen.append(provider.config)
        raise RuntimeError("RESOURCE_BUSY: GPU smoke stopped below 2 GiB free RAM")

    monkeypatch.setattr(gpu_smoke.WanGPProvider, "image", blocked)
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        gpu_smoke.main()
    assert verified == [tmp_path]
    assert seen[0].image_model == gpu_smoke.ENCODER_PROFILE
    assert seen[0].memory_profile == 5 and seen[0].smart_memory_pinning is False
    assert before == (original_report.read_bytes(), original_status.read_bytes())
    reports = list((tmp_path / "ops/evidence").glob("encoder-experiment-image-*.json"))
    assert len(reports) == 1 and json.loads(reports[0].read_text())["status"] == "FAILED"
    summary = json.loads((tmp_path / "tools/gpu/encoder-image-status.json").read_text())
    assert summary["model"] == gpu_smoke.ENCODER_PROFILE and summary["code"] == "IMAGE_RAM_GUARD_STOP"
    reservation = (tmp_path / "tools/gpu/encoder-image-test-reservation.json").read_bytes()
    with pytest.raises(RuntimeError, match="EXPERIMENT_SPENT"):
        gpu_smoke.main()
    assert (
        len(seen) == 1
        and reservation == (tmp_path / "tools/gpu/encoder-image-test-reservation.json").read_bytes()
    )


@pytest.mark.parametrize("phase,ceiling", [("video", "300"), ("runtime", "300"), ("image", "301")])
def test_encoder_experiment_rejects_video_or_unbounded_testing(tmp_path, monkeypatch, phase, ceiling):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", phase, "--encoder-experiment", "--max-seconds", ceiling])
    monkeypatch.setattr(gpu_smoke, "require_resources", lambda: pytest.fail("Invalid phase reached hardware"))
    with pytest.raises(SystemExit):
        gpu_smoke.main()
    assert not (tmp_path / "data").exists()


def test_experimental_resource_gate_does_not_spend_the_approved_image_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", "image", "--encoder-experiment", "--max-seconds", "300"])

    def low_memory():
        raise RuntimeError("RESOURCE_BUSY: explicit insufficient-resource fixture")

    monkeypatch.setattr(gpu_smoke, "require_resources", low_memory)
    monkeypatch.setattr(
        gpu_smoke, "verify_installed", lambda *a: pytest.fail("Model checks ran before resource gate")
    )
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        gpu_smoke.main()
    assert not (tmp_path / "tools/gpu/encoder-image-test-reservation.json").exists()
    assert not (tmp_path / "tools/gpu/encoder-image-status.json").exists()
    reports = list((tmp_path / "ops/evidence").glob("encoder-experiment-image-*.json"))
    assert len(reports) == 1 and not json.loads(reports[0].read_text()).get("image_attempted")


def test_resource_failure_does_not_erase_last_actual_runtime_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", "runtime"])
    path = tmp_path / "tools/gpu/runtime-status.json"
    previous = {"code": "OS_POLICY_BLOCKED", "checked_at": 123, "installation": str(tmp_path / "wan")}
    atomic_json(path, previous)

    def busy():
        raise RuntimeError("RESOURCE_BUSY: fixture lacks free RAM")

    monkeypatch.setattr(gpu_smoke, "require_resources", busy)
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        gpu_smoke.main()
    assert json.loads(path.read_text()) == previous
    report = json.loads((tmp_path / "ops/evidence/real-gpu-runtime.json").read_text())
    assert report["status"] == "FAILED" and not report.get("runtime_attempted")


def test_attempted_native_block_updates_summary_without_exposing_paths_in_message(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", "runtime"])
    monkeypatch.setattr(gpu_smoke, "require_resources", lambda: {"fixture": True})

    def blocked(*args, **kwargs):
        raise RuntimeError("OS_POLICY_BLOCKED: fixture blocked native dependency")

    monkeypatch.setattr(gpu_smoke.WanGPProvider, "request", blocked)
    with pytest.raises(RuntimeError, match="OS_POLICY_BLOCKED"):
        gpu_smoke.main()
    summary = json.loads((tmp_path / "tools/gpu/runtime-status.json").read_text())
    assert summary["code"] == "OS_POLICY_BLOCKED"
    assert len(summary["evidence_sha256"]) == 64
    assert "error" not in summary


def test_parent_guard_rejects_low_or_unknown_ram_and_retains_samples(monkeypatch):
    monkeypatch.setattr(gpu_smoke.time, "monotonic", lambda: 10)
    monkeypatch.setattr(gpu_smoke, "memory_status", lambda: {"available": True, "free_gb": 1.99})
    report = {}
    with pytest.raises(RuntimeError, match="below 2 GiB"):
        gpu_smoke.smoke_guard(report, 0, 600)()
    assert report["parent_memory_samples"][0]["free_gb"] == 1.99
    monkeypatch.setattr(gpu_smoke, "memory_status", lambda: {"available": False})
    with pytest.raises(RuntimeError, match="lost its RAM counters"):
        gpu_smoke.smoke_guard({}, 0, 600)()


def test_parent_guard_has_a_wall_time_ceiling_before_another_sample(monkeypatch):
    monkeypatch.setattr(gpu_smoke.time, "monotonic", lambda: 601)
    monkeypatch.setattr(gpu_smoke, "memory_status", lambda: pytest.fail("Sampled after deadline"))
    with pytest.raises(RuntimeError, match="600-second ceiling"):
        gpu_smoke.smoke_guard({}, 0, 600)()


def test_image_ram_stop_is_separate_from_successful_runtime_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", "image", "--profile", "5"])
    monkeypatch.setattr(gpu_smoke, "require_resources", lambda: {"fixture": True})
    runtime_path = tmp_path / "tools/gpu/runtime-status.json"
    previous = {"code": "RUNTIME_DISCOVERED_NOT_INFERENCE", "checked_at": 123, "installation": "fixture"}
    atomic_json(runtime_path, previous)

    def blocked(*args, **kwargs):
        raise RuntimeError("RESOURCE_BUSY: GPU smoke stopped below 2 GiB free RAM")

    monkeypatch.setattr(gpu_smoke.WanGPProvider, "image", blocked)
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        gpu_smoke.main()
    assert json.loads(runtime_path.read_text()) == previous
    image = json.loads((tmp_path / "tools/gpu/image-status.json").read_text())
    assert image["code"] == "IMAGE_RAM_GUARD_STOP" and image["memory_profile"] == 5


def test_explicit_smoke_transfer_option_is_preserved_in_request_and_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gpu_smoke", "image", "--profile", "5", "--disable-smart-pinning"])
    monkeypatch.setattr(gpu_smoke, "require_resources", lambda: {"fixture": True})
    seen = []

    def blocked(provider, *args, **kwargs):
        seen.append(provider.config.smart_memory_pinning)
        raise RuntimeError("RESOURCE_BUSY: GPU smoke stopped below 2 GiB free RAM")

    monkeypatch.setattr(gpu_smoke.WanGPProvider, "image", blocked)
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        gpu_smoke.main()
    assert seen == [False]
    assert json.loads((tmp_path / "tools/gpu/image-status.json").read_text())["smart_memory_pinning"] is False
