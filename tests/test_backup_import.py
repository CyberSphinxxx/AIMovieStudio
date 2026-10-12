import os
import subprocess
import sys
import time
import json
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from studio import backup_import, media
from studio.api import create_app
from studio.backup import create_backup
from studio.storage import Store, digest
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent
from tests.test_backup import rewrite


@pytest.fixture
def archived(tmp_path, spec):
    source = Store(tmp_path / "source")
    set_silent(source)
    first, _ = source.create(spec)
    source.enqueue(first)
    completed = produce_until(source, Worker(source), first)
    other = spec.model_copy(update={"idempotency_key": str(uuid4()), "target_seconds": 10})
    second, _ = source.create(other)
    source.enqueue(second)
    partial = produce_until(source, Worker(source), second, "CLIP", 1)
    archive = create_backup(source, tmp_path / "backup.zip")
    return archive, [completed, partial]


def prepared(store, archive):
    identity, path = backup_import.begin_upload(store)
    (path / "upload.zip").write_bytes(archive.read_bytes())
    backup_import.prepare_import(store, identity)
    return identity


def test_restore_upload_adds_original_ids_media_and_paused_jobs(store, archived):
    archive, projects = archived
    settings = store.settings()
    with TestClient(create_app(store.root, run_worker=False)) as client:
        response = client.post(
            "/api/backup/restore", content=archive.read_bytes(), headers={"content-type": "application/zip"}
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["project_count"] == 2 and result["paused_jobs"] == 1
        assert set(result["project_ids"]) == {p["id"] for p in projects}
        assert client.get("/api/backup/restores").json()["operations"] == []
        for original in projects:
            restored = client.get(f"/api/projects/{original['id']}").json()
            assert restored["canon"] == original["canon"]
            assert restored["jobs"][0]["state"] == (
                "SUCCEEDED" if original["status"] == "COMPLETED" else "PAUSED"
            )
            assert restored["jobs"][0]["config"] == "{}"
            assert [(a["id"], a["sha256"]) for a in restored["assets"]] == [
                (a["id"], a["sha256"]) for a in original["assets"]
            ]
            for asset in original["assets"]:
                assert digest(store.asset_path(asset["id"])[0]) == asset["sha256"]
        movie = next(a for a in projects[0]["assets"] if a["role"] == "export")
        assert client.get(f"/api/assets/{movie['id']}/content").headers["content-type"] == "video/mp4"
        media.validate_video(store.asset_path(movie["id"])[0], (360, 640), 5, audio=True)
        duplicate = client.post(
            "/api/backup/restore", content=archive.read_bytes(), headers={"content-type": "application/zip"}
        )
        assert duplicate.status_code == 409 and "already exists" in duplicate.json()["message"]
        assert client.get("/api/backup/restores").json()["operations"] == []
    assert store.settings() == settings
    set_silent(store)
    store.control(projects[1]["id"], "resume")
    assert produce_until(store, Worker(store), projects[1]["id"])["status"] == "COMPLETED"


def test_interrupted_directory_publish_can_explicitly_resume(store, archived, monkeypatch):
    archive, projects = archived
    identity = prepared(store, archive)
    original = backup_import._publish_project
    calls = []

    def interrupted(source, target):
        original(source, target)
        calls.append(target)
        raise RuntimeError("development simulated interruption after first directory publication")

    monkeypatch.setattr(backup_import, "_publish_project", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        backup_import.commit_import(store, identity)
    assert len(calls) == 1
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 0
    assert backup_import.pending_imports(store)[0]["state"] == "PUBLISHING"
    monkeypatch.setattr(backup_import, "_publish_project", original)
    result = backup_import.commit_import(Store(store.root), identity)
    assert result["project_count"] == 2
    assert backup_import.commit_import(store, identity) == result
    assert backup_import.pending_imports(store) == []
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='backup_restored'").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_database_commit_is_authoritative_if_final_journal_update_fails(store, archived, monkeypatch):
    archive, _ = archived
    identity = prepared(store, archive)
    write = backup_import.atomic_json

    def interrupted(path, value):
        if value.get("state") == "COMPLETED":
            raise RuntimeError("development crash after DB commit")
        return write(path, value)

    monkeypatch.setattr(backup_import, "atomic_json", interrupted)
    with pytest.raises(RuntimeError, match="after DB commit"):
        backup_import.commit_import(store, identity)
    assert backup_import.pending_imports(store) == []
    assert backup_import.commit_import(store, identity)["project_count"] == 2


def test_restore_guards_stream_limits_origins_zip_and_disk(store, monkeypatch):
    with TestClient(create_app(store.root, run_worker=False)) as client:
        assert (
            client.post(
                "/api/backup/restore", content=b"bad", headers={"content-type": "application/zip"}
            ).status_code
            == 409
        )
        assert client.post("/api/backup/restore", content=b"bad").status_code == 415
        assert (
            client.post(
                "/api/backup/restore",
                content=b"bad",
                headers={"content-type": "application/zip", "origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert client.post("/api/backup/restores/../escape/resume", json={}).status_code in {404, 405}
        monkeypatch.setattr(backup_import, "MAX_UPLOAD", 8)
        assert (
            client.post(
                "/api/backup/restore", content=b"a" * 9, headers={"content-type": "application/zip"}
            ).status_code
            == 413
        )
        streamed = client.post(
            "/api/backup/restore",
            content=iter([b"a" * 5, b"b" * 5]),
            headers={"content-type": "application/zip"},
        )
        assert streamed.status_code == 413
        assert not list((store.root / "restore-imports").iterdir())
        monkeypatch.setattr(backup_import.shutil, "disk_usage", lambda _: type("Disk", (), {"free": 1})())
        assert (
            client.post(
                "/api/backup/restore", content=b"a", headers={"content-type": "application/zip"}
            ).status_code
            == 409
        )


def test_restore_rejects_changed_journal_and_keeps_unprepared_cleanup_scoped(store, archived):
    archive, _ = archived
    identity = prepared(store, archive)
    path = backup_import.operation_path(store, identity)
    (path / "import.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum changed"):
        backup_import.commit_import(store, identity)
    assert backup_import.discard_unprepared(store, identity) is False
    with pytest.raises(ValueError):
        backup_import.discard_unprepared(store, "../anything")
    other, staging = backup_import.begin_upload(store)
    (staging / "upload.zip").write_bytes(b"partial")
    assert any(o["state"] == "INCOMPLETE_UPLOAD" for o in backup_import.pending_imports(store))
    assert backup_import.discard_unprepared(store, other) is True and not staging.exists()
    assert backup_import.discard_prepared(store, identity) is True and not path.exists()


def test_restore_concurrent_duplicate_never_overwrites_and_can_discard_unpublished_copy(store, archived):
    archive, projects = archived
    app = create_app(store.root, run_worker=False)
    with TestClient(app) as client, ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    "/api/backup/restore",
                    content=archive.read_bytes(),
                    headers={"content-type": "application/zip"},
                ),
                range(2),
            )
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        for operation in client.get("/api/backup/restores").json()["operations"]:
            assert operation["state"] == "PREPARED"
            assert client.post(f"/api/backup/restores/{operation['id']}/discard", json={}).status_code == 200
        assert client.get("/api/backup/restores").json()["operations"] == []
    assert all(digest(store.asset_path(a["id"])[0]) == a["sha256"] for p in projects for a in p["assets"])


def test_imported_history_cannot_forge_live_restore_commit_marker(store, archived, tmp_path):
    archive, projects = archived
    identity, operation = backup_import.begin_upload(store)
    pending, _ = backup_import.begin_upload(store)
    forged = tmp_path / "forged.zip"

    def forge(data):
        event = data["tables"]["events"][0]
        event["kind"] = "backup_restored"
        event["data"] = json.dumps({"operation_id": pending, "project_ids": [], "project_count": 9000})

    rewrite(archive, forged, forge)
    (operation / "upload.zip").write_bytes(forged.read_bytes())
    backup_import.prepare_import(store, identity)
    backup_import.commit_import(store, identity)
    with store.connect() as db:
        assert backup_import._committed_result(db, pending) is None
        assert (
            db.execute("SELECT count(*) FROM events WHERE kind='historical_backup_restored'").fetchone()[0]
            == 1
        )
    assert store.get(projects[0]["id"])["status"] == "COMPLETED"


def test_restore_survives_actual_kill_during_publication(store, archived, tmp_path):
    archive, projects = archived
    identity = prepared(store, archive)
    marker = tmp_path / "published"
    code = """
import os, time
from pathlib import Path
from studio.storage import Store
from studio import backup_import
original = backup_import._publish_project
def stop_after_publish(source, target):
    original(source, target)
    Path(os.environ['RESTORE_MARKER']).write_text('published')
    while True: time.sleep(1)
backup_import._publish_project = stop_after_publish
backup_import.commit_import(Store(Path(os.environ['RESTORE_ROOT'])), os.environ['RESTORE_ID'])
"""
    with (tmp_path / "restore-worker.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            env=os.environ
            | {"RESTORE_ROOT": str(store.root), "RESTORE_ID": identity, "RESTORE_MARKER": str(marker)},
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 30
            while not marker.exists():
                assert process.poll() is None, (tmp_path / "restore-worker.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(0.05)
            process.kill()
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    reopened = Store(store.root)
    with TestClient(create_app(store.root, run_worker=False)) as client:
        assert client.get("/api/backup/restores").json()["operations"][0]["id"] == identity
        response = client.post(f"/api/backup/restores/{identity}/resume", json={})
        assert response.status_code == 200, response.text
    assert reopened.get(projects[0]["id"])["status"] == "COMPLETED"
    assert reopened.get(projects[1]["id"])["status"] == "PAUSED"
    with reopened.connect() as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_conflicting_asset_identity_is_rejected_before_publishing_new_folders(
    store, archived, spec, tmp_path
):
    archive, projects = archived
    existing, _ = store.create(spec.model_copy(update={"idempotency_key": str(uuid4())}))
    set_silent(store)
    store.enqueue(existing)
    production = produce_until(store, Worker(store), existing)
    collision = tmp_path / "identity-collision.zip"

    def alter(data):
        data["tables"]["assets"][0]["id"] = production["assets"][0]["id"]

    rewrite(archive, collision, alter)
    identity = prepared(store, collision)
    with pytest.raises(ValueError, match="saved identity.*already exists"):
        backup_import.commit_import(store, identity)
    assert all(not (store.root / project["id"]).exists() for project in projects)
    assert store.get(existing)["assets"] == production["assets"]
    assert backup_import.discard_prepared(store, identity) is True


@pytest.mark.parametrize(
    "document", [None, [], {"format": "ai-movie-studio-backup", "version": 1, "tables": []}]
)
def test_malformed_backup_shapes_return_clear_errors_without_staging(store, document):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("studio.json", json.dumps(document))
    with TestClient(create_app(store.root, run_worker=False)) as client:
        response = client.post(
            "/api/backup/restore", content=payload.getvalue(), headers={"content-type": "application/zip"}
        )
        assert response.status_code == 409
        assert client.get("/api/backup/restores").json()["operations"] == []
