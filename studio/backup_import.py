"""Restore missing projects into the current Library with a durable publish journal."""

import json
import os
import shutil
import time
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from studio.backup import (
    MAX_MANIFEST,
    TABLES,
    restore_backup,
    snapshot,
    validate_document,
    validate_zip_entries,
)
from studio.storage import Store, atomic_json, digest

RESERVE = 1024**3
MAX_UPLOAD = 20 * 1024**3


def operation_path(store: Store, identity: str) -> Path:
    if str(UUID(identity)) != identity:
        raise ValueError("Invalid restore identity")
    parent = store.root / "restore-imports"
    candidate = parent / identity
    if parent.resolve() != parent or candidate.resolve() != candidate:
        raise ValueError("Restore staging cannot use redirected folders")
    return store.resolve(f"restore-imports/{identity}")


def begin_upload(store: Store) -> tuple[str, Path]:
    identity = str(uuid4())
    path = operation_path(store, identity)
    path.mkdir(parents=True, exist_ok=False)
    return identity, path


def discard_unprepared(store: Store, identity: str):
    path = operation_path(store, identity)
    if (path / "receipt.json").exists():
        return False  # Prepared/published copies need journal recovery, not deletion.
    if path.exists():
        shutil.rmtree(path)
    return True


def discard_prepared(store: Store, identity: str):
    path = operation_path(store, identity)
    receipt = path / "receipt.json"
    if not receipt.exists():
        return discard_unprepared(store, identity)
    if receipt.stat().st_size > 8192:
        raise ValueError("Invalid restore journal")
    value = json.loads(receipt.read_text(encoding="utf-8"))
    if value.get("id") != identity or value.get("state") != "PREPARED":
        raise ValueError("Published restore copies must be resumed; files are preserved")
    with store.connect() as db:
        if _committed_result(db, identity):
            raise ValueError("This backup was already restored")
    shutil.rmtree(path)  # PREPARED precedes all publication; only staged copies exist here.
    return True


def _cleanup_staging(store: Store, path: Path):
    (path / "upload.zip").unlink(missing_ok=True)
    staging = (path / "store").resolve()
    if staging.parent != path or not staging.is_relative_to(store.root):
        raise RuntimeError("Unsafe restore staging cleanup target")
    if staging.exists():
        shutil.rmtree(staging)


def prepare_import(store: Store, identity: str):
    path = operation_path(store, identity)
    # Reject conflicts before allocating another extracted copy of a large archive.
    with zipfile.ZipFile(path / "upload.zip") as archive:
        validate_zip_entries(archive.infolist())
        if archive.getinfo("studio.json").file_size > MAX_MANIFEST:
            raise ValueError("Oversized backup manifest")
        document = json.loads(archive.read("studio.json"))
        validate_document(document)
    with store.connect() as db:
        for project in document["tables"]["projects"]:
            if db.execute(
                "SELECT 1 FROM projects WHERE id=? OR key=?", (project["id"], project["key"])
            ).fetchone():
                raise ValueError(
                    "A project from this backup already exists. Existing projects were left unchanged."
                )
            if store.resolve(project["id"]).exists():
                raise ValueError(
                    "A project folder already exists. Resume its unfinished restore from Settings."
                )
    del document  # Release the preview before the extractor parses a large manifest.
    restored = restore_backup(path / "upload.zip", path / "store")
    data = snapshot(restored)
    if not data["tables"]["projects"]:
        raise ValueError("This backup has no projects to restore")
    # Compact immutable manifest; fsync before announcing a resumable operation.
    document = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(document) > MAX_MANIFEST:
        raise ValueError("Restore manifest exceeds its memory limit")
    manifest = path / "import.json"
    with manifest.open("xb") as file:
        file.write(document)
        file.flush()
        os.fsync(file.fileno())
    atomic_json(
        path / "receipt.json",
        {
            "id": identity,
            "state": "PREPARED",
            "created": time.time(),
            "manifest_sha256": digest(manifest),
            "project_count": len(data["tables"]["projects"]),
            "titles": [p["title"][:120] for p in data["tables"]["projects"][:3]],
        },
    )


def _committed_result(db, identity: str):
    for row in db.execute("SELECT data FROM events WHERE kind='backup_restored'"):
        data = json.loads(row["data"])
        if data.get("operation_id") == identity:
            return data
    return None


def _publish_project(source: Path, target: Path):
    # Intent marker already flushed in source; rename publishes the whole directory.
    os.rename(source, target)


def _reject_identity_conflicts(db, tables):
    for table in ("episodes", "jobs", "steps", "assets", "canon"):
        identities = [row["id"] for row in tables[table]]
        for offset in range(0, len(identities), 500):
            batch = identities[offset : offset + 500]
            placeholders = ",".join("?" for _ in batch)
            if db.execute(f"SELECT 1 FROM {table} WHERE id IN ({placeholders}) LIMIT 1", batch).fetchone():
                raise ValueError(
                    "A saved identity from this backup already exists. Existing data was left unchanged."
                )


