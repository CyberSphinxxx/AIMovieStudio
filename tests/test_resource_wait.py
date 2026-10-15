"""Explicit development counter fixtures; none of these tests prove native model fit."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from studio import resource_wait as resources, media
from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.storage import Store
from studio.worker import Worker
from tests.test_crash import await_condition
from tests.test_pipeline import produce_until, set_silent

BUSY = resources.ResourceReason(code="MEMORY_BUSY", message="Development fixture: waiting for free memory.")


def enqueue(store, spec):
    pid, _ = store.create(spec)
    jid = store.enqueue(pid)
    return pid, jid


def busy_worker(store):
    return Worker(store, resource_probe=lambda *_: BUSY)


def test_wait_does_not_claim_write_canon_or_spend_attempts(store, spec, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("studio.worker.time.time", lambda: now[0])
    pid, _ = enqueue(store, spec)
    calls = []
    worker = Worker(store, resource_probe=lambda *_: calls.append(True) or BUSY)
    assert worker.claim() is None
    project = store.get(pid)
    job = project["jobs"][0]
    assert job["state"] == project["status"] == resources.WAIT_STATE
    assert job["error"] is None
    assert job["steps"][0]["attempts"] == 0
    assert project["assets"] == project["canon"] == []
    saved = job["resource_wait"]
    for _ in range(5):
        assert worker.claim() is None
    assert len(calls) == 1
    now[0] += 16
    assert worker.claim() is None
    assert len(calls) == 2
    assert store.get(pid)["jobs"][0]["resource_wait"] == saved
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='resource_wait'").fetchone()[0] == 1
    worker.resource_probe = lambda *_: None
    now[0] += 16
    step = worker.claim()
    assert step["attempts"] == 1
    assert step["id"] == saved["step_id"]
    assert store.get(pid)["jobs"][0]["resource_wait"] is None


def test_waiting_job_does_not_starve_other_movies(store, spec):
    pid, _ = enqueue(store, spec)
    second, _ = enqueue(store, spec.model_copy(update={"idempotency_key": "another-project"}))
    worker = Worker(store, resource_probe=lambda step, *_: BUSY if step["project_id"] == pid else None)
    assert worker.claim()["project_id"] == second
    assert store.get(pid)["status"] == resources.WAIT_STATE


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_user_controls_and_resume_bypass_counter_cache(store, spec, action):
    pid, _ = enqueue(store, spec)
    worker = busy_worker(store)
    worker.claim()
    store.control(pid, action)
    worker.resource_probe = lambda *_: None
    assert worker.claim() is None
    assert store.get(pid)["jobs"][0]["state"] == {"pause": "PAUSED", "cancel": "CANCELLED"}[action]
    if action == "pause":
        store.control(pid, "resume")
        assert worker.claim()["attempts"] == 1
    else:
        with pytest.raises(ValueError, match="terminal"):
            store.control(pid, "resume")


def test_deadline_survives_reopen_expires_and_explicit_retry_starts_new_wait(store, spec, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("studio.worker.time.time", lambda: now[0])
    pid, jid = enqueue(store, spec)
    busy_worker(store).claim()
    original = store.get(pid)["jobs"][0]["resource_wait"]
    reopened = Store(store.root)
    worker = busy_worker(reopened)
    worker.recover()
    worker.claim()
    assert reopened.get(pid)["jobs"][0]["resource_wait"] == original
    now[0] = original["deadline"]
    worker.claim()
    job = reopened.get(pid)["jobs"][0]
    assert job["state"] == "FAILED" and "RESOURCE_WAIT_EXPIRED" in job["error"]
    assert job["steps"][0]["attempts"] == 0
    reopened.control(pid, "resume")
    worker.claim()
    assert reopened.get(pid)["jobs"][0]["resource_wait"]["since"] == now[0]
    assert reopened.enqueue(pid) == jid


@pytest.mark.parametrize("corruption", ["missing", "broken-json", "unbounded-deadline"])
def test_corrupt_wait_fails_closed_without_loading(store, spec, corruption):
    pid, jid = enqueue(store, spec)
    busy_worker(store).claim()
    with store.connect() as db:
        if corruption == "missing":
            db.execute("DELETE FROM events WHERE kind='resource_wait'")
        else:
            wait = resources.load_wait(db, jid).model_dump()
            wait["deadline"] += resources.WAIT_SECONDS
            db.execute(
                "UPDATE events SET data=? WHERE kind='resource_wait'",
                ("{" if corruption == "broken-json" else json.dumps(wait),),
            )
    assert "needs review" in store.get(pid)["jobs"][0]["error"]
    assert busy_worker(store).claim() is None
    assert store.get(pid)["jobs"][0]["state"] == "FAILED"


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_control_race_between_counters_and_claim_is_authoritative(store, spec, action):
    pid, _ = enqueue(store, spec)

    def racing_probe(*_):
        store.control(pid, action)
        return None

    assert Worker(store, resource_probe=racing_probe).claim() is None
    job = store.get(pid)["jobs"][0]
    assert job["steps"][0]["attempts"] == 0
    assert job["state"] == action.upper() + ("D" if action == "pause" else "LED")


def test_probe_failure_does_not_kill_scheduler_or_starve_next_job(store, spec):
    pid, _ = enqueue(store, spec)
    second, _ = enqueue(store, spec.model_copy(update={"idempotency_key": "next-project"}))

    def broken_probe(step, *_):
        if step["project_id"] == pid:
            raise ValueError("Saved development configuration is invalid")
        return None

    assert Worker(store, resource_probe=broken_probe).claim()["project_id"] == second
    job = store.get(pid)["jobs"][0]
    assert job["state"] == "FAILED" and "RESOURCE_PREFLIGHT_FAILED" in job["error"]
    assert job["steps"][0]["attempts"] == 0


def test_two_concurrent_claims_do_not_duplicate_attempt(store, spec):
    pid, _ = enqueue(store, spec)
    busy_worker(store).claim()
    workers = [Worker(store, resource_probe=lambda *_: None) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda w: w.claim(), workers))
    assert sum(result is not None for result in results) == 1
    assert store.get(pid)["jobs"][0]["steps"][0]["attempts"] == 1


def test_wait_backup_restores_paused_then_exports_real_valid_demo_media(store, spec, tmp_path):
    set_silent(store)
    pid, _ = enqueue(store, spec)
    busy_worker(store).claim()
    before = store.get(pid)["jobs"][0]
    archive = create_backup(store, tmp_path / "waiting.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    job = restored.get(pid)["jobs"][0]
    assert job["state"] == "PAUSED" and job["resource_wait"] is None
    assert [s["id"] for s in job["steps"]] == [s["id"] for s in before["steps"]]
    assert Worker(restored).claim() is None
    set_silent(restored)
    restored.control(pid, "resume")
    final = produce_until(restored, Worker(restored), pid)
    assert final["status"] == "COMPLETED"
    movie = next(a for a in final["assets"] if a["role"] == "export")
    assert movie["metadata"]["is_mock"] is True
    media.validate_video(restored.asset_path(movie["id"])[0], media.SIZES[spec.orientation], 5, audio=True)
    assert len(final["canon"]) == 1


def test_api_worker_wait_pause_resume_then_mp4(tmp_path, spec):
    busy = [True]
    app = create_app(tmp_path, resource_probe=lambda *_: BUSY if busy[0] else None)
    set_silent(app.state.store)
    with TestClient(app) as client:
        created = client.post("/api/projects", json=spec.model_dump())
        assert created.status_code == 201
        pid = created.json()["id"]
        url = f"/api/projects/{pid}"
        await_condition(lambda: client.get(url).json()["status"] == resources.WAIT_STATE)
        waiting = client.get(url).json()
        assert waiting["jobs"][0]["resource_wait"]["code"] == "MEMORY_BUSY"
        assert waiting["jobs"][0]["steps"][0]["attempts"] == 0
        assert client.post(url + "/pause").json()["status"] == "PAUSED"
        busy[0] = False
        assert client.post(url + "/resume").status_code == 200
        await_condition(lambda: client.get(url).json()["status"] == "COMPLETED")
        final = client.get(url).json()
        movie = next(a for a in final["assets"] if a["role"] == "export")
        response = client.get(f"/api/assets/{movie['id']}/content")
        assert response.status_code == 200 and response.content[4:8] == b"ftyp"
        media.validate_video(
            app.state.store.asset_path(movie["id"])[0], media.SIZES[spec.orientation], 5, audio=True
        )


def test_hard_kill_while_waiting_preserves_deadline_and_budget(store, spec):
    pid, _ = enqueue(store, spec)
    # Explicit fake counter child. No native model, no production bypass switch.
    code = """
