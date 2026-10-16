"""Explicit timing annotations preserve the original fact and prior evidence."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from scripts.checkpoint_browser_smoke import fixture
from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.domain import EpisodeScript, SeasonPlan, continuity_errors
from studio.storage import Store
from studio.canon_timing import with_timing
from studio import backup_import
from studio.canon_revisions import CanonTimingRevision, assign_timing
from studio.storage import digest
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


@pytest.fixture
def legacy_fact(tmp_path):
    sample = fixture(tmp_path / "legacy-time")
    store = Store(Path(sample["root"]))
    pid, identity = sample["id"], str(uuid4())
    hero = store.get(pid)["plan"]["characters"][0]["id"]
    with store.connect() as db:
        db.execute(
            "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)",
            (identity, pid, hero, 1, "alive", "false", "A legacy declared death without shot evidence.", 1),
        )
    with TestClient(create_app(store.root, run_worker=False)) as client:
        yield store, pid, identity, client


def annotate(client, pid, identity, **fields):
    return client.post(
        f"/api/projects/{pid}/canon/{identity}/timing",
        json={
            "revision": 1,
            "after_shot": 2,
            "reason": "The declared death happens after the second shot.",
            **fields,
        },
    )


def raw(store):
    with store.connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM canon ORDER BY rowid")]


def test_timing_assignment_repairs_exact_flashback_without_rewriting_fact(legacy_fact, tmp_path):
    store, pid, identity, client = legacy_fact
    before, original = store.get(pid), raw(store)
    script = EpisodeScript.model_validate(before["episodes"][1]["script"])
    plan = SeasonPlan.model_validate(before["plan"])
    assert any(
        "no verified shot timing" in e
        for e in continuity_errors(script, before["canon"], plan, episode_lengths={1: 3})
    )
    result = annotate(client, pid, identity)
    assert result.status_code == 200, result.text
    after = result.json()
    assert after["revision"] == 2
    assert after["canon"][0]["id"] == identity and after["canon"][0]["after_shot"] == 2
    assert after["canon"][0]["timing_status"] == "after_shot"
    assert raw(store) == original
    assert after["episodes"][0] == before["episodes"][0]
    assert after["episodes"][1]["script"] == before["episodes"][1]["script"]
    assert after["episodes"][1]["status"] == "REVIEW_REQUIRED"
    assert after["jobs"] == before["jobs"] and after["assets"] == before["assets"]
    assert not continuity_errors(script, after["canon"], plan, episode_lengths={1: 3})
    with store.connect() as db:
        event = json.loads(
            db.execute("SELECT data FROM events WHERE kind='canon_timing_revision'").fetchone()[0]
        )
    assert event["event_id"] == identity and event["source_canon"]["revision"] == 1
    assert event["previous_timing"]["timing_status"] == "episode_only"
    assert event["revision"] == 2 and event["after_shot"] == 2
    assert Store(store.root).get(pid)["canon"] == after["canon"]
    restored = restore_backup(create_backup(store, tmp_path / "timing.zip"), tmp_path / "restored")
    assert restored.get(pid)["canon"] == after["canon"]
    assert raw(restored) == original


def test_explicit_end_and_newer_annotation_override_without_erasing_history(legacy_fact):
    store, pid, identity, client = legacy_fact
    original = raw(store)
    result = annotate(client, pid, identity, after_shot=None)
    assert result.status_code == 200, result.text
    assert result.json()["canon"][0]["timing_status"] == "episode_end"
    result = annotate(client, pid, identity, revision=2, after_shot=0)
    assert result.status_code == 200, result.text
    assert result.json()["canon"][0]["after_shot"] == 0
    assert raw(store) == original
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='canon_timing_revision'").fetchone()[0] == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"revision": 99},
        {"after_shot": 4},
        {"after_shot": -1},
        {"after_shot": True},
        {"after_shot": "1"},
        {"after_shot": 1.5},
        {"reason": "        "},
    ],
)
def test_invalid_annotation_is_atomic(legacy_fact, fields):
    store, pid, identity, client = legacy_fact
    before = store.get(pid)
    result = annotate(client, pid, identity, **fields)
    assert result.status_code in {409, 422}, result.text
    assert store.get(pid) == before


def test_missing_position_is_not_implicitly_episode_end(legacy_fact):
    store, pid, identity, client = legacy_fact
    result = client.post(
        f"/api/projects/{pid}/canon/{identity}/timing",
        json={"revision": 1, "reason": "An explicit timing correction."},
    )
    assert result.status_code == 422
    assert store.get(pid)["revision"] == 1


def test_retry_and_foreign_fact_cannot_append_another_revision(legacy_fact):
    store, pid, identity, client = legacy_fact
    assert annotate(client, pid, identity).status_code == 200
    saved = store.get(pid)
    assert annotate(client, pid, identity).status_code == 409
    assert annotate(client, pid, str(uuid4()), revision=2).status_code == 404
    other = fixture(store.root)
    # A real other project with a foreign fact ID is inaccessible in that scope.
    assert annotate(client, other["id"], identity).status_code == 404
    assert store.get(pid) == saved


@pytest.mark.parametrize("fault", ["outcome", "unreviewed", "missing_script", "active_job", "running_step"])
def test_unsafe_sources_and_inflight_work_block_annotation(legacy_fact, fault):
    store, pid, identity, client = legacy_fact
    with store.connect() as db:
        if fault == "outcome":
            db.execute("UPDATE canon SET field='outcome',entity_id=? WHERE id=?", (pid, identity))
        elif fault == "unreviewed":
            db.execute("UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number=1", (pid,))
        elif fault == "missing_script":
            db.execute("UPDATE episodes SET script=NULL WHERE project_id=? AND number=1", (pid,))
        else:
            job = str(uuid4())
            db.execute(
                "INSERT INTO jobs(id,project_id,episode,state,created) VALUES(?,?,?,?,0)",
                (job, pid, 1, "QUEUED" if fault == "active_job" else "FAILED"),
            )
            if fault == "running_step":
                store.add_step(db, job, 0, "SCRIPT", {"episode": 1})
                db.execute("UPDATE steps SET state='RUNNING' WHERE job_id=?", (job,))
    before = store.get(pid)
    result = annotate(client, pid, identity)
    assert result.status_code == 409, result.text
    assert store.get(pid) == before


def source(row, seq=10, revision=2, **fields):
    return {
        "kind": "canon_timing_revision",
        "seq": seq,
        "data": json.dumps(
            {
                "event_id": row["id"],
                "source_canon": {
                    key: row[key] for key in ("episode", "entity_id", "field", "value", "reason", "revision")
                },
                "revision": revision,
                "after_shot": 2,
                "reason": "Explicit correction to the recorded timing.",
                **fields,
            }
        ),
    }


def test_conflicting_latest_annotations_fail_closed_and_a_newer_correction_resolves(legacy_fact):
    store, _, _, _ = legacy_fact
    row = raw(store)[0]
    evidence = [source(row), source(row, seq=11, after_shot=1)]
    result = with_timing([row], evidence, project_revision=2)[0]
    assert result["timing_status"] == "episode_only" and result["timing_source_seq"] is None
    evidence.append(source(row, seq=12, revision=3, after_shot=0))
    result = with_timing([row], evidence, project_revision=3)[0]
    assert result["after_shot"] == 0 and result["timing_source_seq"] == 12


@pytest.mark.parametrize(
    "fault",
    [
        "foreign_id",
        "wrong_fact",
        "wrong_canon_revision",
        "future_revision",
        "old_revision",
        "bool_revision",
        "missing_position",
        "malformed_json",
        "list_json",
        "bad_position",
        "missing_reason",
    ],
)
def test_malformed_or_unlinked_annotation_never_grants_precision(legacy_fact, fault):
    store, _, _, _ = legacy_fact
    row = raw(store)[0]
    event = source(row)
    data = json.loads(event["data"])
    if fault == "foreign_id":
        data["event_id"] = str(uuid4())
    elif fault == "wrong_fact":
        data["source_canon"]["value"] = "true"
    elif fault == "wrong_canon_revision":
        data["source_canon"]["revision"] = 99
    elif fault == "future_revision":
        data["revision"] = 3
    elif fault == "old_revision":
        data["revision"] = 1
    elif fault == "bool_revision":
        data["revision"] = True
    elif fault == "missing_position":
        del data["after_shot"]
    elif fault == "bad_position":
        data["after_shot"] = True
    elif fault == "missing_reason":
        del data["reason"]
    event["data"] = "{" if fault == "malformed_json" else json.dumps([] if fault == "list_json" else data)
    assert with_timing([row], [event], project_revision=2)[0]["timing_status"] == "episode_only"


def test_import_into_populated_library_relinks_projection_to_new_event_sequence(legacy_fact, tmp_path):
    store, pid, identity, client = legacy_fact
    assert annotate(client, pid, identity).status_code == 200
    archive = create_backup(store, tmp_path / "import-timing.zip")
    target = Store(tmp_path / "populated-library")
    fixture(target.root)
    operation, directory = backup_import.begin_upload(target)
    (directory / "upload.zip").write_bytes(archive.read_bytes())
    backup_import.prepare_import(target, operation)
    backup_import.commit_import(target, operation)
    imported = target.get(pid)["canon"][0]
    assert imported["id"] == identity and imported["after_shot"] == 2
    assert imported["timing_source_seq"] != store.get(pid)["canon"][0]["timing_source_seq"]
    assert raw(target) == raw(store)


def test_competing_corrections_commit_only_one_expected_revision(legacy_fact):
    store, pid, identity, _ = legacy_fact

    def compete(position):
        try:
            assign_timing(
                store,
                pid,
                identity,
                CanonTimingRevision(
                    revision=1, after_shot=position, reason="One explicit concurrent timing correction."
                ),
            )
            return "saved"
        except ValueError as error:
            assert "another window" in str(error)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(compete, [0, 2])) == ["saved", "stale"]
    assert store.get(pid)["revision"] == 2
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='canon_timing_revision'").fetchone()[0] == 1


def test_timing_correction_preserves_completed_demo_movie_bytes(store, spec, tmp_path):
    spec.kind, spec.episodes, spec.prewrite_season = "series", 2, True
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    completed = produce_until(store, Worker(store), pid)
    assert completed["episodes"][0]["status"] == "COMPLETED"
    identity = str(uuid4())
    with store.connect() as db:
        db.execute(
            "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)",
            (
                identity,
                pid,
                completed["plan"]["characters"][0]["id"],
                1,
                "knowledge",
                "The signal came from the ship.",
                "A legacy fact with no linked shot timing.",
                1,
            ),
        )
    original = raw(store)
    hashes = {asset["id"]: digest(store.asset_path(asset["id"])[0]) for asset in completed["assets"]}
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = annotate(client, pid, identity, after_shot=1)
        assert result.status_code == 200, result.text
        movie = next(asset for asset in completed["assets"] if asset["role"] == "export")
        assert client.get(f"/api/assets/{movie['id']}/content").status_code == 200
    after = store.get(pid)
    assert after["episodes"][0] == completed["episodes"][0]
    assert after["jobs"] == completed["jobs"] and after["assets"] == completed["assets"]
    assert raw(store) == original
    for identity, sha in hashes.items():
        assert digest(store.asset_path(identity)[0]) == sha
    restored = restore_backup(
        create_backup(store, tmp_path / "preserved-timed-movie.zip"), tmp_path / "movie-restored"
    )
    assert restored.get(pid)["canon"] == after["canon"]
    for identity, sha in hashes.items():
        assert digest(restored.asset_path(identity)[0]) == sha
