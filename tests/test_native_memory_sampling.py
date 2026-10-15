"""Development counter fixtures and harmless child processes; no GPU/models loaded."""

import ctypes
import json
import os
import sys
import time

import pytest

from scripts.gpu_smoke import smoke_guard
from studio import media
from studio.providers import PARENT_MEMORY_CHECK_SECONDS, WanGPConfig, WanGPProvider


@pytest.mark.parametrize("bad", [None, True, "3", float("nan"), float("inf"), -1])
def test_smoke_rejects_missing_invalid_or_nonfinite_memory(monkeypatch, bad):
    monkeypatch.setattr("scripts.gpu_smoke.memory_status", lambda: {"available": True, "free_gb": bad})
    with pytest.raises(RuntimeError, match="RESOURCE_UNKNOWN"):
        smoke_guard({}, time.monotonic(), 20)()


def test_smoke_samples_at_half_second_without_skipping_deadline_or_controls(monkeypatch):
    now = [0.0]
    readings = iter([3.0, 1.9])
    monkeypatch.setattr("scripts.gpu_smoke.time.monotonic", lambda: now[0])
    monkeypatch.setattr(
        "scripts.gpu_smoke.memory_status", lambda: {"available": True, "free_gb": next(readings)}
    )
    report = {}
    check = smoke_guard(report, 0, 20)
    check()
    now[0] = 0.49
    check()
    assert len(report["parent_memory_samples"]) == 1
    now[0] = 0.5
    with pytest.raises(RuntimeError, match="below 2 GiB"):
        check()
    assert [r["seconds"] for r in report["parent_memory_samples"]] == [0.0, 0.5]
    assert report["parent_memory_sample_interval_seconds"] == 0.5
    now[0] = 20.01
    with pytest.raises(RuntimeError, match="TIMEOUT"):
        check()


@pytest.mark.parametrize(
    "reading,code", [(1.9, "RESOURCE_BUSY"), (float("nan"), "RESOURCE_UNKNOWN"), (None, "RESOURCE_UNKNOWN")]
)
def test_provider_samples_sooner_and_preserves_request(tmp_path, monkeypatch, reading, code):
    provider = WanGPProvider(WanGPConfig(license_reviewed=True), tmp_path)
    monkeypatch.setattr(provider, "configured", lambda: True)
    monkeypatch.setattr("studio.providers.require_resources", lambda: None)
    now, samples, controls = [0.0], [], []
    monkeypatch.setattr("studio.providers.time.monotonic", lambda: now[0])

    def memory():
        samples.append(now[0])
        return {"available": True, "free_gb": 3.0 if len(samples) == 1 else reading}

    def run(argv, check, **kwargs):
        now[0] = 0.49
        check()
        assert samples == [0.0]
        now[0] = 0.5
        check()
        pytest.fail("Provider did not stop at the next sample")

    monkeypatch.setattr("studio.diagnostics.memory_status", memory)
    monkeypatch.setattr("studio.providers.media.run", run)
    with pytest.raises(RuntimeError, match=code):
        provider.request("image", "development fixture", tmp_path, lambda: controls.append(now[0]))
    assert samples == [0.0, 0.5] and controls == [0.0, 0.49, 0.5]
    request = json.loads((tmp_path / "provider-request.json").read_text())
    assert request["parent_memory_sample_interval_seconds"] == PARENT_MEMORY_CHECK_SECONDS == 0.5
    assert not (tmp_path / "provider-result.json").exists()


def process_alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259
    finally:
        kernel.CloseHandle(handle)


def test_low_memory_stop_releases_actual_owned_child_without_running_vendor(tmp_path, monkeypatch):
    # Isolated fake bridge writes its PID and sleeps; native runtime is never imported.
    studio = tmp_path / "studio"
    studio.mkdir()
    pid_path = tmp_path / "fixture-pid.txt"
    (studio / "vendor_bridge.py").write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(media, "ROOT", tmp_path)
    provider = WanGPProvider(WanGPConfig(license_reviewed=True, python=sys.executable), tmp_path)
    monkeypatch.setattr(provider, "configured", lambda: True)
    monkeypatch.setattr("studio.providers.require_resources", lambda: None)
    began, observed_live = time.monotonic(), []

    def memory():
        if time.monotonic() - began > 8:
            raise RuntimeError("Fixture child did not start in time")
        if pid_path.exists():
            observed_live.append(process_alive(int(pid_path.read_text())))
            return {"available": True, "free_gb": 1.9}
        return {"available": True, "free_gb": 3.0}

    monkeypatch.setattr("studio.diagnostics.memory_status", memory)
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        provider.request("image", "development fixture", output, lambda: None)
    assert observed_live == [True]
    deadline = time.monotonic() + 3
    while process_alive(int(pid_path.read_text())) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not process_alive(int(pid_path.read_text()))
    assert not (output / "provider-result.json").exists()
    assert (output / "provider-request.json").is_file()
