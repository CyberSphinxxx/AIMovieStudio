import json
import os
import shutil

import pytest

from studio import media
from studio.storage import Store, atomic_json, digest
from studio.worker import Worker


def produce_until(store, worker, pid, stop_stage=None, stop_count=0):
    count = 0
    while True:
        step = worker.claim()
        if not step:
            break
        output = worker.execute(step)
        worker.verify(output)
        atomic_json(worker.directory(step) / "receipt.json", output)
        worker.complete(step, output)
        if step["stage"] == stop_stage:
            count += 1
            if count >= stop_count:
                break
    return store.get(pid)


def set_silent(store):
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")


@pytest.mark.parametrize("orientation,seconds", [("portrait", 30), ("landscape", 60), ("square", 5)])
def test_full_media_flow(store, spec, orientation, seconds):
    spec.orientation, spec.target_seconds, spec.kind = orientation, seconds, "drama"
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    result = produce_until(store, Worker(store), pid)
    assert result["status"] == "COMPLETED"
    assert len(result["canon"]) == 1
    movie = next(a for a in result["assets"] if a["role"] == "export")
    assert movie["metadata"]["is_mock"]
    output = store.asset_path(movie["id"])[0]
    media.validate_video(output, media.SIZES[orientation], seconds, audio=True)
    manifest = next(a for a in result["assets"] if a["role"] == "manifest")
    data = json.loads(store.asset_path(manifest["id"])[0].read_text(encoding="utf-8"))
    assert len(data["edit_decision_list"]) == len([a for a in result["assets"] if a["role"] == "clip"])


def test_checkpoint_recovery_and_series_reuse(store, spec):
    spec.kind, spec.episodes = "series", 6
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    partial = produce_until(store, worker, pid, "CLIP", 1)
    original = {a["id"]: a["sha256"] for a in partial["assets"]}
    # Reopen storage, simulate a crash after publication but before transaction commit.
    nextstep = worker.claim()
    output = worker.execute(nextstep)
    atomic_json(worker.directory(nextstep) / "receipt.json", output)
    reopened = Store(store.root)
    recovery = Worker(reopened)
    recovery.recover()
    finished = produce_until(reopened, recovery, pid)
    assert finished["status"] == "COMPLETED"
    assert all(
        next(a for a in finished["assets"] if a["id"] == aid)["sha256"] == sha
        for aid, sha in original.items()
    )
    ref_ids = {a["id"] for a in finished["assets"] if a["role"] == "reference"}
    reopened.enqueue(pid, 2)
    episode2 = produce_until(reopened, recovery, pid)
    assert len(episode2["canon"]) == 2
    assert ref_ids == {a["id"] for a in episode2["assets"] if a["role"] == "reference"}
    assert finished["canon"][0]["value"] in episode2["episodes"][1]["script"]["screenplay"]


def test_exclusive_worker_lock(store):
    first = Worker(store)
    first.start()
    try:
        with pytest.raises(RuntimeError, match="Another Studio"):
            Worker(store).start()
    finally:
        first.close()


def test_corruption_rejected(tmp_path):
    path = tmp_path / "corrupt.mp4"
    path.write_bytes(b"broken mp4")
    with pytest.raises(RuntimeError):
        media.validate_video(path, (360, 640), 5)


def test_checksum_and_disk_reserve(store, spec, monkeypatch):
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    step = worker.claim()
    usage = shutil.disk_usage(store.root)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: type(usage)(usage.total, usage.total, 0))
    with pytest.raises(RuntimeError, match="DISK_FULL"):
        worker.execute(step)
    path = store.root / "test.bin"
    path.write_bytes(b"old")
    receipt = {"artifacts": [{"path": "test.bin", "sha256": digest(path)}]}
    path.write_bytes(b"new")
    with pytest.raises(RuntimeError, match="checksum"):
        worker.verify(receipt)


def test_retry_budget(store, spec):
    pid, _ = store.create(spec)
    jid = store.enqueue(pid)
    with store.connect() as db:
        db.execute("UPDATE jobs SET state='FAILED' WHERE id=?", (jid,))
        db.execute("UPDATE steps SET state='FAILED',attempts=max_attempts WHERE job_id=?", (jid,))
    with pytest.raises(ValueError, match="exhausted"):
        store.control(pid, "resume")


@pytest.mark.skipif(
    os.name != "nt", reason="Installed Windows SAPI voices required; separate real speech check"
)
def test_real_windows_speech_and_subtitles(store, spec):
    pid, _ = store.create(spec)
    store.enqueue(pid)
    result = produce_until(store, Worker(store), pid)
    audio = next(a for a in result["assets"] if a["role"] == "soundtrack")
    assert audio["metadata"]["provider"] == "windows-speech+synthetic-ambience"
    assert not audio["metadata"]["is_mock"]
    timeline = audio["metadata"]["timeline"]
    assert timeline[0]["start"] == 0 and 0 < timeline[0]["end"] <= 5
    movie = next(a for a in result["assets"] if a["role"] == "export")
    result = media.probe(store.asset_path(movie["id"])[0])
    assert any(s["codec_type"] == "subtitle" for s in result["streams"])
