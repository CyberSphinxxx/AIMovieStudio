import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.storage import digest
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


def rewrite(archive, destination, change):
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(destination, "w") as output:
        for name in source.namelist():
            content = source.read(name)
            if name == "studio.json":
                data = json.loads(content)
                change(data)
                content = json.dumps(data).encode()
            output.writestr(name, content)


def test_interrupted_backup_restore_preserves_hashes_and_can_resume(store, spec, tmp_path):
    spec.target_seconds = 10
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    result = produce_until(store, Worker(store), pid, "CLIP", 1)
    archive = create_backup(store, tmp_path / "original.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    copy = restored.get(pid)
    assert copy["status"] == "PAUSED"
    assert restored.settings()["wangp"] == {}
    with restored.connect() as db:
        assert db.execute("SELECT config FROM jobs").fetchone()[0] == "{}"
    assert {(a["id"], a["sha256"]) for a in result["assets"]} == {
        (a["id"], a["sha256"]) for a in copy["assets"]
    }
    for asset in copy["assets"]:
        assert digest(restored.asset_path(asset["id"])[0]) == asset["sha256"]
    set_silent(restored)
    restored.control(pid, "resume")
    with restored.connect() as db:
        assert json.loads(db.execute("SELECT config FROM jobs").fetchone()[0])["speech"] == "none"
        # Mid-job settings changes must not mutate the restored job's frozen config.
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"windows\"')")
    final = produce_until(restored, Worker(restored), pid)
    assert final["status"] == "COMPLETED"
    assert len([a for a in final["assets"] if a["role"] == "export"]) == 1
    assert next(a for a in final["assets"] if a["role"] == "export")["metadata"]["dialogue_present"] is False
    assert archive.exists()


def test_backup_download_and_existing_destination_protection(tmp_path, spec):
    app = create_app(tmp_path / "data", run_worker=False)
    app.state.store.create(spec)
    with TestClient(app) as client:
        response = client.get("/api/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert not list((app.state.store.root / "backups").glob("*.zip"))
    archive = tmp_path / "backup.zip"
    archive.write_bytes(response.content)
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("untouched")
    with pytest.raises(ValueError, match="existing data"):
        restore_backup(archive, destination)
    assert sentinel.read_text() == "untouched"
    with pytest.raises(ValueError, match="already exists"):
        create_backup(app.state.store, archive)


def test_hostile_archive_paths_and_configuration_are_not_executed(store, spec, tmp_path):
    pid, _ = store.create(spec)
    store.enqueue(pid)
    archive = create_backup(store, tmp_path / "safe.zip")
    bad = tmp_path / "unsafe.zip"
    rewrite(archive, bad, lambda d: d["tables"]["steps"][0].update(id="../../outside"))
    with pytest.raises(ValueError):
        restore_backup(bad, tmp_path / "bad-destination")
    assert not (tmp_path / "bad-destination").exists()
    assert not list(tmp_path.glob(".studio-restore-*"))
    rewrite(
        archive,
        bad,
        lambda d: d["tables"]["jobs"][0].update(config=json.dumps({"wangp": {"python": "evil.exe"}})),
    )
    restored = restore_backup(bad, tmp_path / "safe-destination")
    with restored.connect() as db:
        assert db.execute("SELECT config,state FROM jobs").fetchone()["state"] == "PAUSED"
        assert db.execute("SELECT config FROM jobs").fetchone()[0] == "{}"
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr("../outside.txt", "unsafe")
    with pytest.raises(ValueError, match="Unexpected"):
        restore_backup(archive, tmp_path / "foreign-destination")
    assert not (tmp_path / "outside.txt").exists()


def test_restore_rejects_changed_media(store, spec, tmp_path):
    pid, _ = store.create(spec)
    store.enqueue(pid)
    produce_until(store, Worker(store), pid, "REFERENCE", 1)
    archive = create_backup(store, tmp_path / "safe.zip")
    bad = tmp_path / "changed.zip"
    rewrite(archive, bad, lambda d: d["tables"]["assets"][0].update(sha256="0" * 64))
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_backup(bad, tmp_path / "changed-destination")
    assert not (tmp_path / "changed-destination").exists()
