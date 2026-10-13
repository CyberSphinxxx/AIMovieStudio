"""Explicit MOCK retake tests; these do not prove native inference or quality."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from studio import media
from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.export_variants import ExportCopy, enqueue_copy
from studio.shot_revisions import RetakeRequest, discard_retake, enqueue_retake, latest_movie
from studio.storage import atomic_json, digest
from studio.worker import Worker
from tests.test_export_variants import finish
from tests.test_pipeline import produce_until


def request_for(project, episode=1, seed=8, key="test-retake-request"):
    return RetakeRequest(
        source_export_id=latest_movie(project, episode)["id"],
        revision=project["revision"],
        seed=seed,
        idempotency_key=key,
    )


def shot_id(project, episode=1, index=0):
    return project["episodes"][episode - 1]["script"]["shots"][index]["id"]


def run_one(worker):
    step = worker.claim()
    result = worker.execute(step)
    worker.verify(result)
    atomic_json(worker.directory(step) / "receipt.json", result)
    worker.complete(step, result)
    return step


def test_cumulative_cuts_preserve_other_shots_audio_canon_and_copy_source(store, spec):
    spec.target_seconds = 10
    pid, original = finish(store, spec)
    sid = shot_id(original)
    request = request_for(original)
    with ThreadPoolExecutor(4) as pool:
        requests = list(pool.map(lambda _: enqueue_retake(store, pid, 1, sid, request), range(8)))
    assert len({r["step_id"] for r in requests}) == 1
    assert sum(not r["reused"] for r in requests) == 1
    with pytest.raises(ValueError, match="different take"):
        enqueue_retake(store, pid, 1, sid, request.model_copy(update={"seed": 9}))
    second = produce_until(store, Worker(store), pid)
    movie1, movie2 = latest_movie(original, 1), latest_movie(second, 1)
    assert movie2["metadata"]["edition"] == 2 and movie2["metadata"]["is_mock"]
    assert movie2["metadata"]["parent_asset_ids"][0] != movie1["metadata"]["parent_asset_ids"][0]
    assert movie2["metadata"]["parent_asset_ids"][1:] == movie1["metadata"]["parent_asset_ids"][1:]
    assert second["canon"] == original["canon"] and second["episodes"] == original["episodes"]
    assert second["revision"] == original["revision"]
    media.validate_video(store.asset_path(movie2["id"])[0], (360, 640), 10, audio=True)
    enqueue_retake(
        store, pid, 1, shot_id(second, index=1), request_for(second, seed=9, key="test-other-shot")
    )
    third = produce_until(store, Worker(store), pid)
    movie3 = latest_movie(third, 1)
    assert movie3["metadata"]["edition"] == 3
    assert movie3["metadata"]["parent_asset_ids"][0] == movie2["metadata"]["parent_asset_ids"][0]
    assert movie3["metadata"]["parent_asset_ids"][1] != movie2["metadata"]["parent_asset_ids"][1]
    enqueue_copy(store, pid, 1, ExportCopy(orientation="landscape"))
    copies = produce_until(store, Worker(store), pid)
    copy = next(a for a in copies["assets"] if a["role"] == "export-variant")
    assert copy["metadata"]["parent_asset_ids"] == [movie3["id"]]
    assert copies["canon"] == original["canon"]
    for a in original["assets"]:
        assert digest(store.asset_path(a["id"])[0]) == a["sha256"]
    frames = [a for a in copies["assets"] if a["role"] == "keyframe-revision"]
    original_frame = next(
        a for a in original["assets"] if a["role"] == "keyframe" and a["metadata"]["shot_id"] == sid
    )
    assert frames[0]["sha256"] != original_frame["sha256"]
    assert frames[0]["metadata"]["parent_asset_ids"] == original_frame["metadata"]["parent_asset_ids"]
    assert frames[0]["metadata"]["parent_hashes"] == original_frame["metadata"]["parent_hashes"]


def test_stale_api_validation_pause_discard_caps_and_busy(store, spec):
    spec.kind, spec.episodes = "series", 3
    pid, original = finish(store, spec)
    store.enqueue(pid, 2)
    original = produce_until(store, Worker(store), pid)
    sid = shot_id(original)
    url = f"/api/projects/{pid}/episodes/1/shots/{sid}/retake"
    with TestClient(create_app(store.root, run_worker=False)) as client:
        value = request_for(original).model_dump()
        assert client.post(url, json=value | {"path": "../evil"}).status_code == 422
        assert client.post(url, json=value | {"seed": -1}).status_code == 422
        assert client.post(url, json=value | {"revision": 99}).status_code == 409
        assert (
            client.post(
                url, json=value | {"source_export_id": "00000000-0000-0000-0000-000000000000"}
            ).status_code
            == 409
        )
        assert client.post(url, json=value | {"seed": 1}).status_code == 409
        assert client.post(url, json=value).status_code == 202
        assert client.post(f"/api/projects/{pid}/produce", json={"episode": 3}).status_code == 409
        assert client.post(f"/api/projects/{pid}/episodes/1/pause").status_code == 200
        paused = store.get(pid)
        assert paused["jobs"][0]["state"] == "PAUSED" and paused["jobs"][1]["state"] == "SUCCEEDED"
        assert client.post(f"/api/projects/{pid}/episodes/1/discard-retake").status_code == 200
        assert client.post(url, json=value).json()["reused"] is True
        assert (
            client.post(url, json=value | {"idempotency_key": "test-second-retake", "seed": 9}).status_code
            == 202
        )
        assert client.post(f"/api/projects/{pid}/episodes/1/cancel").status_code == 200
        assert client.post(f"/api/projects/{pid}/episodes/1/resume").status_code == 409
        assert client.post(f"/api/projects/{pid}/episodes/1/discard-retake").status_code == 200
        assert (
            client.post(url, json=value | {"idempotency_key": "test-third-retake", "seed": 10}).status_code
            == 409
        )
    result = store.get(pid)
    assert result["canon"] == original["canon"]
    assert result["jobs"][0]["state"] == "SUCCEEDED"
    assert all(s["state"] in {"SUCCEEDED", "SUPERSEDED"} for s in result["jobs"][0]["steps"])
    assert len([a for a in result["assets"] if a["role"] == "export-edition"]) == 0


@pytest.mark.parametrize("target", ["reference", "export", "soundtrack", "clip"])
def test_corrupted_inputs_block_retake_and_preserve_original(store, spec, target):
    pid, original = finish(store, spec)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    worker = Worker(store)
    if target in {"soundtrack", "clip"}:
        run_one(worker)
        run_one(worker)
    asset = next(a for a in original["assets"] if a["role"] == target)
    store.asset_path(asset["id"])[0].write_bytes(b"deliberately corrupted test input")
    step = worker.claim()
    with pytest.raises(RuntimeError, match="checksum changed"):
        worker.execute(step)
    assert latest_movie(store.get(pid), 1)["id"] == latest_movie(original, 1)["id"]


def test_revision_race_and_disk_guard_block_publication(store, spec, monkeypatch):
    pid, original = finish(store, spec)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    worker = Worker(store)
    step = worker.claim()
    with monkeypatch.context() as patch:
        patch.setattr("studio.shot_revisions.shutil.disk_usage", lambda _: type("Disk", (), {"free": 0})())
        with pytest.raises(RuntimeError, match="DISK_FULL"):
            worker.execute(step)
    output = worker.execute(step)
    with store.connect() as db:
        db.execute("UPDATE projects SET revision=revision+1 WHERE id=?", (pid,))
    with pytest.raises(RuntimeError, match="CANON_CONFLICT"):
        worker.complete(step, output)
    assert not any(a["role"] == "keyframe-revision" for a in store.get(pid)["assets"])


def test_lineage_metadata_cannot_replace_pinned_references(store, spec):
    pid, original = finish(store, spec)
    frame = next(a for a in original["assets"] if a["role"] == "keyframe")
    with store.connect() as db:
        metadata = frame["metadata"] | {"parent_hashes": ["0" * 64]}
        db.execute("UPDATE assets SET metadata=? WHERE id=?", (json.dumps(metadata), frame["id"]))
    with pytest.raises(ValueError, match="lineage checksums"):
        enqueue_retake(store, pid, 1, shot_id(original), request_for(original))


def test_partial_backup_resume_preserves_candidates_and_does_not_recommit_canon(store, spec, tmp_path):
    pid, original = finish(store, spec)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    worker = Worker(store)
    run_one(worker)
    run_one(worker)
    store.control(pid, "pause", 1)
    saved = store.get(pid)
    archive = tmp_path / "retakes.zip"
    create_backup(store, archive)
    restored = restore_backup(archive, tmp_path / "restored")
    assert restored.get(pid)["jobs"][0]["state"] == "PAUSED"
    restored.control(pid, "resume", 1)
    result = produce_until(restored, Worker(restored), pid)
    assert latest_movie(result, 1)["metadata"]["edition"] == 2
    assert result["canon"] == original["canon"]
    for a in saved["assets"]:
        assert digest(restored.asset_path(a["id"])[0]) == a["sha256"]


def test_discard_waits_for_atomic_step_and_retains_candidates(store, spec):
    pid, original = finish(store, spec)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    worker = Worker(store)
    step = worker.claim()
    store.control(pid, "pause", 1)
    with pytest.raises(ValueError, match="current step"):
        discard_retake(store, pid, 1)
    output = worker.execute(step)
    worker.complete(step, output)
    discard_retake(store, pid, 1)
    result = store.get(pid)
    assert any(a["role"] == "keyframe-revision" for a in result["assets"])
    assert latest_movie(result, 1)["id"] == latest_movie(original, 1)["id"]
    assert result["canon"] == original["canon"]


def test_recut_receipt_after_actual_child_kill(store, spec, tmp_path):
    pid, original = finish(store, spec)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    worker = Worker(store)
    run_one(worker)
    run_one(worker)
    marker = tmp_path / "recut-published"
    code = """
