import json
import time

from fastapi.testclient import TestClient

from studio.api import create_app
from studio.worker import Worker


def wait_for(check, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("Worker control did not settle")


def test_active_pause_resume_and_cancel(store, spec):
    spec.kind, spec.target_seconds = "drama", 50
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    worker.start()
    try:
        wait_for(
            lambda: any(
                s["state"] == "RUNNING" and s["stage"] == "CLIP" for s in store.get(pid)["jobs"][0]["steps"]
            )
        )
        store.control(pid, "pause")
        wait_for(lambda: not any(s["state"] == "RUNNING" for s in store.get(pid)["jobs"][0]["steps"]))
        paused = store.get(pid)
        hashes = {a["id"]: a["sha256"] for a in paused["assets"]}
        time.sleep(0.4)
        assert len(store.get(pid)["assets"]) == len(paused["assets"])
        store.control(pid, "resume")
        wait_for(lambda: store.get(pid)["status"] == "COMPLETED")
        completed = store.get(pid)
        assert all(
            next(a for a in completed["assets"] if a["id"] == aid)["sha256"] == sha
            for aid, sha in hashes.items()
        )
        spec.idempotency_key = "cancel-second-production"
        second, _ = store.create(spec)
        store.enqueue(second)
        wait_for(lambda: any(s["state"] == "RUNNING" for s in store.get(second)["jobs"][0]["steps"]))
        store.control(second, "cancel")
        wait_for(lambda: not any(s["state"] == "RUNNING" for s in store.get(second)["jobs"][0]["steps"]))
        assert store.get(second)["jobs"][0]["state"] == "CANCELLED"
        assert not any(a["role"] == "export" for a in store.get(second)["assets"])
    finally:
        worker.close()


def test_event_replay_and_explicit_configuration_retry(tmp_path, spec):
    app = create_app(tmp_path, run_worker=False)
    store = app.state.store
    with TestClient(app) as client:
        p = client.post("/api/projects", json=spec.model_dump()).json()
        pid, jid = p["id"], p["jobs"][0]["id"]
        response = client.get(f"/api/projects/{pid}/events?follow=false")
        assert response.status_code == 200 and "text/event-stream" in response.headers["content-type"]
        ids = [int(line.split(":")[1]) for line in response.text.splitlines() if line.startswith("id:")]
        assert ids == sorted(ids) and len(ids) == 2
        replay = client.get(
            f"/api/projects/{pid}/events?follow=false", headers={"Last-Event-ID": str(ids[-1])}
        )
        assert "id:" not in replay.text
        assert (
            client.get(
                f"/api/projects/{pid}/events?follow=false", headers={"Last-Event-ID": "bad"}
            ).status_code
            == 422
        )
        with store.connect() as db:
            db.execute("UPDATE jobs SET state='FAILED' WHERE id=?", (jid,))
            db.execute("UPDATE steps SET state='FAILED' WHERE job_id=?", (jid,))
        client.patch("/api/settings", json={"speech": "none", "reserve_mb": 2048, "story_model": ""})
        assert client.post(f"/api/projects/{pid}/resume", json={}).status_code == 200
        with store.connect() as db:
            config = json.loads(db.execute("SELECT config FROM jobs WHERE id=?", (jid,)).fetchone()[0])
        assert config["reserve_mb"] == 2048 and config["speech"] == "none"


def test_queue_fifty_projects_with_single_claims(store, spec):
    worker = Worker(store)
    for i in range(50):
        spec.idempotency_key = f"unique-queued-project-{i}"
        pid, _ = store.create(spec)
        store.enqueue(pid)
    claimed = set()
    for _ in range(50):
        step = worker.claim()
        assert step and step["id"] not in claimed
        claimed.add(step["id"])
        with store.connect() as db:
            # Simulate paused owners rather than inventing successful inference outputs.
            db.execute("UPDATE jobs SET state='PAUSED' WHERE id=?", (step["job_id"],))
            db.execute("UPDATE steps SET state='READY' WHERE id=?", (step["id"],))
    assert worker.claim() is None
