"""Explicit development fixtures: OS ownership/process recovery, never model fit."""

import json
import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from studio import inference_lock as ownership
from studio.backup import create_backup, restore_backup
from studio.inference_lock import InferenceBusy, native_inference
from studio.processes import owned_process
from studio.providers import WanGPConfig, WanGPProvider
from studio.resource_wait import ResourceReason, WAIT_SECONDS, probe
from studio.worker import Worker
from tests.test_crash import await_condition
from tests.test_native_memory_sampling import process_alive
from tests.test_pipeline import produce_until, set_silent

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def shared_lock(tmp_path, monkeypatch):
    path = tmp_path / "common user profile/runtime/native.lock"
    monkeypatch.setattr(ownership, "lock_path", lambda: path)
    return path


@contextmanager
def owner_process(
    tmp_path, path, *, extra_child=False, cwd=None, app_root=ROOT, env=None, default_path=False
):
    ready, stop, log_path = tmp_path / "owner-ready.json", tmp_path / "owner-stop", tmp_path / "owner.log"
    # Use the base executable directly so a Windows venv launcher is not mistaken
    # for the actual owner. -I and explicit app path allow an unrelated cwd.
    executable = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python3")
    code = """
import sys,json,time,subprocess,os
from pathlib import Path
from contextlib import ExitStack
sys.path.insert(0,sys.argv[1])
from studio.inference_lock import native_inference
from studio.processes import owned_process
with native_inference(Path(sys.argv[2]) if sys.argv[2] else None), ExitStack() as cleanup:
    child=None
    if sys.argv[5]=='True':
        child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)'])
        cleanup.enter_context(owned_process(child))
    Path(sys.argv[3]).write_text(json.dumps({'pid':os.getpid(),'child':child.pid if child else None}))
    until=time.monotonic()+20
    while not Path(sys.argv[4]).exists() and time.monotonic()<until:
        time.sleep(.02)
    if child:
        child.terminate()
        child.wait(timeout=5)
"""
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                str(executable),
                "-I",
                "-c",
                code,
                str(app_root),
                "" if default_path else str(path),
                str(ready),
                str(stop),
                str(extra_child),
            ],
            cwd=cwd or tmp_path,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
        try:
            with owned_process(process):
                await_condition(lambda: ready.exists() or process.poll() is not None, timeout=8)
                assert ready.exists(), log_path.read_text(errors="replace")
                yield process, json.loads(ready.read_text())
                stop.touch()
                process.wait(timeout=8)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def test_nested_and_thread_contention_release_without_replacing_file(shared_lock):
    with native_inference():
        identity = shared_lock.stat().st_ino
        assert ownership.inference_busy()
        errors = []

        def second_thread():
            try:
                with native_inference():
                    errors.append("entered")
            except InferenceBusy:
                errors.append("busy")

        thread = threading.Thread(target=second_thread)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive() and errors == ["busy"]
    assert not ownership.inference_busy()
    assert shared_lock.exists() and shared_lock.stat().st_ino == identity
    for _ in range(10):
        with native_inference():
            pass
    assert shared_lock.stat().st_size == 0  # No repeated lock-file writes/growth.


def test_different_process_and_folder_share_ownership_then_release(shared_lock, tmp_path):
    another_folder = tmp_path / "other Studio copy"
    another_folder.mkdir()
    with owner_process(tmp_path, shared_lock, cwd=another_folder):
        assert ownership.inference_busy()
        with pytest.raises(InferenceBusy):
            with native_inference():
                pytest.fail("Concurrent native workload entered")
    assert not ownership.inference_busy()


def test_actual_killed_owner_and_owned_child_release_lock(shared_lock, tmp_path):
    with owner_process(tmp_path, shared_lock, extra_child=True) as (process, record):
        assert process.pid == record["pid"] and process_alive(record["child"])
        assert ownership.inference_busy()
        process.kill()
        process.wait(timeout=5)
    await_condition(lambda: not process_alive(record["child"]), timeout=5)
    assert not ownership.inference_busy()
    with native_inference():
        pass


def test_exception_cleanup_and_broken_storage_fail_closed(shared_lock, monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="fixture failure"):
        with native_inference():
            raise ValueError("fixture failure")
    assert not ownership.inference_busy()
    directory = tmp_path / "directory-not-file"
    directory.mkdir()
    monkeypatch.setattr(ownership, "lock_path", lambda: directory)
    with pytest.raises(RuntimeError, match="INFERENCE_LOCK_UNAVAILABLE"):
        ownership.inference_busy()


