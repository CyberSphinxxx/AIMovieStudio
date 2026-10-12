import json

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.domain import CanonChange, EpisodeScript
from studio.storage import Store
from studio.story import DemoStory
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


@pytest.fixture
def drafts(store, spec):
    spec.kind, spec.episodes, spec.prewrite_season = "series", 3, True
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    produce_until(store, worker, pid)
    app = create_app(store.root, run_worker=False)
    with TestClient(app) as client:
        yield store, worker, pid, client


def edit_body(project, **fields):
    return {
        "revision": project["revision"],
        "edits": [{"shot_id": project["episodes"][1]["script"]["shots"][0]["id"], **fields}],
    }


def test_saved_draft_edit_keeps_history_identity_and_is_consumed_in_production(drafts, monkeypatch):
    store, worker, pid, client = drafts
    before = store.get(pid)
    old = before["episodes"][1]["script"]
    result = client.patch(
        f"/api/projects/{pid}/episodes/2/draft",
        json=edit_body(
            before,
            narration="We found the missing vessel.",
            action="Mara places the recovered compass on a map beside the warm station lamp.",
        ),
    )
    assert result.status_code == 200, result.text
    after = result.json()
    assert after["revision"] == 2
    assert after["episodes"][2]["status"] == "REVIEW_REQUIRED"
    script = after["episodes"][1]["script"]
    assert script["shots"][0]["duration"] == old["shots"][0]["duration"]
    assert script["shots"][0]["id"] == old["shots"][0]["id"]
    assert "We found the missing vessel." in script["screenplay"]
    with store.connect() as db:
        history = json.loads(db.execute("SELECT data FROM events WHERE kind='draft_revision'").fetchone()[0])
    assert history["original_script"] == old
    assert history["revision"] == 2
    previous = client.get(f"/api/projects/{pid}/episodes/2/draft-history").json()["revisions"]
    assert previous[0]["screenplay"] == old["screenplay"]
    assert previous[0]["before_revision"] == 2
    assert len(after["canon"]) == 1
    reopened = Store(store.root)
    assert reopened.get(pid)["episodes"][1]["script"] == script
    monkeypatch.setattr(DemoStory, "script", lambda *args: pytest.fail("Rewrote edited saved draft"))
    reopened.enqueue(pid, 2)
    result = produce_until(reopened, Worker(reopened), pid)
    assert result["episodes"][1]["script"] == script
    assert result["episodes"][1]["status"] == "COMPLETED"
    assert len(result["canon"]) == 2


def test_edit_refuses_stale_active_or_produced_episode(drafts):
    store, worker, pid, client = drafts
    before = store.get(pid)
    body = edit_body(before, narration="A small clue remained.")
    body["revision"] = 999
    assert client.patch(f"/api/projects/{pid}/episodes/2/draft", json=body).status_code == 409
    body["revision"] = before["revision"]
    with store.connect() as db:
        db.execute("UPDATE jobs SET state='PAUSED' WHERE project_id=?", (pid,))
    assert client.patch(f"/api/projects/{pid}/episodes/2/draft", json=body).status_code == 409
    with store.connect() as db:
        db.execute("UPDATE jobs SET state='SUCCEEDED' WHERE project_id=?", (pid,))
    assert client.patch(f"/api/projects/{pid}/episodes/1/draft", json=body).status_code == 409
    assert client.patch(f"/api/projects/{pid}/episodes/24/draft", json=body).status_code == 409
    assert store.get(pid)["revision"] == before["revision"]


@pytest.mark.parametrize("fault", ["unknown_shot", "unknown_speaker", "duplicate", "duration", "empty"])
def test_invalid_sparse_edits_never_publish(drafts, fault):
    store, _, pid, client = drafts
    before = store.get(pid)
    body = edit_body(before, narration="A safe short line.")
    if fault == "unknown_shot":
        body["edits"][0]["shot_id"] = "missing"
    elif fault == "unknown_speaker":
        body["edits"][0]["speaker_id"] = "missing"
    elif fault == "duplicate":
        body["edits"].append(body["edits"][0])
    elif fault == "duration":
        body["edits"][0]["duration"] = 99
    else:
        del body["edits"][0]["narration"]
    result = client.patch(f"/api/projects/{pid}/episodes/2/draft", json=body)
    assert result.status_code in {409, 422}, result.text
    after = store.get(pid)
    assert after["revision"] == before["revision"]
    assert after["episodes"] == before["episodes"]


def test_edit_validates_future_draft_with_prior_planned_changes_and_no_canon_leak(drafts):
    store, _, pid, client = drafts
    project = store.get(pid)
    hero = project["plan"]["characters"][0]["id"]
    earlier = EpisodeScript.model_validate(project["episodes"][1]["script"])
    earlier.proposed_changes = [
        CanonChange(
            after_shot=1,
            entity_id=hero,
            field="alive",
            before_value="true",
            value="false",
            reason="Mara dies in the chamber after the final shot.",
        )
    ]
    with store.connect() as db:
        db.execute(
            "UPDATE episodes SET script=? WHERE project_id=? AND number=2", (earlier.model_dump_json(), pid)
        )
    target = project["episodes"][2]["script"]["shots"][0]["id"]
    result = client.patch(
        f"/api/projects/{pid}/episodes/3/draft",
        json={
            "revision": project["revision"],
            "edits": [{"shot_id": target, "narration": "The journey continues."}],
        },
    )
    assert result.status_code == 409 and "CANON_CONFLICT" in result.text
    assert len(store.get(pid)["canon"]) == 1
