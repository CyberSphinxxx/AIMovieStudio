import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient

from studio import local_story
from studio.api import create_app
from studio.diagnostics import process_rss


def test_missing_selected_cpu_model_fails_without_launch_or_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(local_story, "ROOT", tmp_path)
    monkeypatch.setattr(
        local_story.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Launched missing model")
    )
    assert local_story.SmallCPUStory(profile="cpu_1_5b").model == "Qwen2.5-1.5B-Instruct-Q4_K_M"
    with pytest.raises(RuntimeError, match="MISSING_MODEL"):
        with local_story.cpu_server(profile="cpu_1_5b"):
            pytest.fail("Accepted missing model")


@pytest.mark.parametrize(
    "profile,free,available",
    [("cpu_1_5b", 4.99, True), ("cpu_1_5b", 8, False), ("cpu_4b", 6.99, True), ("cpu_4b", 8, False)],
)
def test_cpu_ram_guard_runs_before_launch(tmp_path, monkeypatch, profile, free, available):
    folder = tmp_path / "tools/story"
    folder.mkdir(parents=True)
    (folder / "llama-server.exe").write_bytes(b"fixture-not-executable")
    (folder / local_story.CPU_PROFILES[profile][1]).write_bytes(b"fixture-not-model")
    monkeypatch.setattr(local_story, "ROOT", tmp_path)
    monkeypatch.setattr(local_story, "memory_status", lambda: {"available": available, "free_gb": free})
    monkeypatch.setattr(
        local_story.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Launched despite busy RAM")
    )
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY" if available else "RESOURCE_UNKNOWN"):
        with local_story.cpu_server(profile=profile):
            pytest.fail("Loaded despite busy RAM")


def test_changed_weights_rejected_before_any_runtime_launch(tmp_path, monkeypatch):
    folder = tmp_path / "tools/story"
    folder.mkdir(parents=True)
    (folder / "llama-server.exe").write_bytes(b"fixture-not-executable")
    (folder / "weights.gguf").write_bytes(b"wrong")
    monkeypatch.setattr(local_story, "ROOT", tmp_path)
    monkeypatch.setattr(local_story, "memory_status", lambda: {"available": True, "free_gb": 8})
    monkeypatch.setitem(
        local_story.CPU_PROFILES,
        "small_cpu",
        ("fixture", "weights.gguf", 5, hashlib.sha256(b"right").hexdigest()),
    )
    monkeypatch.setattr(
        local_story.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Launched corrupt model")
    )
    with pytest.raises(RuntimeError, match="BAD_MODEL"):
        with local_story.cpu_server():
            pytest.fail("Accepted corrupt weights")


@pytest.mark.parametrize("profile,provider_id", [("cpu_1_5b", "cpu-1-5b"), ("cpu_4b", "cpu-4b")])
def test_explicit_profile_is_persisted_in_job_configuration(tmp_path, spec, profile, provider_id):
    with TestClient(create_app(tmp_path, run_worker=False)) as client:
        response = client.patch("/api/settings", json={"story_engine": profile})
        assert response.status_code == 200
        created = client.post("/api/projects", json=spec.model_dump()).json()
        assert created["jobs"][0]["config"].find(json.dumps(profile)) >= 0
        provider = next(p for p in client.get("/api/providers").json()["providers"] if p["id"] == provider_id)
        assert provider["is_mock"] is False and provider["verified"] is False


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only process counters")
def test_actual_own_process_memory_counter():
    assert process_rss(os.getpid()) > 0


def test_cpu_timeout_has_actionable_error_without_automatic_retry_or_fallback():
    import httpx

    calls = []

    class Client:
        def post(self, path, json):
            calls.append(path)
            raise httpx.ReadTimeout("fixture stalled writing response")

    with pytest.raises(RuntimeError, match="TIMEOUT.*180 seconds") as caught:
        local_story.cpu_post(Client(), {"model": "test"}, lambda: None)
    assert calls == ["/v1/chat/completions"]
    assert "Earlier checkpoints are preserved" in str(caught.value)
    assert isinstance(caught.value.__cause__, httpx.ReadTimeout)


@pytest.mark.parametrize(
    "memory,code",
    [
        ({"available": True, "free_gb": 1.99}, "RESOURCE_BUSY"),
        ({"available": False}, "RESOURCE_UNKNOWN"),
        ({"available": True, "free_gb": None}, "RESOURCE_UNKNOWN"),
    ],
)
def test_cpu_ongoing_ram_guard_does_not_require_test_observer(monkeypatch, memory, code):
    monkeypatch.setattr(local_story, "memory_status", lambda: memory)
    with pytest.raises(RuntimeError, match=code):
        local_story.observe_process(None, None)


def test_cpu_memory_observation_preserves_measured_failure_sample(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(local_story, "memory_status", lambda: {"available": True, "free_gb": 1.5})
    monkeypatch.setattr(local_story, "process_rss", lambda pid: 123)
    samples = []
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        local_story.observe_process(samples.append, SimpleNamespace(pid=42))
    assert samples == [{"pid": 42, "rss_bytes": 123, "memory": {"available": True, "free_gb": 1.5}}]


def test_startup_guard_is_rechecked_after_hashing_before_launch(tmp_path, monkeypatch):
    folder = tmp_path / "tools/story"
    folder.mkdir(parents=True)
    (folder / "llama-server.exe").write_bytes(b"fixture-not-executable")
    (folder / "weights.gguf").write_bytes(b"fixture")
    monkeypatch.setattr(local_story, "ROOT", tmp_path)
    monkeypatch.setitem(local_story.CPU_PROFILES, "cpu_4b", ("fixture", "weights.gguf", 7, "fixture-sha"))
    available = iter([8, 6.99])
    monkeypatch.setattr(local_story, "memory_status", lambda: {"available": True, "free_gb": next(available)})
    monkeypatch.setattr(local_story, "digest", lambda path: "fixture-sha")
    monkeypatch.setattr(
        local_story.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Launched after RAM dropped")
    )
    with pytest.raises(RuntimeError, match="requires at least 7 GiB"):
        with local_story.cpu_server(profile="cpu_4b"):
            pytest.fail("Passed stale memory check")