def test_cpu_ollama_and_gpu_do_not_enter_when_owned(shared_lock, tmp_path, monkeypatch):
    from studio.local_story import cpu_server
    from studio.story import OllamaStory
    from studio.domain import SeasonPlan

    monkeypatch.setattr("studio.local_story._cpu_server", lambda *a, **kw: pytest.fail("Started CPU model"))
    monkeypatch.setattr("studio.story.httpx.Client", lambda *a, **kw: pytest.fail("Called Ollama"))
    monkeypatch.setattr("studio.providers.require_resources", lambda: pytest.fail("Entered GPU provider"))
    provider = WanGPProvider(WanGPConfig(license_reviewed=True), tmp_path)
    with native_inference():
        with pytest.raises(InferenceBusy):
            with cpu_server():
                pass
        with pytest.raises(InferenceBusy):
            OllamaStory("development-fixture").generate(SeasonPlan, "fixture")
        with pytest.raises(InferenceBusy):
            provider.request("image", "fixture", tmp_path, lambda: None)
    assert not (tmp_path / "provider-request.json").exists()


def test_probe_waits_for_common_owner_without_hardware_and_skips_demo(shared_lock, monkeypatch):
    monkeypatch.setattr(
        "studio.resource_wait.memory_status", lambda: pytest.fail("Read RAM while owner busy")
    )
    settings = {"story_model": "development-fixture", "story_engine": "ollama"}
    with native_inference():
        result = probe({"stage": "PLAN"}, settings, {"backend": "local"}, lambda: pytest.fail("Read GPU"))
        assert result.code == "INFERENCE_BUSY"
        assert probe({"stage": "PLAN"}, settings, {"backend": "demo"}, None) is None
        assert probe({"stage": "AUDIO"}, settings, {"backend": "local"}, None) is None


def enqueue(store, spec):
    pid, _ = store.create(spec)
    return pid, store.enqueue(pid)


def test_ownership_wait_is_durable_and_does_not_spend_attempts(store, spec, shared_lock, tmp_path):
    spec.backend = "local"
    with store.connect() as db:
        db.execute("INSERT INTO settings VALUES('story_model','\"development-fixture\"')")
    pid, _ = enqueue(store, spec)
    with native_inference():
        assert Worker(store).claim() is None
        job = store.get(pid)["jobs"][0]
        assert job["state"] == "WAITING_RESOURCES" and job["steps"][0]["attempts"] == 0
        assert job["resource_wait"]["code"] == "INFERENCE_BUSY"
        reopened = Worker(store)
        reopened.recover()
        assert reopened.claim() is None
        assert store.get(pid)["jobs"][0]["resource_wait"] == job["resource_wait"]
        archive = create_backup(store, tmp_path / "waiting.zip")
        restored = restore_backup(archive, tmp_path / "restored")
        assert restored.get(pid)["jobs"][0]["state"] == "PAUSED"
        assert Worker(restored).claim() is None
    assert Worker(store).claim()["attempts"] == 1


@pytest.mark.parametrize("control", [None, "pause", "cancel"])
def test_claim_race_refunds_once_and_preserves_user_control(store, spec, shared_lock, control):
    pid, _ = enqueue(store, spec)
    worker = Worker(store, resource_probe=lambda *_: None)
    step = worker.claim()
    if control:
        store.control(pid, control)
    worker.defer_inference(step)
    worker.defer_inference(step)  # Repeated handler cannot refund twice.
    job = store.get(pid)["jobs"][0]
    assert job["steps"][0]["attempts"] == 0
    assert job["state"] == {None: "WAITING_RESOURCES", "pause": "PAUSED", "cancel": "CANCELLED"}[control]
    assert job["steps"][0]["state"] == ("CANCELLED" if control == "cancel" else "READY")
    if control:
        assert worker.claim() is None