import os, time
from pathlib import Path
from studio.storage import Store
from studio.worker import Worker
from studio.resource_wait import ResourceReason
w=Worker(Store(Path(os.environ['STUDIO_DATA'])), resource_probe=lambda *_: ResourceReason(code='MEMORY_BUSY', message='Development kill fixture'))
w.start()
time.sleep(60)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        env=os.environ | {"STUDIO_DATA": str(store.root)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await_condition(lambda: store.get(pid)["status"] == resources.WAIT_STATE)
        before = store.get(pid)["jobs"][0]
        process.kill()
        process.wait(timeout=10)
        reopened = Store(store.root)
        worker = busy_worker(reopened)
        worker.recover()
        worker.claim()
        after = reopened.get(pid)["jobs"][0]
        assert after["resource_wait"]["deadline"] == before["resource_wait"]["deadline"]
        assert after["steps"][0]["id"] == before["steps"][0]["id"]
        assert after["steps"][0]["attempts"] == 0
        worker.resource_probe = lambda *_: None
        reopened.control(pid, "resume")
        assert worker.claim()["attempts"] == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


@pytest.mark.parametrize("profile,minimum", [("small_cpu", 2), ("cpu_1_5b", 5), ("cpu_4b", 7)])
def test_cpu_counter_thresholds_without_real_weights(tmp_path, monkeypatch, profile, minimum):
    import studio.local_story as story

    monkeypatch.setattr(story, "ROOT", tmp_path)
    monkeypatch.setattr(story, "CPU_PROFILES", {profile: ("fixture", "fixture.gguf", 3, "not-a-real-model")})
    folder = tmp_path / "tools/story"
    folder.mkdir(parents=True)
    (folder / "llama-server.exe").write_bytes(b"not executable")
    weights = folder / "fixture.gguf"
    weights.write_bytes(b"123")
    memory = {"available": True, "free_gb": minimum - 0.01}
    monkeypatch.setattr(resources, "memory_status", lambda: memory)
    args = (
        {"stage": "SCRIPT_BATCH"},
        {"story_engine": profile},
        {"backend": "local"},
        lambda: pytest.fail("CPU stage read GPU"),
    )
    assert resources.probe(*args).code == "MEMORY_BUSY"
    memory["free_gb"] = minimum
    assert resources.probe(*args) is None
    memory["free_gb"] = float("nan")
    assert resources.probe(*args).code == "COUNTERS_UNKNOWN"
    weights.write_bytes(b"bad size")
    assert resources.probe(*args) is None  # Missing/bad setup belongs to actual provider validation.


@pytest.mark.parametrize(
    "gpu,expected",
    [
        ({"available": False}, "COUNTERS_UNKNOWN"),
        ({"total_mb": 6144, "used_mb": 2048, "temperature_c": 84}, None),
        ({"total_mb": 6144, "used_mb": 2049, "temperature_c": 70}, "GRAPHICS_BUSY"),
        ({"total_mb": 6144, "used_mb": 0, "temperature_c": 85}, "GPU_HOT"),
        ({"total_mb": 6144, "used_mb": -1, "temperature_c": 70}, "COUNTERS_UNKNOWN"),
        ({"total_mb": 6144, "used_mb": 0, "temperature_c": True}, "COUNTERS_UNKNOWN"),
    ],
)
def test_gpu_counter_thresholds_without_runtime(tmp_path, monkeypatch, gpu, expected):
    python = tmp_path / "not-python.exe"
    python.write_bytes(b"fixture")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "api.py").write_bytes(b"fixture")
    settings = {"wangp": {"installation": str(tmp_path), "python": str(python), "license_reviewed": True}}
    monkeypatch.setattr(resources, "memory_status", lambda: {"available": True, "free_gb": 5})
    result = resources.probe(
        {"stage": "FRAME"}, settings, {"backend": "local"}, lambda: {"available": True} | gpu
    )
    assert (result.code if result else None) == expected
    assert (
        resources.probe(
            {"stage": "FRAME"}, settings, {"backend": "demo"}, lambda: pytest.fail("Demo read GPU")
        )
        is None
    )


