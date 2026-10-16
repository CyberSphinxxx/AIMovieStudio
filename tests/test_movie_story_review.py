"""Review declared continuity on retained demo movies, never native quality."""

from uuid import uuid4
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.domain import ProjectInput
from studio.shot_revisions import latest_movie
from studio.storage import Store, digest
from studio.worker import Worker
from studio.movie_story_review import MovieStoryReview, review_movie
from studio.shot_revisions import RetakeRequest, enqueue_retake
from tests.test_pipeline import produce_until, set_silent


@pytest.fixture(scope="module")
def produced_pair_archive(tmp_path_factory):
    directory = tmp_path_factory.mktemp("retained-movie-source")
    store = Store(directory / "source")
    spec = ProjectInput(
        idea="A lighthouse keeper follows an old signal and returns home.",
        kind="series",
        episodes=3,
        target_seconds=5,
        prewrite_season=True,
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    produce_until(store, worker, pid)
    store.enqueue(pid, 2)
    produce_until(store, worker, pid)
    return create_backup(store, directory / "completed-pair.zip"), pid


@pytest.fixture
def review_project(produced_pair_archive, tmp_path):
    archive, pid = produced_pair_archive
    store = restore_backup(archive, tmp_path / "review-library")
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.post(
            f"/api/projects/{pid}/canon",
            json={
                "revision": 1,
                "event": {
                    "episode": 1,
                    "entity_id": pid,
                    "field": "outcome",
                    "value": "The distant signal was answered.",
                    "reason": "Clarify the first episode outcome without changing the declared character facts.",
                },
            },
        )
        assert result.status_code == 200, result.text
        yield store, pid, client


def keep(client, project, **fields):
    return client.post(
        f"/api/projects/{project['id']}/episodes/2/review-movie",
        json={
            "revision": project["revision"],
            "source_export_id": latest_movie(project, 2)["id"],
            "reviewed_movie": True,
            **fields,
        },
    )


def test_keep_reviewed_movie_unlocks_continuation_and_preserves_original_outputs(review_project, tmp_path):
    store, pid, client = review_project
    before = store.get(pid)
    assert before["episodes"][1]["status"] == "REVIEW_REQUIRED"
    hashes = {a["id"]: digest(store.asset_path(a["id"])[0]) for a in before["assets"]}
    with pytest.raises(ValueError, match="[Rr]eview"):
        store.enqueue(pid, 3)
    result = keep(client, before)
    assert result.status_code == 200, result.text
    after = result.json()
    assert after["revision"] == 3 and after["episodes"][1]["status"] == "COMPLETED"
    assert after["episodes"][1]["script"] == before["episodes"][1]["script"]
    assert after["episodes"][0] == before["episodes"][0]
    assert after["episodes"][2] == before["episodes"][2]
    assert (
        after["canon"] == before["canon"]
        and after["assets"] == before["assets"]
        and after["jobs"] == before["jobs"]
    )
    assert keep(client, before).status_code == 409
    restored = restore_backup(create_backup(store, tmp_path / "reviewed.zip"), tmp_path / "reviewed-restored")
    assert restored.get(pid)["episodes"] == after["episodes"]
    store.enqueue(pid, 3)
    complete = produce_until(store, Worker(store), pid)
    assert complete["episodes"][2]["status"] == "COMPLETED"
    for identity, sha in hashes.items():
        assert digest(store.asset_path(identity)[0]) == sha


def test_review_never_overrides_a_real_declared_contradiction(review_project):
    store, pid, client = review_project
    project = store.get(pid)
    hero = project["plan"]["characters"][0]["id"]
    response = client.post(
        f"/api/projects/{pid}/canon",
        json={
            "revision": 2,
            "event": {
                "episode": 1,
                "entity_id": hero,
                "field": "alive",
                "value": "false",
                "reason": "The keeper dies at the end of the first episode.",
            },
        },
    )
    assert response.status_code == 200, response.text
    before = store.get(pid)
    result = keep(client, before)
    assert result.status_code == 409 and "CANON_CONFLICT" in result.text and hero in result.text
    assert response.json()["event_id"] in result.text
    assert store.get(pid) == before


@pytest.mark.parametrize(
    "fields",
    [{"revision": 99}, {"source_export_id": str(uuid4())}, {"reviewed_movie": 1}, {"reviewed_movie": "true"}],
)
def test_stale_foreign_or_coerced_review_never_mutates(review_project, fields):
    store, pid, client = review_project
    before = store.get(pid)
    result = keep(client, before, **fields)
    assert result.status_code in {409, 422}, result.text
    assert store.get(pid) == before


@pytest.mark.parametrize(
    "fault",
    [
        "active",
        "running",
        "earlier_review",
        "missing_fact",
        "changed_script",
        "wrong_shot",
        "wrong_duration",
        "missing_parent",
        "wrong_provider",
        "missing_checkpoint",
    ],
)
def test_incompatible_saved_evidence_blocks_keep(review_project, fault):
    store, pid, client = review_project
    project = store.get(pid)
    movie = latest_movie(project, 2)
    with store.connect() as db:
        if fault == "active":
            db.execute("UPDATE jobs SET state='PAUSED' WHERE project_id=? AND episode=1", (pid,))
        elif fault == "running":
            db.execute(
                "UPDATE steps SET state='RUNNING' WHERE job_id=? AND stage='EXPORT'",
                (project["jobs"][0]["id"],),
            )
        elif fault == "earlier_review":
            db.execute("UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number=1", (pid,))
        elif fault == "missing_fact":
            db.execute("DELETE FROM canon WHERE project_id=? AND episode=2", (pid,))
        elif fault == "changed_script":
            script = project["episodes"][1]["script"]
            script["shots"][0]["narration"] = "An unrendered different line."
            db.execute(
                "UPDATE episodes SET script=? WHERE project_id=? AND number=2", (json.dumps(script), pid)
            )
        elif fault == "missing_checkpoint":
            db.execute(
                "UPDATE steps SET output=NULL WHERE job_id=? AND stage='SCRIPT'", (project["jobs"][1]["id"],)
            )
        else:
            asset = (
                movie
                if fault in {"missing_parent", "wrong_provider"}
                else next(
                    a for a in project["assets"] if a["role"] == "clip" and a["metadata"]["episode"] == 2
                )
            )
            metadata = asset["metadata"]
            if fault == "wrong_shot":
                metadata["shot_id"] = str(uuid4())
            elif fault == "wrong_duration":
                metadata["duration"] = 100
            elif fault == "missing_parent":
                metadata["parent_asset_ids"] = [str(uuid4())]
            else:
                metadata["is_mock"] = False
            db.execute("UPDATE assets SET metadata=? WHERE id=?", (json.dumps(metadata), asset["id"]))
    before = store.get(pid)
    result = keep(client, before)
    assert result.status_code == 409, result.text
    assert store.get(pid) == before


def test_changed_movie_bytes_and_manual_own_facts_cannot_be_kept(review_project):
    store, pid, client = review_project
    before = store.get(pid)
    movie = latest_movie(before, 2)
    store.asset_path(movie["id"])[0].write_bytes(b"DEVELOPMENT corrupt sample movie")
    assert keep(client, before).status_code == 409
    assert store.get(pid) == before


def test_manual_correction_of_the_episodes_own_canon_needs_a_story_revision(review_project):
    store, pid, client = review_project
    response = client.post(
        f"/api/projects/{pid}/canon",
        json={
            "revision": 2,
            "event": {
                "episode": 2,
                "entity_id": pid,
                "field": "outcome",
                "value": "The keeper never returned.",
                "reason": "A different outcome cannot silently approve the original finished movie.",
            },
        },
    )
    assert response.status_code == 200
    before = store.get(pid)
    assert keep(client, before).status_code == 409
    assert store.get(pid) == before


def test_review_transaction_rolls_back_if_audit_write_is_interrupted(review_project, monkeypatch):
    store, pid, client = review_project
    before = store.get(pid)
    original = Store.event

    def interrupted(self, db, pid, jid, kind, data):
        original(self, db, pid, jid, kind, data)
        if kind == "movie_story_review":
            raise OSError("DEVELOPMENT simulated interrupted audit transaction")

    monkeypatch.setattr(Store, "event", interrupted)
    with pytest.raises(OSError, match="simulated interrupted"):
        keep(client, before)
    assert store.get(pid) == before
    with store.connect() as db:
        assert not db.execute("SELECT 1 FROM events WHERE kind='movie_story_review'").fetchone()


def test_concurrent_keep_decisions_serialize_at_one_project_revision(review_project):
    store, pid, _ = review_project
    project = store.get(pid)
    request = MovieStoryReview(
        revision=2, source_export_id=latest_movie(project, 2)["id"], reviewed_movie=True
    )

    def compete(_):
        try:
            review_movie(store, pid, 2, request)
            return "saved"
        except ValueError as error:
            assert "another window" in str(error)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(compete, range(2))) == ["saved", "stale"]
    assert store.get(pid)["revision"] == 3


