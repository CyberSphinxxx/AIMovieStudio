"""Admission contracts use saved sample rows; they never call a model."""

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.domain import stable
from studio.story import DemoStory


def completed_pair(store, spec):
    spec.kind, spec.episodes = "series", 3
    pid, _ = store.create(spec)
    plan = DemoStory().plan(store.get(pid))
    with store.connect() as db:
        db.execute("UPDATE projects SET plan=?,status='COMPLETED' WHERE id=?", (plan.model_dump_json(), pid))
        for outline in plan.episodes:
            db.execute(
                "INSERT INTO episodes VALUES(?,?,?,?,?,?)",
                (
                    stable(pid, f"episode:{outline.number}"),
                    pid,
                    outline.number,
                    outline.model_dump_json(),
                    None,
                    "COMPLETED" if outline.number < 3 else "PLANNED",
                ),
            )
            if outline.number < 3:
                db.execute(
                    "INSERT INTO jobs(id,project_id,episode,state,created) VALUES(?,?,?,?,?)",
                    (str(uuid4()), pid, outline.number, "SUCCEEDED", time.time()),
                )
    return pid


def test_canon_revision_blocks_continuation_without_changing_old_jobs(store, spec):
    pid = completed_pair(store, spec)
    before = store.get(pid)
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.post(
            f"/api/projects/{pid}/canon",
            json={
                "revision": before["revision"],
                "event": {
                    "episode": 1,
                    "entity_id": pid,
                    "field": "outcome",
                    "value": "The signal was answered.",
                    "reason": "Correct the declared first episode outcome.",
                },
            },
        )
        assert result.status_code == 200, result.text
        invalidated = store.get(pid)
        assert invalidated["episodes"][1]["status"] == "REVIEW_REQUIRED"
        assert invalidated["jobs"] == before["jobs"]
        result = client.post(f"/api/projects/{pid}/produce", json={"episode": 3})
        assert result.status_code == 409, result.text
        assert "review" in result.text.lower()
    assert store.get(pid) == invalidated


@pytest.mark.parametrize("status", ["REVIEW_REQUIRED", "SCRIPTED", "DRAFTED", "PLANNED", None])
def test_successful_job_alone_never_authorizes_continuation(store, spec, status):
    pid = completed_pair(store, spec)
    with store.connect() as db:
        if status is None:
            db.execute("DELETE FROM episodes WHERE project_id=? AND number=2", (pid,))
        else:
            db.execute("UPDATE episodes SET status=? WHERE project_id=? AND number=2", (status, pid))
    before = store.get(pid)
    with pytest.raises(ValueError, match="[Rr]eview"):
        store.enqueue(pid, 3)
    assert store.get(pid) == before


def test_completed_prior_episode_allows_one_idempotent_job(store, spec):
    pid = completed_pair(store, spec)
    job = store.enqueue(pid, 3)
    assert store.enqueue(pid, 3) == job
    after = store.get(pid)
    assert len(after["jobs"]) == 3
    assert len(after["jobs"][-1]["steps"]) == 1


def test_missing_successful_job_is_still_refused(store, spec):
    pid = completed_pair(store, spec)
    with store.connect() as db:
        db.execute("DELETE FROM jobs WHERE project_id=? AND episode=2", (pid,))
    with pytest.raises(ValueError, match="Finish the previous"):
        store.enqueue(pid, 3)
