"""Counter fault fixtures only; no model/server is loaded."""

import pytest

from studio import local_story


@pytest.mark.parametrize("free", [None, True, "8", -1, float("nan"), float("inf")])
@pytest.mark.parametrize("phase", ["startup", "ongoing"])
def test_cpu_rejects_invalid_counter_as_unknown(monkeypatch, free, phase):
    monkeypatch.setattr(local_story, "memory_status", lambda: {"available": True, "free_gb": free})
    with pytest.raises(RuntimeError, match="RESOURCE_UNKNOWN"):
        if phase == "startup":
            local_story.require_startup_memory("cpu_4b")
        else:
            local_story.observe_process(None, None)


@pytest.mark.parametrize("phase", ["startup", "ongoing"])
def test_cpu_counter_io_error_fails_closed_with_actionable_reason(monkeypatch, phase):
    def unavailable():
        raise OSError("Development fixture counter unavailable")

    monkeypatch.setattr(local_story, "memory_status", unavailable)
    with pytest.raises(RuntimeError, match="RESOURCE_UNKNOWN"):
        if phase == "startup":
            local_story.require_startup_memory("cpu_4b")
        else:
            local_story.observe_process(None, None)


@pytest.mark.parametrize("profile,minimum", [("small_cpu", 2), ("cpu_1_5b", 5), ("cpu_4b", 7)])
def test_valid_cpu_startup_thresholds_remain_unchanged(monkeypatch, profile, minimum):
    memory = {"available": True, "free_gb": minimum}
    monkeypatch.setattr(local_story, "memory_status", lambda: memory)
    local_story.require_startup_memory(profile)
    memory["free_gb"] = minimum - 0.01
    with pytest.raises(RuntimeError, match=f"RESOURCE_BUSY.*{minimum} GiB"):
        local_story.require_startup_memory(profile)


def test_valid_low_ram_is_retained_but_bad_readings_cannot_pollute_json(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(local_story, "process_rss", lambda _: 123)
    monkeypatch.setattr(local_story, "memory_status", lambda: {"available": True, "free_gb": float("nan")})
    observations = []
    with pytest.raises(RuntimeError, match="RESOURCE_UNKNOWN"):
        local_story.observe_process(observations.append, SimpleNamespace(pid=42))
    assert len(observations) == 1
    assert observations[0]["memory"]["available"] is False
    assert "free_gb" not in observations[0]["memory"]


@pytest.mark.parametrize(
    "change",
    [
        {"used_mb": float("nan")},
        {"used_mb": True},
        {"used_mb": None},
        {"used_mb": -1},
        {"used_mb": 7000},
        {"temperature_c": float("inf")},
        {"temperature_c": False},
        {"temperature_c": -1},
        {"total_mb": 0},
        {"total_mb": None},
    ],
)
def test_bad_gpu_readings_fail_admission_and_queue_waits_for_counters(monkeypatch, tmp_path, change):
    from studio.providers import WanGPProvider, require_resources
    from studio.resource_wait import probe

    memory = {"available": True, "free_gb": 8}
    gpu = {"available": True, "total_mb": 6144, "used_mb": 1024, "temperature_c": 60} | change
    monkeypatch.setattr("studio.diagnostics.hardware", lambda **kw: {"memory": memory, "gpu": gpu})
    monkeypatch.setattr("studio.resource_wait.memory_status", lambda: memory)
    monkeypatch.setattr("studio.resource_wait.inference_busy", lambda: False)
    monkeypatch.setattr(WanGPProvider, "configured", lambda self: True)
    with pytest.raises(RuntimeError, match="RESOURCE_UNKNOWN"):
        require_resources()
    reason = probe({"stage": "FRAME"}, {"wangp": {}}, {"backend": "local"}, lambda: gpu)
    assert reason.code == "COUNTERS_UNKNOWN"


def test_bad_ram_is_not_admitted_by_gpu_startup(monkeypatch):
    from studio.providers import require_resources

    gpu = {"available": True, "total_mb": 6144, "used_mb": 1024, "temperature_c": 60}
    monkeypatch.setattr(
        "studio.diagnostics.hardware",
        lambda **kw: {
            "memory": {"available": True, "free_gb": float("nan")},
            "gpu": gpu,
        },
    )
    with pytest.raises(RuntimeError, match="RESOURCE_UNKNOWN"):
        require_resources()
