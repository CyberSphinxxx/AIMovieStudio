"""Portable data archives. Restore creates a new folder and never executes imported jobs."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from uuid import UUID

from studio.domain import EpisodeOutline, EpisodeScript, ProjectInput, SeasonPlan
from studio.storage import Store, digest

TABLES = {
    "projects": "id key spec title status revision plan created updated",
    "episodes": "id project_id number outline script status",
    "jobs": "id project_id episode state error created config",
    "steps": "id job_id ordinal stage payload state attempts max_attempts heartbeat output error",
    "assets": "id project_id step_id role path sha256 metadata",
    "events": "seq job_id project_id kind data created",
    "canon": "id project_id entity_id episode field value reason revision",
}
MAX_FILES = 100000
MAX_MANIFEST = 64 * 1024**2
MAX_EXPANDED = 20 * 1024**3


def media_name(relative: str) -> str:
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if len(parts) != 4 or any(p in {".", ".."} for p in parts):
        raise ValueError("Unsafe archive media path")
    for identity in parts[:3]:
        if str(UUID(identity)) != identity:
            raise ValueError("Unsafe archive media identity")
    if ":" in parts[-1] or not parts[-1] or parts[-1].endswith((".", " ")):
        raise ValueError("Unsafe archive filename")
    return "media/" + "/".join(parts)


def snapshot(store: Store) -> dict:
    with store.connect() as db:
        db.execute("BEGIN")
        tables = {
            table: [dict(row) for row in db.execute(f"SELECT {', '.join(fields.split())} FROM {table}")]
            for table, fields in TABLES.items()
        }
    # Machine-specific commands/configuration are deliberately not portable.
    for job in tables["jobs"]:
        job["config"] = "{}"
    return {"format": "ai-movie-studio-backup", "version": 1, "created": time.time(), "tables": tables}


def create_backup(store: Store, destination: Path) -> Path:
    if destination.exists():
        raise ValueError("Backup destination already exists")
    data = snapshot(store)
    document = json.dumps(data, ensure_ascii=False).encode("utf-8")
    assets = data["tables"]["assets"]
    if len(document) > MAX_MANIFEST or len(assets) > MAX_FILES:
        raise ValueError("Backup exceeds archive limits")
    paths = [(media_name(a["path"]), store.resolve(a["path"]), a["sha256"]) for a in assets]
    total = len(document) + sum(path.stat().st_size for _, path, _ in paths)
    if total > MAX_EXPANDED:
        raise ValueError("Backup exceeds 20 GB limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < total + 1024**3:
        raise ValueError("Backup requires space for all saved media plus a 1 GB reserve")
    with tempfile.NamedTemporaryFile(
        prefix=".studio-backup-", suffix=".partial", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("studio.json", document)
            for name, path, sha in paths:
                if digest(path) != sha:
                    raise ValueError("Backup source checksum changed")
                archive.write(path, name)
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        # Exclusive publication also refuses a destination created during the backup.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def validate_document(data):
    if data.get("format") != "ai-movie-studio-backup" or data.get("version") != 1:
        raise ValueError("Unsupported backup format")
    if set(data.get("tables", {})) != set(TABLES):
        raise ValueError("Backup table inventory does not match")
    for table, fields in TABLES.items():
        rows = data["tables"][table]
        if not isinstance(rows, list) or len(rows) > MAX_FILES:
            raise ValueError("Backup row limit exceeded")
        for row in rows:
            if set(row) != set(fields.split()):
                raise ValueError("Invalid backup fields")
            if any(not isinstance(v, (str, int, float, type(None))) for v in row.values()):
                raise ValueError("Invalid backup field type")
    for project in data["tables"]["projects"]:
        if str(UUID(project["id"])) != project["id"]:
            raise ValueError("Invalid project identity")
        ProjectInput.model_validate_json(project["spec"])
        if project["plan"]:
            SeasonPlan.model_validate_json(project["plan"])
    for table in ("jobs", "steps"):
        for row in data["tables"][table]:
            if str(UUID(row["id"])) != row["id"]:
                raise ValueError("Invalid job/step identity")
    steps = {s["id"]: s for s in data["tables"]["steps"]}
    for asset in data["tables"]["assets"]:
        name = media_name(asset["path"])
        parts = PurePosixPath(name).parts
        if parts[1] != asset["project_id"] or parts[3] != asset["step_id"]:
            raise ValueError("Media ownership mismatch")
        if asset["step_id"] not in steps or parts[2] != steps[asset["step_id"]]["job_id"]:
            raise ValueError("Media job mismatch")
    for episode in data["tables"]["episodes"]:
        EpisodeOutline.model_validate_json(episode["outline"])
        if episode["script"]:
            EpisodeScript.model_validate_json(episode["script"])
    for step in data["tables"]["steps"]:
        if step["stage"] not in {"PLAN", "DRAFT", "SCRIPT", "REFERENCE", "FRAME", "CLIP", "AUDIO", "EXPORT"}:
            raise ValueError("Unknown restored stage")
        json.loads(step["payload"])
        if not 0 <= step["attempts"] <= step["max_attempts"] <= 3:
            raise ValueError("Invalid restored retry budget")


def restore_backup(source: Path, destination: Path) -> Store:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Restore requires a new folder; existing data is never overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".studio-restore-", dir=destination.parent)).resolve()
    try:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
                raise ValueError("Duplicate or excessive archive entries")
            if "studio.json" not in names or archive.getinfo("studio.json").file_size > MAX_MANIFEST:
                raise ValueError("Missing or oversized backup manifest")
            total = sum(e.file_size for e in entries)
            if total > MAX_EXPANDED or shutil.disk_usage(staging).free < total + 1024**3:
                raise ValueError("Restore exceeds size or free disk limits")
            data = json.loads(archive.read("studio.json"))
            validate_document(data)
            assets = data["tables"]["assets"]
            if set(names) != {"studio.json"} | {media_name(a["path"]) for a in assets}:
                raise ValueError("Unexpected archive files")
            store = Store(staging)
            for asset in assets:
                name = media_name(asset["path"])
                path = store.resolve(name.removeprefix("media/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as incoming, path.open("xb") as output:
                    shutil.copyfileobj(incoming, output, 1024**2)
                if digest(path) != asset["sha256"]:
                    raise ValueError("Restored media checksum mismatch")
                asset["path"] = name.removeprefix("media/")
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                for table, fields in TABLES.items():
                    columns = fields.split()
                    for row in data["tables"][table]:
                        if table == "jobs":
                            row["config"] = "{}"
                            if row["state"] not in {"SUCCEEDED", "CANCELLED"}:
                                row["state"], row["error"] = (
                                    "PAUSED",
                                    "Restored backup; review settings before resuming",
                                )
                        elif table == "steps" and row["state"] == "RUNNING":
                            row["state"] = "READY" if row["attempts"] < row["max_attempts"] else "FAILED"
                            row["heartbeat"] = None
                        db.execute(
                            f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                            [row[c] for c in columns],
                        )
                db.execute(
                    "UPDATE projects SET status='PAUSED' WHERE id IN (SELECT project_id FROM jobs WHERE state='PAUSED')"
                )
                if (
                    db.execute("PRAGMA foreign_key_check").fetchone()
                    or db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                ):
                    raise ValueError("Restored database failed integrity checks")
            with store.connect() as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        os.rename(staging, destination)
        return Store(destination)
    finally:
        if staging.exists():
            # Only the exact generated staging directory in the verified parent is removable.
            if staging.parent != destination.parent or not staging.name.startswith(".studio-restore-"):
                raise RuntimeError("Unsafe restore cleanup target")
            shutil.rmtree(staging)