def commit_import(store: Store, identity: str) -> dict:
    path = operation_path(store, identity)
    with store.connect() as db:
        completed = _committed_result(db, identity)
    if completed:
        _cleanup_staging(store, path)
        return completed  # DB commit is authoritative even if journal update was interrupted.
    receipt_path, manifest = path / "receipt.json", path / "import.json"
    if not receipt_path.is_file():
        raise KeyError(identity)
    if receipt_path.stat().st_size > 8192 or manifest.stat().st_size > MAX_MANIFEST:
        raise ValueError("Invalid restore journal size")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["id"] != identity or digest(manifest) != receipt["manifest_sha256"]:
        raise ValueError("Restore journal checksum changed; keep the original backup")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    validate_document(data)
    tables = data["tables"]
    projects = tables["projects"]
    if not projects:
        raise ValueError("This backup has no projects")
    marker_name = ".restore-owner.json"
    # Recheck media on explicit resume, including projects already published before a kill.
    for asset in tables["assets"]:
        target = store.resolve(asset["path"])
        source = (path / "store" / asset["path"]).resolve()
        if not source.is_relative_to(path / "store"):
            raise ValueError("Restore media escaped staging")
        media = target if (store.resolve(asset["project_id"]) / marker_name).is_file() else source
        if not media.is_file() or digest(media) != asset["sha256"]:
            raise ValueError("Restore media is missing or changed; keep the original backup")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        completed = _committed_result(db, identity)
        if completed:
            return completed
        _reject_identity_conflicts(db, tables)
        for project in projects:
            if db.execute(
                "SELECT 1 FROM projects WHERE id=? OR key=?", (project["id"], project["key"])
            ).fetchone():
                raise ValueError(
                    "A project from this backup already exists. Existing projects were left unchanged."
                )
            target = store.resolve(project["id"])
            if target.exists():
                marker = target / marker_name
                if not marker.is_file() or marker.read_text(encoding="utf-8") != identity:
                    raise ValueError("A project folder already exists. Existing files were left unchanged.")
        receipt["state"] = "PUBLISHING"
        atomic_json(receipt_path, receipt)
        for project in projects:
            source, target = path / "store" / project["id"], store.resolve(project["id"])
            if target.exists():
                continue  # Only this operation's already-published directory was accepted above.
            source.mkdir(exist_ok=True)
            marker = source / marker_name
            with marker.open("w", encoding="utf-8") as file:
                file.write(identity)
                file.flush()
                os.fsync(file.fileno())
            _publish_project(source, target)
        for table, fields in TABLES.items():
            columns = fields.split()
            if table == "events":
                columns.remove("seq")  # Current studio's SSE cursor stays monotonic and unique.
            for row in tables[table]:
                if table == "events" and row["kind"] == "backup_restored":
                    # Imported history must not forge a live operation's commit marker.
                    row = row | {"kind": "historical_backup_restored"}
                db.execute(
                    f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                    [row[c] for c in columns],
                )
        result = {
            "operation_id": identity,
            "project_ids": [p["id"] for p in projects],
            "project_count": len(projects),
            "paused_jobs": sum(j["state"] == "PAUSED" for j in tables["jobs"]),
        }
        store.event(db, projects[0]["id"], None, "backup_restored", result)
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Restored data failed relationship checks")
    receipt["state"] = "COMPLETED"
    atomic_json(receipt_path, receipt)
    # Uploaded and extracted copies are app-owned staging. Published projects stay intact.
    _cleanup_staging(store, path)
    return result


def pending_imports(store: Store, active: set[str] | None = None) -> list[dict]:
    parent = store.resolve("restore-imports")
    if not parent.exists():
        return []
    with store.connect() as db:
        committed = {
            json.loads(row["data"])["operation_id"]
            for row in db.execute("SELECT data FROM events WHERE kind='backup_restored'")
        }
    result = []
    for directory in parent.iterdir():
        try:
            path = operation_path(store, directory.name) / "receipt.json"
            if directory.name in committed or directory.name in (active or set()):
                continue
            if not path.is_file():
                result.append(
                    {
                        "id": directory.name,
                        "state": "INCOMPLETE_UPLOAD",
                        "created": directory.stat().st_mtime,
                        "project_count": 0,
                    }
                )
                continue
            if path.stat().st_size > 8192:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if value["id"] != directory.name or value["state"] not in {"PREPARED", "PUBLISHING"}:
                continue
            result.append({k: value[k] for k in ("id", "state", "created", "project_count")})
            result[-1]["titles"] = value.get("titles", [])
        except (ValueError, KeyError, OSError):
            continue
    return sorted(result, key=lambda r: r["created"], reverse=True)[:20]
