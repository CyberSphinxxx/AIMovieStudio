"""Story-only alternative projects preserve produced originals; no AI inference."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.storage import digest
from studio.domain import ProjectInput
from studio.story_branches import StoryBranchRequest, copy_story, create_story_branch
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent
from tests.test_movie_story_review import produced_pair_archive as produced_pair_archive


@pytest.fixture
def branch_source(produced_pair_archive, tmp_path):
    archive, pid = produced_pair_archive
    store = restore_backup(archive, tmp_path / "story-branches")
    with TestClient(create_app(store.root, run_worker=False)) as client:
        yield store, pid, client


def branch(client, pid, revision=1, key=None):
    return client.post(
        f"/api/projects/{pid}/story-branch",
        json={"revision": revision, "idempotency_key": key or str(uuid4())},
    )


def test_alternative_story_has_editable_scripts_new_ids_and_no_media_or_queue(branch_source):
    store, pid, client = branch_source
    original = store.get(pid)
    hashes = {asset["id"]: digest(store.asset_path(asset["id"])[0]) for asset in original["assets"]}
    result = branch(client, pid)
    assert result.status_code == 201, result.text
    alternative = store.get(result.json()["project_id"])
    assert alternative["id"] != pid and alternative["revision"] == 1
    assert alternative["plan"]["ending"] == original["plan"]["ending"]
    assert alternative["jobs"] == [] and alternative["assets"] == [] and alternative["canon"] == []
    assert all(ep["can_edit_draft"] for ep in alternative["episodes"] if ep["script"])
    assert {c["id"] for c in original["plan"]["characters"]}.isdisjoint(
        c["id"] for c in alternative["plan"]["characters"]
    )
    assert {s["id"] for s in original["episodes"][0]["script"]["shots"]}.isdisjoint(
        s["id"] for s in alternative["episodes"][0]["script"]["shots"]
    )
    assert store.get(pid) == original
    for identity, sha in hashes.items():
        assert digest(store.asset_path(identity)[0]) == sha


def test_duplicate_branch_request_reuses_exact_project_even_after_source_revision_changes(branch_source):
    store, pid, client = branch_source
    key = str(uuid4())
    first = branch(client, pid, key=key)
    assert first.status_code == 201, first.text
    with store.connect() as db:
        db.execute("UPDATE projects SET revision=2 WHERE id=?", (pid,))
    second = branch(client, pid, key=key)
    assert second.status_code == 200 and second.json()["project_id"] == first.json()["project_id"]
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 2
        event = db.execute(
            "SELECT data FROM events WHERE project_id=? AND kind='story_branch_created'",
            (first.json()["project_id"],),
        ).fetchone()
        assert json.loads(event["data"])["source_revision"] == 1


def test_stale_branch_request_leaves_library_unchanged(branch_source):
    store, pid, client = branch_source
    before = store.get(pid)
    result = branch(client, pid, revision=99)
    assert result.status_code == 409 and "another window" in result.text
    assert store.get(pid) == before
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1


@pytest.mark.parametrize(
    "fault", ["active", "running_step", "no_plan", "wrong_cast", "wrong_episode", "episode_count"]
)
def test_ineligible_or_malformed_source_never_leaves_partial_branch(branch_source, fault):
    store, pid, client = branch_source
    source = store.get(pid)
    with store.connect() as db:
        if fault == "active":
            db.execute("UPDATE jobs SET state='PAUSED' WHERE project_id=? AND episode=1", (pid,))
        elif fault == "running_step":
            db.execute(
                "UPDATE steps SET state='RUNNING' WHERE job_id=? AND stage='EXPORT'",
                (source["jobs"][0]["id"],),
            )
        elif fault == "no_plan":
            db.execute("UPDATE projects SET plan=NULL WHERE id=?", (pid,))
        elif fault == "episode_count":
            db.execute("DELETE FROM episodes WHERE project_id=? AND number=3", (pid,))
        else:
            script = source["episodes"][0]["script"]
            if fault == "wrong_cast":
                script["shots"][0]["character_ids"] = [str(uuid4())]
            else:
                script["number"] = 2
            db.execute(
                "UPDATE episodes SET script=? WHERE project_id=? AND number=1", (json.dumps(script), pid)
            )
    before = store.get(pid)
    response = branch(client, pid)
    assert response.status_code == 409, response.text
    assert store.get(pid) == before
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1


def test_branch_can_render_saved_episodes_without_rewriting_story_and_survives_backup(
    branch_source, tmp_path, monkeypatch
):
    store, pid, client = branch_source
    original = store.get(pid)
    hashes = {asset["id"]: digest(store.asset_path(asset["id"])[0]) for asset in original["assets"]}
    result = branch(client, pid)
    new_id = result.json()["project_id"]
    scripts = [episode["script"] for episode in store.get(new_id)["episodes"]]
    set_silent(store)

    def no_rewrite(*_args, **_kwargs):
        pytest.fail("Saved branch screenplay unexpectedly invoked story generation")

    monkeypatch.setattr("studio.worker.DemoStory.script", no_rewrite)
    monkeypatch.setattr("studio.worker.DemoStory.plan", no_rewrite)
    for number in [1, 2]:
        store.enqueue(new_id, number)
        produced = produce_until(store, Worker(store), new_id)
        assert produced["episodes"][number - 1]["status"] == "COMPLETED"
        assert produced["episodes"][number - 1]["script"] == scripts[number - 1]
    assert store.get(pid) == original
    restored = restore_backup(
        create_backup(store, tmp_path / "alternatives.zip"), tmp_path / "alternatives-restored"
    )
    assert restored.get(new_id)["episodes"] == store.get(new_id)["episodes"]
    assert restored.get(pid)["assets"] == original["assets"]
    with restored.connect() as db:
        data = json.loads(
            db.execute(
                "SELECT data FROM events WHERE project_id=? AND kind='story_branch_created'", (new_id,)
            ).fetchone()[0]
        )
        assert data["source_project_id"] == pid and data["generation_started"] is False
    for identity, sha in hashes.items():
        assert digest(restored.asset_path(identity)[0]) == sha


def test_remapping_covers_props_knowledge_changes_and_flashbacks_without_rewriting_text(branch_source):
    store, pid, _ = branch_source
    source = store.get(pid)
    hero = source["plan"]["characters"][0]["id"]
    place = source["plan"]["locations"][0]["id"]
    prop = str(uuid4())
    source["plan"]["props"].append(
        {
            "id": prop,
            "name": "Notebook",
            "description": "A worn notebook with yellow pages.",
            "owner_id": hero,
        }
    )
    script = source["episodes"][0]["script"]
    script["shots"][0]["required_props"] = [{"prop_id": prop, "character_id": hero}]
    script["shots"][0]["required_knowledge"] = [
        {"character_id": hero, "fact": "The old signal returns at dusk."}
    ]
    script["proposed_changes"] += [
        {
            "after_shot": 1,
            "entity_id": prop,
            "field": "prop_owner",
            "before_value": hero,
            "value": hero,
            "reason": "The keeper retains the notebook after answering.",
        },
        {
            "after_shot": 1,
            "entity_id": hero,
            "field": "location",
            "before_value": place,
            "value": place,
            "reason": "The keeper stays inside the lighthouse.",
        },
    ]
    second = source["episodes"][1]["script"]["shots"][0]
    second.update(
        flashback_episode=1,
        flashback_after_shot=0,
        continuity_note="A memory before the signal was answered.",
    )
    _, episodes, ids, _, _ = copy_story(source, str(uuid4()))
    copied = episodes[0]["script"]
    assert copied["screenplay"] == script["screenplay"]
    assert copied["shots"][0]["required_props"] == [{"prop_id": ids[prop], "character_id": ids[hero]}]
    assert copied["shots"][0]["required_knowledge"][0]["character_id"] == ids[hero]
    assert copied["proposed_changes"][-2]["before_value"] == ids[hero]
    assert copied["proposed_changes"][-1]["value"] == ids[place]
    assert episodes[1]["script"]["shots"][0]["flashback_after_shot"] == 0


def test_branch_write_interruption_rolls_back_all_new_rows(branch_source, monkeypatch):
    store, pid, _ = branch_source
    original = store.get(pid)
    event = store.event

    def interrupted(db, project, job, kind, data):
        if kind == "story_branch_created":
            raise OSError("Simulated interrupted branch audit write")
        return event(db, project, job, kind, data)

    monkeypatch.setattr(store, "event", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        create_story_branch(store, pid, StoryBranchRequest(revision=1, idempotency_key=uuid4()))
    assert store.get(pid) == original
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1


def test_two_concurrent_same_requests_create_exactly_one_alternative(branch_source):
    store, pid, _ = branch_source
    request = StoryBranchRequest(revision=1, idempotency_key=uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_story_branch(store, pid, request), range(2)))
    assert results[0][0] == results[1][0] and sum(created for _, created in results) == 1


def test_uuid_and_revision_request_validation_is_strict(branch_source):
    store, pid, client = branch_source
    for payload in [
        {"revision": True, "idempotency_key": str(uuid4())},
        {"revision": 1, "idempotency_key": "not-a-uuid"},
    ]:
        result = client.post(f"/api/projects/{pid}/story-branch", json=payload)
        assert result.status_code == 422
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1


def test_branch_key_cannot_alias_an_unrelated_project_or_another_source_revision(branch_source):
    store, pid, client = branch_source
    occupied = str(uuid4())
    store.create(
        ProjectInput(
            idea="A different project owns this request key.",
            target_seconds=5,
            idempotency_key="story-branch:" + occupied,
        )
    )
    assert branch(client, pid, key=occupied).status_code == 409
    key = str(uuid4())
    first = branch(client, pid, key=key)
    assert first.status_code == 201
    with store.connect() as db:
        db.execute("UPDATE projects SET revision=2 WHERE id=?", (pid,))
    assert branch(client, pid, revision=2, key=key).status_code == 409


def test_missing_saved_scripts_cannot_create_empty_alternative(branch_source):
    store, pid, client = branch_source
    with store.connect() as db:
        db.execute("UPDATE episodes SET script=NULL WHERE project_id=?", (pid,))
    response = branch(client, pid)
    assert response.status_code == 409 and "saved screenplay" in response.text


def test_cancelled_source_can_be_branched_without_copied_commands_settings_or_committed_facts(branch_source):
    store, pid, client = branch_source
    with store.connect() as db:
        db.execute(
            "UPDATE jobs SET state='CANCELLED',config=? WHERE project_id=?",
            (
                json.dumps(
                    {"private_token": "SAMPLE_SECRET_DO_NOT_COPY", "command": "SAMPLE_PROVIDER_COMMAND"}
                ),
                pid,
            ),
        )
    source = store.get(pid)
    response = branch(client, pid)
    assert response.status_code == 201, response.text
    new_id = response.json()["project_id"]
    copied = store.get(new_id)
    assert not copied["jobs"] and not copied["canon"]
    with store.connect() as db:
        rows = db.execute("SELECT data FROM events WHERE project_id=?", (new_id,)).fetchall()
    assert "SAMPLE_SECRET_DO_NOT_COPY" not in json.dumps(copied) + json.dumps([list(row) for row in rows])
    assert store.get(pid) == source


def test_foreign_origin_and_missing_source_cannot_write_a_branch(branch_source):
    store, pid, client = branch_source
    payload = {"revision": 1, "idempotency_key": str(uuid4())}
    assert (
        client.post(
            f"/api/projects/{pid}/story-branch", json=payload, headers={"origin": "https://example.com"}
        ).status_code
        == 403
    )
    assert branch(client, str(uuid4())).status_code == 404
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1
