"""Development-only smoke harness fixtures. No GPU/native runtime is launched."""

import json
import sys

import pytest

from scripts import gpu_smoke
from studio.storage import atomic_json


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
