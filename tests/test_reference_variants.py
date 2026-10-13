"""MOCK visual fixtures verify lineage/choices; they do not prove pose or identity quality."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.domain import stable
from studio.reference_variants import ReferenceVariant, ReferenceSelection, enqueue_variant, select_reference
from studio.shot_revisions import discard_retake, enqueue_retake
from studio.storage import digest, atomic_json
from studio.worker import Worker
from tests.test_export_variants import finish
from tests.test_pipeline import produce_until
from tests.test_shot_revisions import request_for, shot_id


def original_reference(project, entity_id):
    return next(
        a for a in project["assets"] if a["role"] == "reference" and a["metadata"]["entity_id"] == entity_id
    )


def request(project, entity_id, view="side", seed=1, key="test-reference-view"):
    return ReferenceVariant(
        source_reference_id=original_reference(project, entity_id)["id"],
        revision=project["revision"],
        idempotency_key=key,
        view=view,
        seed=seed,
    )


def select(store, project, entity_id, asset_id):
    return select_reference(
        store,
        project["id"],
        entity_id,
        ReferenceSelection(
            asset_id=asset_id,
            revision=project["revision"],
            current_asset_id=project["reference_choices"][entity_id]["asset_id"],
        ),
    )


def test_reference_choice_only_changes_new_episode_shots_and_old_retakes_stay_pinned(store, spec):
    spec.kind, spec.episodes, spec.target_seconds = "series", 2, 10
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    source = original_reference(original, entity)
    variant_request = request(original, entity)
    with ThreadPoolExecutor(4) as pool:
        requests = list(pool.map(lambda _: enqueue_variant(store, pid, entity, variant_request), range(6)))
    assert len({r["step_id"] for r in requests}) == 1 and sum(not r["reused"] for r in requests) == 1
    candidate = produce_until(store, Worker(store), pid)
    asset = next(a for a in candidate["assets"] if a["role"] == "reference-variant")
    assert candidate["reference_choices"][entity]["asset_id"] == source["id"]
    assert candidate["episodes"] == original["episodes"] and candidate["canon"] == original["canon"]
    assert asset["metadata"]["parent_asset_ids"] == [source["id"]]
    assert asset["metadata"]["parent_hashes"] == [source["sha256"]]
    assert asset["metadata"]["requested_view"] == "side" and asset["metadata"]["is_mock"]
    select(store, candidate, entity, asset["id"])
    chosen = store.get(pid)
    assert chosen["reference_choices"][entity]["asset_id"] == asset["id"]
    assert chosen["revision"] == original["revision"] and chosen["canon"] == original["canon"]
    # Old-movie retakes still consume their original frame's references.
    enqueue_retake(store, pid, 1, shot_id(chosen), request_for(chosen))
    retaken = produce_until(store, Worker(store), pid)
    frame = next(a for a in retaken["assets"] if a["role"] == "keyframe-revision")
    assert (
        source["id"] in frame["metadata"]["parent_asset_ids"]
        and asset["id"] not in frame["metadata"]["parent_asset_ids"]
    )
    store.enqueue(pid, 2)
    finished = produce_until(store, Worker(store), pid)
    frames = [a for a in finished["assets"] if a["role"] == "keyframe" and a["metadata"]["episode"] == 2]
    affected = [a for a in frames if entity in a["metadata"]["reference_versions"]]
    assert affected and all(asset["id"] in a["metadata"]["parent_asset_ids"] for a in affected)
    assert all(source["id"] not in a["metadata"]["parent_asset_ids"] for a in affected)
    assert all(a["metadata"]["reference_versions"][entity] == 2 for a in affected)
    assert all(digest(store.asset_path(a["id"])[0]) == a["sha256"] for a in original["assets"])
    assert finished["canon"][: len(original["canon"])] == original["canon"]
    # New-movie retakes use the new movie's pinned variant, irrespective of later selection.
    select(store, finished, entity, source["id"])
    baseline = store.get(pid)
    enqueue_retake(
        store,
        pid,
        2,
        shot_id(baseline, episode=2),
        request_for(baseline, episode=2, key="test-episode-two-take"),
    )
    revised = produce_until(store, Worker(store), pid)
    new_frame = next(
        a for a in revised["assets"] if a["role"] == "keyframe-revision" and a["metadata"]["episode"] == 2
    )
    assert asset["id"] in new_frame["metadata"]["parent_asset_ids"]


def test_validation_stale_selection_and_request_caps(store, spec):
    pid, project = finish(store, spec)
    entity = project["plan"]["characters"][0]["id"]
    source = original_reference(project, entity)
    url = f"/api/projects/{pid}/references/{entity}"
    with TestClient(create_app(store.root, run_worker=False)) as client:
        body = request(project, entity).model_dump()
        assert client.post(url + "/variants", json=body | {"path": "../file"}).status_code == 422
        assert client.post(url + "/variants", json=body | {"revision": 99}).status_code == 409
        assert client.post(url + "/variants", json=body | {"view": "angle"}).status_code == 409
        assert client.post(url + "/variants", json=body | {"seed": 0}).status_code == 422
        assert client.post(url + "/variants", json=body).status_code == 202
        assert client.post(url + "/variants", json=body | {"seed": 2}).status_code == 409
        assert (
            client.post(
                url + "/select",
                json={
                    "asset_id": source["id"],
                    "current_asset_id": source["id"],
                    "revision": project["revision"],
                },
            ).status_code
            == 409
        )
    first = produce_until(store, Worker(store), pid)
    candidate = next(a for a in first["assets"] if a["role"] == "reference-variant")
    select(store, first, entity, candidate["id"])
    chosen = store.get(pid)
    stale = ReferenceSelection(
        asset_id=source["id"], current_asset_id=source["id"], revision=chosen["revision"]
    )
    with pytest.raises(ValueError, match="Current reference changed"):
        select_reference(store, pid, entity, stale)
    assert select(store, chosen, entity, candidate["id"])["reused"]
    for number in (2, 3):
        current = store.get(pid)
        enqueue_variant(
            store, pid, entity, request(current, entity, seed=number, key=f"test-ref-request-{number}")
        )
        store.control(pid, "cancel", 1)
        discard_retake(store, pid, 1, allowed_stages={"REFERENCE_VARIANT"})
    with pytest.raises(ValueError, match="three reference-view"):
        enqueue_variant(store, pid, entity, request(store.get(pid), entity, seed=4, key="test-fourth-ref"))
    assert store.get(pid)["canon"] == project["canon"]


def test_source_and_selection_checksums_other_entity_or_project_are_rejected(store, spec):
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    enqueue_variant(store, pid, entity, request(original, entity))
    candidate = produce_until(store, Worker(store), pid)
    asset = next(a for a in candidate["assets"] if a["role"] == "reference-variant")
    other = original_reference(original, original["plan"]["characters"][1]["id"])
    with pytest.raises(ValueError, match="another entity"):
        select(store, candidate, entity, other["id"])
    with pytest.raises(ValueError, match="does not belong"):
        select(store, candidate, entity, "00000000-0000-0000-0000-000000000000")
    store.asset_path(asset["id"])[0].write_bytes(b"CORRUPT MOCK CANDIDATE")
    with pytest.raises(RuntimeError, match="checksum"):
        select(store, candidate, entity, asset["id"])
    assert (
        store.get(pid)["reference_choices"][entity]["asset_id"] == original_reference(original, entity)["id"]
    )
    enqueue_variant(store, pid, entity, request(candidate, entity, seed=2, key="test-second-source"))
    step = Worker(store).claim()
    store.asset_path(original_reference(original, entity)["id"])[0].write_bytes(b"CORRUPT ORIGINAL")
    with pytest.raises(RuntimeError, match="checksum"):
        Worker(store).execute(step)


def test_candidates_selection_and_paused_receipt_survive_backup(store, spec, tmp_path):
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    enqueue_variant(store, pid, entity, request(original, entity))
    worker = Worker(store)
    step = worker.claim()
    output = worker.execute(step)
    atomic_json(worker.directory(step) / "receipt.json", output)
    worker.recover()
    project = store.get(pid)
    asset = next(a for a in project["assets"] if a["role"] == "reference-variant")
    select(store, project, entity, asset["id"])
    chosen = store.get(pid)
    enqueue_variant(
        store, pid, entity, request(chosen, entity, view="full_body", seed=2, key="test-full-body-ref")
    )
    store.control(pid, "pause", 1)
    archive = tmp_path / "references.zip"
    create_backup(store, archive)
    restored = restore_backup(archive, tmp_path / "restored")
    assert restored.get(pid)["reference_choices"] == chosen["reference_choices"]
    assert restored.get(pid)["jobs"][0]["state"] == "PAUSED"
    restored.control(pid, "resume", 1)
    completed = produce_until(restored, Worker(restored), pid)
    assert len([a for a in completed["assets"] if a["role"] == "reference-variant"]) == 2
    assert completed["reference_choices"] == chosen["reference_choices"]
    assert completed["canon"] == original["canon"]
    assert all(digest(restored.asset_path(a["id"])[0]) == a["sha256"] for a in chosen["assets"])


def test_native_reference_contract_failure_never_falls_back_to_demo(store, spec, monkeypatch):
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    source = original_reference(original, entity)
    with store.connect() as db:
        db.execute(
            "UPDATE projects SET spec=? WHERE id=?",
            (json.dumps(original["spec"] | {"backend": "local"}), pid),
        )
        db.execute(
            "UPDATE assets SET metadata=? WHERE id=?",
            (
                json.dumps(source["metadata"] | {"is_mock": False, "provider": "TEST-CONTRACT-ONLY"}),
                source["id"],
            ),
        )
    original = store.get(pid)
    enqueue_variant(store, pid, entity, request(original, entity, seed=17))

    def image(_self, prompt, directory, size, check, references=None, seed=0):
        assert references == [store.asset_path(source["id"])[0]] and seed == 17
        assert "Side profile" in prompt and "Keep the same identity" in prompt
        raise RuntimeError("TEST_NATIVE_PROVIDER_UNAVAILABLE")

    monkeypatch.setattr("studio.providers.WanGPProvider.image", image)
    with pytest.raises(RuntimeError, match="TEST_NATIVE_PROVIDER_UNAVAILABLE"):
        Worker(store).execute(Worker(store).claim())
    assert not any(a["role"] == "reference-variant" for a in store.get(pid)["assets"])


def test_reference_receipt_recovers_after_actual_child_kill(store, spec, tmp_path):
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    queued = enqueue_variant(store, pid, entity, request(original, entity))
    marker = tmp_path / "published-reference"
    code = """