def test_cli_opt_out_keeps_smoke_failfast(store, spec):
    enqueue(store, spec)
    worker = Worker(
        store,
        wait_for_resources=False,
        resource_probe=lambda *_: pytest.fail("Passive wait in bounded smoke"),
    )
    assert worker.claim()["attempts"] == 1


def test_counter_errors_wait_but_missing_setup_and_render_do_not(tmp_path, monkeypatch):
    python = tmp_path / "fixture.exe"
    python.write_bytes(b"not executable")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "api.py").write_bytes(b"not importable")
    settings = {"wangp": {"installation": str(tmp_path), "python": str(python), "license_reviewed": True}}
    memory = {"available": True, "free_gb": 4.99}
    monkeypatch.setattr(resources, "memory_status", lambda: memory)

    def fail_gpu():
        pytest.fail("RAM gate must precede GPU sampling")

    assert resources.probe({"stage": "FRAME"}, settings, {"backend": "local"}, fail_gpu).code == "MEMORY_BUSY"
    assert resources.probe({"stage": "AUDIO"}, settings, {"backend": "local"}, fail_gpu) is None
    assert resources.probe({"stage": "FRAME"}, {}, {"backend": "local"}, fail_gpu) is None
    memory["available"] = False
    assert (
        resources.probe({"stage": "FRAME"}, settings, {"backend": "local"}, fail_gpu).code
        == "COUNTERS_UNKNOWN"
    )
    memory.update(available=True, free_gb=5)

    def unreadable():
        raise OSError("Fixture GPU counter error")

    assert (
        resources.probe({"stage": "FRAME"}, settings, {"backend": "local"}, unreadable).code
        == "COUNTERS_UNKNOWN"
    )


def test_waiting_movie_blocks_canon_revisions(store, spec):
    pid, _ = enqueue(store, spec)
    busy_worker(store).claim()
    with TestClient(create_app(store.root, run_worker=False)) as client:
        response = client.post(
            f"/api/projects/{pid}/canon",
            json={
                "revision": 1,
                "event": {
                    "episode": 1,
                    "entity_id": pid,
                    "field": "outcome",
                    "value": "A different outcome.",
                    "reason": "Development fixture testing the active-job guard.",
                },
            },
        )
    assert response.status_code == 409, response.text
    assert "active production" in response.json()["message"]
    assert store.get(pid)["canon"] == []


def test_waiting_production_blocks_other_saved_draft_editing():
    from studio.draft_editing import edit_eligibility

    episode = {"number": 2, "script": {"screenplay": "Saved draft"}, "status": "DRAFTED"}
    project = {"jobs": [{"episode": 1, "state": resources.WAIT_STATE, "steps": []}]}
    eligible, reason = edit_eligibility(project, episode)
    assert not eligible and "current production" in reason
