"""Sampler fixtures verify durability, not native model fit or generation quality."""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from studio.vendor_telemetry import Sampler


def sample(value=10):
    return {
        "seconds": 1,
        "rss_bytes": value,
        "available_ram_bytes": 100,
        "global_vram_bytes": 20,
        "temperature_c": 30,
    }


def test_periodic_snapshots_bound_history_but_preserve_lifetime_extrema(tmp_path):
    path = tmp_path / "telemetry.json"
    sampler = Sampler(path)
    sampler.mark_phase("runtime_initialization")
    sampler.record(sample(500))
    for _ in range(125):
        sampler.record(sample())
    data = json.loads(path.read_text())
    assert data["sample_count"] == 126 and len(data["samples"]) == 120
    assert data["peak_rss_bytes_sampled"] == 500
    assert data["min_available_ram_bytes_sampled"] == 100
    assert data["phase"] == "runtime_initialization" and not data["sampler_closed"]
    sampler.on_progress(SimpleNamespace(phase="loading_model", status="private prompt text"))
    data = json.loads(path.read_text())
    assert data["phase"] == "loading_model" and "private prompt text" not in path.read_text()
    sampler.on_progress(SimpleNamespace(phase="unrecognized-private-text"))
    assert json.loads(path.read_text())["phase"] == "loading_model"


def test_disk_write_failure_retains_last_snapshot_without_masking_generation(tmp_path, monkeypatch):
    path = tmp_path / "telemetry.json"
    sampler = Sampler(path)
    sampler.record(sample())
    original = path.read_bytes()
    monkeypatch.setattr(Path, "replace", lambda *args: (_ for _ in ()).throw(OSError("fixture disk full")))
    sampler.mark_phase("loading_model")
    assert path.read_bytes() == original
    assert sampler.errors == ["fixture disk full"]


def test_actual_terminated_subprocess_keeps_last_atomic_measurements(tmp_path):
    path = tmp_path / "telemetry.json"
    code = """
import sys, time
from pathlib import Path
from studio.vendor_telemetry import Sampler
sampler = Sampler(Path(sys.argv[1]))
sampler.mark_phase('loading_model')
sampler.record({'seconds': 1, 'rss_bytes': 100, 'available_ram_bytes': 200, 'global_vram_bytes': 300, 'temperature_c': 40})
while True:
    time.sleep(0.1)
"""
    # A development fixture process, no GPU imports/models and no vendor execution.
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if path.exists() and json.loads(path.read_text()).get("sample_count") == 1:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Sampler did not save while child was running")
        process.kill()
        process.wait(timeout=5)
        data = json.loads(path.read_text())
        assert data["phase"] == "loading_model" and data["peak_rss_bytes_sampled"] == 100
        assert not data["sampler_closed"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
