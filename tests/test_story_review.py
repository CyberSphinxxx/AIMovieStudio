import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.storage import digest
from studio.story import DemoStory
from studio.worker import Worker
from studio.draft_editing import stopped_before_media
from tests.test_pipeline import produce_until, set_silent


def test_incomplete_media_metadata_cannot_advertise_a_safe_edit():
    job = {"state": "PAUSED", "episode": 1, "steps": [{"stage": "SCRIPT", "state": "SUCCEEDED"}]}
    for metadata in [{}, [], {"episode": 1}]:
        assert not stopped_before_media({"assets": [{"metadata": metadata}]}, job)


def test_optional_review_stops_before_media_edits_and_resumes_from_backup(store, spec, tmp_path, monkeypatch):
    spec.review_story = True
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    stopped = produce_until(store, worker, pid)
    assert stopped["jobs"][0]["state"] == "PAUSED"
    assert stopped["episodes"][0]["can_edit_draft"]
    assert not stopped["assets"] and not stopped["canon"]
    sid = stopped["episodes"][0]["script"]["shots"][0]["id"]
    old_steps = [s["id"] for s in stopped["jobs"][0]["steps"] if s["state"] == "READY"]
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.patch(
            f"/api/projects/{pid}/episodes/1/draft",
            json={"revision": 1, "edits": [{"shot_id": sid, "narration": "We reached home."}]},
        )
    assert result.status_code == 200, result.text
    edited = result.json()
    assert edited["jobs"][0]["state"] == "PAUSED"
    assert all(s["state"] == "SUPERSEDED" for s in edited["jobs"][0]["steps"] if s["id"] in old_steps)
    assert edited["jobs"][0]["steps"][-1]["stage"] == "SCRIPT"
    archive = create_backup(store, tmp_path / "review.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    set_silent(restored)
    restored.control(pid, "resume")
    monkeypatch.setattr(DemoStory, "script", lambda *args: pytest.fail("Rewrote user-reviewed script"))
    finished = produce_until(restored, Worker(restored), pid)
    assert finished["status"] == "COMPLETED"
    assert finished["episodes"][0]["script"]["shots"][0]["narration"] == "We reached home."
    assert len(finished["canon"]) == 1


def test_default_remains_automatic_and_cancel_or_committed_media_cannot_be_edited(store, spec):
    assert spec.review_story is False
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    partial = produce_until(store, worker, pid, "AUDIO", 1)
    store.control(pid, "pause")
    assert not store.get(pid)["episodes"][0]["can_edit_draft"]
    sid = partial["episodes"][0]["script"]["shots"][0]["id"]
    with TestClient(create_app(store.root, run_worker=False)) as client:
        body = {"revision": 1, "edits": [{"shot_id": sid, "narration": "A short line."}]}
        assert client.patch(f"/api/projects/{pid}/episodes/1/draft", json=body).status_code == 409
        store.control(pid, "cancel")
        assert client.patch(f"/api/projects/{pid}/episodes/1/draft", json=body).status_code == 409


def test_running_atomic_step_cannot_be_revised(store, spec):
    spec.review_story = True
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    result = produce_until(store, worker, pid)
    store.control(pid, "resume")
    assert worker.claim()["stage"] == "AUDIO"
    store.control(pid, "pause")
    assert not store.get(pid)["episodes"][0]["can_edit_draft"]
    sid = result["episodes"][0]["script"]["shots"][0]["id"]
    with TestClient(create_app(store.root, run_worker=False)) as client:
        response = client.patch(
            f"/api/projects/{pid}/episodes/1/draft",
            json={"revision": 1, "edits": [{"shot_id": sid, "narration": "A short line."}]},
        )
    assert response.status_code == 409


def test_saved_local_draft_reuse_does_not_require_a_story_runtime(store, spec, monkeypatch):
    spec.kind, spec.episodes, spec.prewrite_season = "series", 2, True
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    project = produce_until(store, worker, pid, "DRAFT", 2)
    with store.connect() as db:
        db.execute(
            "UPDATE projects SET spec=? WHERE id=?", (json.dumps(project["spec"] | {"backend": "local"}), pid)
        )
    monkeypatch.setattr(
        "studio.worker.OllamaStory",
        lambda *args, **kwargs: pytest.fail("Constructed unneeded story provider"),
    )
    step = worker.claim()
    assert step["stage"] == "SCRIPT"
    assert worker.execute(step)["script"] == project["episodes"][0]["script"]


@pytest.mark.skipif(os.name != "nt", reason="Actual installed Windows speech")
def test_real_overlong_voice_is_preserved_and_repaired_with_fresh_steps(store, spec, monkeypatch):
    pid, _ = store.create(spec)
    original = DemoStory.script

    def long_line(self, project, number):
        script = original(self, project, number)
        script.shots[0].narration = (
            "This sentence explains every detail of the difficult journey through the lighthouse. " * 5
        )
        return script

    monkeypatch.setattr(DemoStory, "script", long_line)
    store.enqueue(pid)
    worker = Worker(store)
    worker.start()
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            project = store.get(pid)
            if project["jobs"][0]["state"] == "FAILED":
                break
            time.sleep(0.1)
        assert "DIALOGUE_TOO_LONG" in project["jobs"][0]["error"]
    finally:
        worker.close()
    failed_step = next(s for s in project["jobs"][0]["steps"] if s["stage"] == "AUDIO")
    raw = (
        worker.directory({**failed_step, "project_id": pid, "job_id": project["jobs"][0]["id"]})
        / "voice-1.wav"
    )
    assert raw.is_file()
    original_hash = digest(raw)
    assert project["episodes"][0]["can_edit_draft"] and not project["assets"]
    sid = project["episodes"][0]["script"]["shots"][0]["id"]
    with TestClient(create_app(store.root, run_worker=False)) as client:
        response = client.patch(
            f"/api/projects/{pid}/episodes/1/draft",
            json={"revision": 1, "edits": [{"shot_id": sid, "narration": "We reached home."}]},
        )
    assert response.status_code == 200, response.text
    monkeypatch.setattr(DemoStory, "script", lambda *args: pytest.fail("Rewrote repaired script"))
    store.control(pid, "resume")
    result = produce_until(store, Worker(store), pid)
    assert result["status"] == "COMPLETED"
    assert digest(raw) == original_hash
    assert any(a["role"] == "voice-1" for a in result["assets"])
    assert (
        next(s for s in result["jobs"][0]["steps"] if s["id"] == failed_step["id"])["state"] == "SUPERSEDED"
    )
