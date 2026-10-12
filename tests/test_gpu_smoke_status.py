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