import os, time
from pathlib import Path
from studio.storage import Store, atomic_json
from studio.worker import Worker
w = Worker(Store(Path(os.environ['STUDIO_DATA'])))
s = w.claim()
assert s['stage'] == 'REFERENCE_VARIANT'
o = w.execute(s)
w.verify(o)
atomic_json(w.directory(s) / 'receipt.json', o)
Path(os.environ['REFERENCE_MARKER']).write_text(s['id'])
while True: time.sleep(1)
"""
    with (tmp_path / "worker.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            env=os.environ | {"STUDIO_DATA": str(store.root), "REFERENCE_MARKER": str(marker)},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 20
            while not marker.exists():
                assert process.poll() is None, (tmp_path / "worker.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(0.05)
            process.kill()
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    worker = Worker(store)
    worker.recover()
    result = store.get(pid)
    assert result["jobs"][0]["state"] == "SUCCEEDED"
    assert sum(a["id"] == stable(queued["step_id"], "reference-variant") for a in result["assets"]) == 1
    assert result["reference_choices"] == original["reference_choices"]
    assert result["canon"] == original["canon"]


def test_legacy_pending_frames_keep_original_references(store, spec):
    spec.kind, spec.episodes = "series", 2
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    enqueue_variant(store, pid, entity, request(original, entity))
    project = produce_until(store, Worker(store), pid)
    candidate = next(a for a in project["assets"] if a["role"] == "reference-variant")
    select(store, project, entity, candidate["id"])
    store.enqueue(pid, 2)
    worker = Worker(store)
    project = produce_until(store, worker, pid, "SCRIPT", 1)
    # A persisted job from an older app version has no explicit reference snapshot.
    with store.connect() as db:
        for step in project["jobs"][1]["steps"]:
            if step["stage"] == "FRAME":
                payload = step["payload"].copy()
                payload.pop("reference_inputs")
                db.execute("UPDATE steps SET payload=? WHERE id=?", (json.dumps(payload), step["id"]))
    completed = produce_until(store, worker, pid)
    frame = next(a for a in completed["assets"] if a["role"] == "keyframe" and a["metadata"]["episode"] == 2)
    assert original_reference(original, entity)["id"] in frame["metadata"]["parent_asset_ids"]
    assert candidate["id"] not in frame["metadata"]["parent_asset_ids"]


def test_reference_revision_race_dimensions_and_disk_errors_preserve_old_choice(store, spec, monkeypatch):
    from PIL import Image

    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    enqueue_variant(store, pid, entity, request(original, entity))
    worker = Worker(store)
    step = worker.claim()
    with monkeypatch.context() as patch:
        patch.setattr(
            "studio.reference_variants.shutil.disk_usage", lambda _: type("Disk", (), {"free": 0})()
        )
        with pytest.raises(RuntimeError, match="DISK_FULL"):
            worker.execute(step)

    def wrong_size(path, *_args, **_kwargs):
        Image.new("RGB", (20, 30)).save(path)

    with monkeypatch.context() as patch:
        patch.setattr("studio.media.demo_image", wrong_size)
        with pytest.raises(RuntimeError, match="dimensions"):
            worker.execute(step)
    output = worker.execute(step)
    with store.connect() as db:
        db.execute("UPDATE projects SET revision=revision+1 WHERE id=?", (pid,))
    with pytest.raises(RuntimeError, match="CANON_CONFLICT"):
        worker.complete(step, output)
    assert store.get(pid)["reference_choices"] == original["reference_choices"]
    assert not any(a["role"] == "reference-variant" for a in store.get(pid)["assets"])


def test_reference_failure_retry_limit_and_atomic_discard(store, spec, monkeypatch):
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    enqueue_variant(store, pid, entity, request(original, entity))

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("TEST_REFERENCE_UNAVAILABLE")

    monkeypatch.setattr("studio.media.demo_image", unavailable)
    worker = Worker(store)
    worker.start()
    try:
        for attempt in range(1, 4):
            if attempt > 1:
                store.control(pid, "resume", 1)
            deadline = time.monotonic() + 10
            while store.get(pid)["jobs"][0]["state"] != "FAILED":
                assert time.monotonic() < deadline
                time.sleep(0.05)
            assert store.get(pid)["jobs"][0]["steps"][-1]["attempts"] == attempt
        with pytest.raises(ValueError, match="Retry budget exhausted"):
            store.control(pid, "resume", 1)
        with TestClient(create_app(store.root, run_worker=False)) as client:
            assert client.post(f"/api/projects/{pid}/episodes/1/discard-reference-view").status_code == 200
        project = store.get(pid)
        assert project["reference_choices"] == original["reference_choices"]
        assert project["jobs"][0]["state"] == "SUCCEEDED"
        assert project["jobs"][0]["steps"][-1]["state"] == "SUPERSEDED"
    finally:
        worker.close()


def test_invalid_reference_selection_is_rejected_before_backup_import(store, spec, tmp_path):
    pid, original = finish(store, spec)
    entity = original["plan"]["characters"][0]["id"]
    select(store, original, entity, original_reference(original, entity)["id"])
    with store.connect() as db:
        store.event(
            db,
            pid,
            None,
            "reference_selected",
            {"entity_id": entity, "asset_id": original_reference(original, entity)["id"], "sha256": "0" * 64},
        )
    archive = tmp_path / "corrupt-choice.zip"
    create_backup(store, archive)
    with pytest.raises(ValueError, match="reference choice"):
        restore_backup(archive, tmp_path / "restored")