import os, time
from pathlib import Path
from studio.storage import Store, atomic_json
from studio.worker import Worker
w = Worker(Store(Path(os.environ['STUDIO_DATA'])))
s = w.claim()
assert s['stage'] == 'RECUT'
o = w.execute(s)
w.verify(o)
atomic_json(w.directory(s) / 'receipt.json', o)
Path(os.environ['RETAKE_MARKER']).write_text(s['id'])
while True: time.sleep(1)
"""
    with (tmp_path / "child.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            env=os.environ | {"STUDIO_DATA": str(store.root), "RETAKE_MARKER": str(marker)},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while not marker.exists():
                assert process.poll() is None, (tmp_path / "child.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(0.05)
            process.kill()
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    assert latest_movie(store.get(pid), 1)["id"] == latest_movie(original, 1)["id"]
    worker.recover()
    result = store.get(pid)
    assert latest_movie(result, 1)["metadata"]["edition"] == 2
    assert result["canon"] == original["canon"]
    assert result["jobs"][0]["state"] == "SUCCEEDED"
    assert all(digest(store.asset_path(a["id"])[0]) == a["sha256"] for a in original["assets"])


def test_native_dispatch_preserves_seed_references_and_never_falls_back_to_mock(store, spec, monkeypatch):
    # Only a dispatch contract test: no native model is loaded and no real generation is claimed.
    pid, original = finish(store, spec)
    movie = latest_movie(original, 1)
    with store.connect() as db:
        db.execute(
            "UPDATE projects SET spec=? WHERE id=?",
            (json.dumps(original["spec"] | {"backend": "local"}), pid),
        )
        db.execute(
            "UPDATE assets SET metadata=? WHERE id=?",
            (
                json.dumps(movie["metadata"] | {"is_mock": False, "provider": "TEST-CONTRACT-ONLY"}),
                movie["id"],
            ),
        )
    original = store.get(pid)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original, seed=11))
    worker = Worker(store)
    step = worker.claim()

    def image(_self, prompt, directory, size, check, references=None, seed=0):
        assert prompt == step["payload"]["prompt"] and seed == 11
        assert references == [store.asset_path(p["id"])[0] for p in step["payload"]["reference_inputs"]]
        raise RuntimeError("TEST_PROVIDER_UNAVAILABLE")

    monkeypatch.setattr("studio.shot_revisions.WanGPProvider.image", image)
    with pytest.raises(RuntimeError, match="TEST_PROVIDER_UNAVAILABLE"):
        worker.execute(step)
    assert latest_movie(store.get(pid), 1)["id"] == movie["id"]
    assert not any(a["role"] == "keyframe-revision" for a in store.get(pid)["assets"])
    # Register a conspicuous MOCK frame solely to test the video call boundary.
    path = worker.directory(step) / "test-mock.png"
    media.demo_image(path, (360, 640), "MOCK CONTRACT TEST", "MOCK", 11)
    worker.complete(
        step,
        {
            "artifacts": [
                worker.artifact(
                    step,
                    "keyframe-revision",
                    path,
                    {"is_mock": True, "provider": "TEST-CONTRACT-ONLY", "shot_id": shot_id(original)},
                )
            ]
        },
    )
    clip_step = worker.claim()

    def video(_self, prompt, source, directory, size, seconds, check, seed=0):
        assert prompt == step["payload"]["shot"]["action"] + ". " + step["payload"]["shot"]["camera"]
        assert source == path and size == (360, 640) and seconds == 5 and seed == 11
        raise RuntimeError("TEST_VIDEO_UNAVAILABLE")

    monkeypatch.setattr("studio.shot_revisions.WanGPProvider.video", video)
    with pytest.raises(RuntimeError, match="TEST_VIDEO_UNAVAILABLE"):
        worker.execute(clip_step)


def test_recut_keeps_actual_windows_voice_and_embedded_subtitles(store, spec):
    # Native Windows speech; the visual provider is explicitly MOCK.
    pid, _ = store.create(spec)
    store.enqueue(pid)
    original = produce_until(store, Worker(store), pid)
    assert latest_movie(original, 1)["metadata"]["dialogue_present"]
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    result = produce_until(store, Worker(store), pid)
    movie = latest_movie(result, 1)
    probe = media.validate_video(store.asset_path(movie["id"])[0], (360, 640), 5, audio=True)
    assert any(s["codec_name"] == "mov_text" for s in probe["streams"])
    old_srt = next(a for a in original["assets"] if a["role"] == "subtitles")
    new_srt = next(a for a in result["assets"] if a["role"] == "subtitles-edition")
    assert new_srt["sha256"] == old_srt["sha256"]
    assert result["canon"] == original["canon"]

    def audio_hash(asset):
        return media.run(
            [
                media.binary("ffmpeg"),
                "-v",
                "error",
                "-i",
                str(store.asset_path(asset["id"])[0]),
                "-map",
                "0:a",
                "-c",
                "copy",
                "-f",
                "hash",
                "-",
            ]
        )

    assert audio_hash(movie) == audio_hash(latest_movie(original, 1))


def test_failed_take_retry_budget_is_finite_and_discard_preserves_movie(store, spec, monkeypatch):
    pid, original = finish(store, spec)
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("TEST_IMAGE_UNAVAILABLE")

    monkeypatch.setattr(media, "demo_image", unavailable)
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
            take = next(s for s in store.get(pid)["jobs"][0]["steps"] if s["stage"] == "RETAKE_FRAME")
            assert take["attempts"] == attempt
        with pytest.raises(ValueError, match="Retry budget exhausted"):
            store.control(pid, "resume", 1)
        discard_retake(store, pid, 1)
        result = store.get(pid)
        assert latest_movie(result, 1)["id"] == latest_movie(original, 1)["id"]
        assert result["canon"] == original["canon"]
    finally:
        worker.close()