def test_latest_retake_can_be_reviewed_and_an_older_cut_is_refused(review_project):
    store, pid, client = review_project
    before = store.get(pid)
    assert keep(client, before).status_code == 200
    approved = store.get(pid)
    original = latest_movie(approved, 2)
    shot = approved["episodes"][1]["script"]["shots"][0]
    enqueue_retake(
        store,
        pid,
        2,
        shot["id"],
        RetakeRequest(source_export_id=original["id"], revision=3, idempotency_key=str(uuid4()), seed=999),
    )
    produced = produce_until(store, Worker(store), pid)
    newest = latest_movie(produced, 2)
    assert newest["id"] != original["id"]
    response = client.post(
        f"/api/projects/{pid}/canon",
        json={
            "revision": 3,
            "event": {
                "episode": 1,
                "entity_id": pid,
                "field": "outcome",
                "value": "The keeper answered the distant signal.",
                "reason": "Clarify the earlier outcome after saving the visual retake.",
            },
        },
    )
    assert response.status_code == 200
    revised = store.get(pid)
    assert keep(client, revised, source_export_id=original["id"]).status_code == 409
    assert keep(client, revised).status_code == 200
    assert digest(store.asset_path(newest["id"])[0]) == newest["sha256"]


def test_manual_review_confirmation_is_required(review_project):
    store, pid, client = review_project
    before = store.get(pid)
    result = keep(client, before, reviewed_movie=False)
    assert result.status_code == 409
    assert store.get(pid) == before