def test_repeated_race_retains_deadline_then_expires_without_attempt(store, spec, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("studio.worker.time.time", lambda: now[0])
    pid, _ = enqueue(store, spec)
    reason = ResourceReason(code="INFERENCE_BUSY", message="Development fixture ownership wait")
    worker = Worker(store, resource_probe=lambda *_: reason)
    assert worker.claim() is None
    original = store.get(pid)["jobs"][0]["resource_wait"]
    now[0] += 16
    worker.resource_probe = lambda *_: None
    step = worker.claim()
    worker.defer_inference(step)
    saved = store.get(pid)["jobs"][0]["resource_wait"]
    assert saved["since"] == original["since"] and saved["deadline"] == original["deadline"]
    now[0] += 16
    step = worker.claim()
    now[0] = original["since"] + WAIT_SECONDS
    worker.defer_inference(step)
    job = store.get(pid)["jobs"][0]
    assert job["state"] == "FAILED" and "RESOURCE_WAIT_EXPIRED" in job["error"]
    assert job["steps"][0]["attempts"] == 0


def test_busy_loop_defers_but_other_inference_failure_consumes_attempt(store, spec, monkeypatch):
    pid, _ = enqueue(store, spec)
    worker = Worker(store, resource_probe=lambda *_: None)

    def busy(step):
        worker.stop.set()
        raise InferenceBusy()

    monkeypatch.setattr(worker, "execute", busy)
    worker.loop()
    job = store.get(pid)["jobs"][0]
    assert job["state"] == "WAITING_RESOURCES" and job["steps"][0]["attempts"] == 0
    store.control(pid, "resume")
    other = Worker(store, resource_probe=lambda *_: None)

    def failed(step):
        other.stop.set()
        raise RuntimeError("OUT_OF_MEMORY: development fixture after inference began")

    monkeypatch.setattr(other, "execute", failed)
    other.loop()
    job = store.get(pid)["jobs"][0]
    assert job["state"] == "FAILED" and job["steps"][0]["attempts"] == 1


def test_demo_can_export_while_native_ownership_is_busy(store, spec, shared_lock):
    set_silent(store)
    pid, _ = enqueue(store, spec)
    with native_inference():
        result = produce_until(store, Worker(store), pid)
    assert result["status"] == "COMPLETED"
    assert next(a for a in result["assets"] if a["role"] == "export")["metadata"]["is_mock"] is True


def test_cancelled_http_callback_keeps_ownership_until_actual_request_exits(shared_lock):
    from studio.story import checked_post
    from studio.media import Interrupted

    started, finish, ended = threading.Event(), threading.Event(), threading.Event()

    class SlowClient:
        def post(self, *a, **kw):
            started.set()
            assert finish.wait(timeout=5)
            ended.set()
            return "development response"

    def cancel():
        assert started.is_set()
        raise Interrupted("Development fixture cancelled")

    try:
        with pytest.raises(Interrupted):
            with native_inference():
                checked_post(SlowClient(), "/fixture", {}, cancel)
        assert not ended.is_set()
        assert ownership.inference_busy(), "Released ownership while request thread was still working"
    finally:
        finish.set()
        await_condition(lambda: not ownership.inference_busy(), timeout=5)
    assert ended.is_set()


def test_cpu_shutdown_still_holds_ownership_until_child_context_exits(shared_lock, monkeypatch):
    from studio.local_story import cpu_server

    @contextmanager
    def fake_server(*a, **kw):
        assert ownership.inference_busy()
        try:
            yield "development-server", None
        finally:
            assert ownership.inference_busy(), "Ownership released before model cleanup"

    monkeypatch.setattr("studio.local_story._cpu_server", fake_server)
    with pytest.raises(ValueError):
        with cpu_server():
            raise ValueError("Development fixture failure")
    assert not ownership.inference_busy()


def test_two_store_roots_wait_while_third_process_owns_models(shared_lock, tmp_path, spec):
    from studio.storage import Store

    stores = [Store(tmp_path / f"copy-{i}") for i in range(2)]
    pids = []
    for store in stores:
        with store.connect() as db:
            db.execute("INSERT INTO settings VALUES('story_model','\"development-fixture\"')")
        spec.backend = "local"
        pids.append(enqueue(store, spec)[0])
    with owner_process(tmp_path, shared_lock):
        for store, pid in zip(stores, pids, strict=True):
            assert Worker(store).claim() is None
            job = store.get(pid)["jobs"][0]
            assert job["state"] == "WAITING_RESOURCES" and job["steps"][0]["attempts"] == 0
    for store in stores:
        assert Worker(store).claim()["attempts"] == 1


def test_race_wait_can_resume_to_valid_demo_mp4(store, spec, shared_lock):
    set_silent(store)
    pid, _ = enqueue(store, spec)
    worker = Worker(store, resource_probe=lambda *_: None)
    step = worker.claim()
    with native_inference():
        worker.defer_inference(step)
    reopened = Worker(store)
    reopened.recover()
    # Existing throttle applies only within the first worker; reopen uses durable state.
    result = produce_until(store, reopened, pid)
    assert result["status"] == "COMPLETED"
    assert result["jobs"][0]["steps"][0]["attempts"] == 1
    assert len(result["canon"]) == 1


def test_two_copied_modules_choose_the_same_default_user_lock(tmp_path):
    copies = []
    for number in range(2):
        copy = tmp_path / f"private-copy-{number}"
        package = copy / "studio"
        package.mkdir(parents=True)
        (package / "__init__.py").write_bytes(b"")
        shutil.copyfile(ROOT / "studio/inference_lock.py", package / "inference_lock.py")
        shutil.copyfile(ROOT / "studio/processes.py", package / "processes.py")
        copies.append(copy)
    profile = tmp_path / "simulated-profile"
    environment = os.environ | {
        "LOCALAPPDATA": str(profile),
        "HOME": str(profile),
        "USERPROFILE": str(profile),
    }
    with owner_process(tmp_path, None, app_root=copies[0], env=environment, default_path=True):
        executable = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python3")
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "from studio.inference_lock import inference_busy;"
            "assert inference_busy();print('BUSY_FROM_SECOND_COPY')"
        )
        second = subprocess.run(
            [str(executable), "-I", "-c", code, str(copies[1])],
            cwd=copies[1],
            env=environment,
            capture_output=True,
            timeout=8,
        )
        assert second.returncode == 0, second.stderr.decode(errors="replace")
        assert b"BUSY_FROM_SECOND_COPY" in second.stdout


