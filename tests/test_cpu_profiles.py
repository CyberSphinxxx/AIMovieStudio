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
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        with local_story.cpu_server(profile=profile):
            pytest.fail("Loaded despite busy RAM")


def test_changed_weights_rejected_before_any_runtime_launch(tmp_path, monkeypatch):
    folder = tmp_path / "tools/story"
    folder.mkdir(parents=True)
    (folder / "llama-server.exe").write_bytes(b"fixture-not-executable")
    (folder / "weights.gguf").write_bytes(b"wrong")
    monkeypatch.setattr(local_story, "ROOT", tmp_path)
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
