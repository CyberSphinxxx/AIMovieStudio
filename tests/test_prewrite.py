import json

import pytest

from studio.storage import Store, atomic_json
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


def test_ten_episode_prewrite_recovers_and_reuses_without_future_canon(store, spec, monkeypatch):
    spec.kind, spec.episodes, spec.target_seconds, spec.prewrite_season = "series", 10, 5, True
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    partial = produce_until(store, worker, pid, "DRAFT", 4)
    saved = [e["script"] for e in partial["episodes"][:4]]
    assert not partial["canon"]
    assert not partial["assets"]
    # Simulate power loss between draft publication and its database commit.
    step = worker.claim()
    assert step["stage"] == "DRAFT"
    output = worker.execute(step)
    atomic_json(worker.directory(step) / "receipt.json", output)
    reopened = Store(store.root)
    recovery = Worker(reopened)
    recovery.recover()
    drafts = produce_until(reopened, recovery, pid, "DRAFT", 5)
    assert all(e["status"] == "DRAFTED" for e in drafts["episodes"])
    assert [e["script"] for e in drafts["episodes"][:4]] == saved
    assert not drafts["canon"]

    # Production must consume the saved screenplay rather than call the model again.
    def no_rewrite(*args):
        raise AssertionError("Saved draft was needlessly regenerated")

    monkeypatch.setattr("studio.story.DemoStory.script", no_rewrite)
    finished = produce_until(reopened, recovery, pid)
    assert finished["status"] == "COMPLETED"
    assert len(finished["canon"]) == 1
    reopened.enqueue(pid, 2)
    episode2 = produce_until(reopened, recovery, pid)
    assert episode2["episodes"][1]["script"] == saved[1]
    assert len(episode2["canon"]) == 2


def test_prewrite_does_not_bypass_current_canon(store, spec):
    spec.kind, spec.episodes, spec.target_seconds, spec.prewrite_season = "series", 2, 5, True
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    result = produce_until(store, worker, pid, "DRAFT", 2)
    character = result["episodes"][0]["script"]["shots"][0]["character_ids"][0]
    with store.connect() as db:
        # Validate a later episode against newly established canon.
        db.execute("UPDATE jobs SET episode=2 WHERE project_id=?", (pid,))
        db.execute(
            "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)",
            (
                "test-death",
                pid,
                character,
                1,
                "alive",
                "false",
                "Confirmed prior outcome",
                1,
            ),
        )
    step = worker.claim()
    with pytest.raises(RuntimeError, match="CANON_CONFLICT"):
        worker.execute(step)
    assert json.loads(step["config"])["speech"] == "windows"