def test_api_automatically_continues_to_mp4_after_shared_ownership_releases(
    tmp_path, spec, shared_lock, monkeypatch
):
    from fastapi.testclient import TestClient
    from studio.api import create_app
    from studio.resource_wait import busy_reason

    # Explicit demo fixture uses real shared ownership for scheduling. Never
    # substitutes mock media for a requested local provider in production.
    monkeypatch.setattr("studio.worker.RECHECK_SECONDS", 0.05)
    app = create_app(
        tmp_path / "api-workspace",
        resource_probe=lambda *_: busy_reason() if ownership.inference_busy() else None,
    )
    set_silent(app.state.store)
    with TestClient(app) as client:
        with native_inference():
            response = client.post("/api/projects", json=spec.model_dump())
            assert response.status_code == 201
            pid = response.json()["id"]
            path = f"/api/projects/{pid}"
            await_condition(lambda: client.get(path).json()["status"] == "WAITING_RESOURCES")
            job = client.get(path).json()["jobs"][0]
            assert job["resource_wait"]["code"] == "INFERENCE_BUSY" and job["steps"][0]["attempts"] == 0
        await_condition(lambda: client.get(path).json()["status"] == "COMPLETED")
        project = client.get(path).json()
        movie = next(a for a in project["assets"] if a["role"] == "export")
        assert movie["metadata"]["is_mock"] is True
        assert client.get(f"/api/assets/{movie['id']}/content").content[4:8] == b"ftyp"


def test_real_worker_kill_releases_model_ownership_and_recovers_same_step(store, spec, shared_lock, tmp_path):
    set_silent(store)
    pid, _ = enqueue(store, spec)
    ready = tmp_path / "worker-ready.json"
    executable = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python3")
    code = """
import sys,time,json,subprocess,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from studio.storage import Store
from studio.worker import Worker
from studio.inference_lock import native_inference
from studio.processes import owned_process
class DevelopmentWorker(Worker):
    def execute(self,step):
        with native_inference(Path(sys.argv[3])):
            child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)'])
            with owned_process(child):
                Path(sys.argv[4]).write_text(json.dumps({'step_id':step['id'],'child_pid':child.pid}))
                time.sleep(30)
worker=DevelopmentWorker(Store(Path(sys.argv[2])))
worker.start()
time.sleep(30)
"""
    with (tmp_path / "worker-kill.log").open("wb") as log:
        process = subprocess.Popen(
            [str(executable), "-I", "-c", code, str(ROOT), str(store.root), str(shared_lock), str(ready)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
        try:
            with owned_process(process):
                await_condition(lambda: ready.exists() or process.poll() is not None, timeout=8)
                assert ready.exists(), (tmp_path / "worker-kill.log").read_text(errors="replace")
                record = json.loads(ready.read_text())
                assert ownership.inference_busy() and process_alive(record["child_pid"])
                process.kill()
                process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    await_condition(lambda: not process_alive(record["child_pid"]), timeout=5)
    assert not ownership.inference_busy()
    restarted = Worker(store)
    restarted.recover()
    recovered = store.get(pid)["jobs"][0]["steps"][0]
    assert recovered["id"] == record["step_id"] and recovered["state"] == "READY"
    assert recovered["attempts"] == 1  # Crash is not an unstarted lock-contention refund.
    result = produce_until(store, restarted, pid)
    assert result["status"] == "COMPLETED"
    assert result["jobs"][0]["steps"][0]["attempts"] == 2
    assert len(result["canon"]) == 1
