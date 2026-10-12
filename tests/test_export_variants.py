from concurrent.futures import ThreadPoolExecutor
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
from studio.storage import atomic_json, digest
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


def finish(store, spec):
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    return pid, produce_until(store, Worker(store), pid)


def test_copy_duplicate_atomic_recovery_and_backup(store, spec, tmp_path):
    pid, original = finish(store, spec)
    hashes = {a["id"]: a["sha256"] for a in original["assets"]}
    request = ExportCopy(orientation="landscape")
    with ThreadPoolExecutor(4) as pool:
        requests = list(pool.map(lambda _: enqueue_copy(store, pid, 1, request), range(8)))
    assert len({r["step_id"] for r in requests}) == 1
    assert sum(not r["reused"] for r in requests) == 1
    worker = Worker(store)
    step = worker.claim()
    assert step["stage"] == "REFORMAT"
    output = worker.execute(step)
    atomic_json(worker.directory(step) / "receipt.json", output)
    # Simulated publication/DB-commit interruption: no duplicate conversion.
    worker.recover()
    result = store.get(pid)
    assert result["status"] == "COMPLETED"
    assert result["canon"] == original["canon"]
    assert result["episodes"] == original["episodes"]
    for aid, sha in hashes.items():
        assert digest(store.asset_path(aid)[0]) == sha
    copy = next(a for a in result["assets"] if a["role"] == "export-variant")
    probe = media.validate_video(store.asset_path(copy["id"])[0], (640, 360), 5, audio=True)
    assert probe["streams"][0]["sample_aspect_ratio"] == "1:1"
    assert copy["metadata"]["is_mock"] is True
    assert copy["metadata"]["reframe"] == "fit with black bars"
    assert enqueue_copy(store, pid, 1, request)["state"] == "SUCCEEDED"
    enqueue_copy(store, pid, 1, ExportCopy(orientation="square"))
    archive = tmp_path / "copy.zip"
    create_backup(store, archive)
    restored = restore_backup(archive, tmp_path / "restored")
    assert restored.get(pid)["jobs"][0]["state"] == "PAUSED"
    restored.control(pid, "resume")
    finished = produce_until(restored, Worker(restored), pid)
    assert len([a for a in finished["assets"] if a["role"] == "export-variant"]) == 2
    assert finished["canon"] == original["canon"]


def test_copy_api_validation_and_source_integrity(store, spec):
    pid, result = finish(store, spec)
    app = create_app(store.root, run_worker=False)
    url = f"/api/projects/{pid}/episodes/1/export-copy"
    with TestClient(app) as client:
        assert client.post(url, json={"orientation": "crop"}).status_code == 422
        assert client.post(url, json={"orientation": "landscape", "path": "../evil"}).status_code == 422
        assert client.post(url.replace("/1/", "/2/"), json={"orientation": "landscape"}).status_code == 409
        same = client.post(url, json={"orientation": "portrait"})
        assert same.status_code == 202 and same.json()["asset_id"]
        assert client.post(url, json={"orientation": "landscape"}).status_code == 202
    source = next(a for a in result["assets"] if a["role"] == "export")
    store.asset_path(source["id"])[0].write_bytes(b"corrupted original test fixture")
    with pytest.raises(RuntimeError, match="checksum changed"):
        Worker(store).execute(Worker(store).claim())


def test_copy_requires_complete_idle_production(store, spec):
    pid, _ = store.create(spec)
    store.enqueue(pid)
    with pytest.raises(ValueError, match="Finish this episode"):
        enqueue_copy(store, pid, 1, ExportCopy(orientation="landscape"))
    set_silent(store)
    produce_until(store, Worker(store), pid)
    enqueue_copy(store, pid, 1, ExportCopy(orientation="landscape"))
    with pytest.raises(ValueError, match="resolve stopped production"):
        enqueue_copy(store, pid, 1, ExportCopy(orientation="square"))


def test_copy_after_hard_kill_retains_original_and_recovers_receipt(store, spec, tmp_path):
    pid, original = finish(store, spec)
    enqueue_copy(store, pid, 1, ExportCopy(orientation="landscape"))
    marker = tmp_path / "published"
    code = """
import os, time
from pathlib import Path
from studio.storage import Store, atomic_json
from studio.worker import Worker
w = Worker(Store(Path(os.environ['STUDIO_DATA'])))
s = w.claim()
o = w.execute(s)
w.verify(o)
atomic_json(w.directory(s) / 'receipt.json', o)
Path(os.environ['COPY_MARKER']).write_text(s['id'])
while True: time.sleep(1)
"""
    with (tmp_path / "worker.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            env=os.environ | {"STUDIO_DATA": str(store.root), "COPY_MARKER": str(marker)},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
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
    recovery = Worker(store)
    recovery.recover()
    result = store.get(pid)
    assert result["jobs"][0]["state"] == "SUCCEEDED"
    assert result["canon"] == original["canon"]
    assert len([a for a in result["assets"] if a["role"] == "export-variant"]) == 1
    assert all(digest(store.asset_path(a["id"])[0]) == a["sha256"] for a in original["assets"])


def test_reformat_keeps_embedded_subtitles_and_audio(tmp_path):
    source, output = tmp_path / "source.mp4", tmp_path / "copy.mp4"
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nAn original caption.\n", encoding="utf-8")
    media.run(
        [
            media.binary("ffmpeg"),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=640x360:r=24:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-i",
            str(subtitles),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            str(source),
        ]
    )
    media.reformat(source, output, (360, 640), lambda: None)
    probe = media.validate_video(output, (360, 640), 1, audio=True)
    assert any(s["codec_name"] == "mov_text" for s in probe["streams"])
    extracted = media.run(
        [media.binary("ffmpeg"), "-v", "error", "-i", str(output), "-map", "0:s", "-f", "srt", "-"]
    )
    assert b"An original caption." in extracted

    def audio_hash(path):
        return media.run(
            [
                media.binary("ffmpeg"),
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:a",
                "-c",
                "copy",
                "-f",
                "hash",
                "-",
            ]
        )

    assert audio_hash(source) == audio_hash(output)
    # Black bars retain the full center image in the portrait copy.
    frame = media.run(
        [
            media.binary("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
    )
    assert max(frame[: 360 * 3]) <= 5
    center = (320 * 360 + 180) * 3
    assert frame[center + 2] > 200
