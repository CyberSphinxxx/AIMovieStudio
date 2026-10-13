"""Append durable, idempotent copies of an immutable original movie."""

import json
import time
from typing import Literal

from studio.domain import StrictModel
from studio.media import SIZES
from studio.storage import Store


class ExportCopy(StrictModel):
    orientation: Literal["portrait", "landscape", "square"]


def enqueue_copy(store: Store, pid: str, number: int, value: ExportCopy) -> dict:
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
            raise KeyError(pid)
        job = db.execute("SELECT * FROM jobs WHERE project_id=? AND episode=?", (pid, number)).fetchone()
        if not job:
            raise ValueError("Finish this episode before making an export copy")
        source = db.execute(
            "SELECT a.* FROM assets a JOIN steps s ON s.id=a.step_id "
            "WHERE a.project_id=? AND s.job_id=? AND a.role IN ('export','export-edition') ORDER BY a.rowid DESC LIMIT 1",
            (pid, job["id"]),
        ).fetchone()
        if not source:
            raise ValueError("Finish this episode before making an export copy")
        metadata = json.loads(source["metadata"])
        if (metadata["width"], metadata["height"]) == SIZES[value.orientation]:
            return {"asset_id": source["id"], "state": "SUCCEEDED", "reused": True}
        for step in db.execute(
            "SELECT id,state,payload FROM steps WHERE job_id=? AND stage='REFORMAT'", (job["id"],)
        ):
            payload = json.loads(step["payload"])
            if payload["source_id"] == source["id"] and payload["orientation"] == value.orientation:
                return {"step_id": step["id"], "state": step["state"], "reused": True}
        if (
            job["state"] != "SUCCEEDED"
            or db.execute(
                "SELECT 1 FROM jobs WHERE project_id=? AND state!='SUCCEEDED' LIMIT 1",
                (pid,),
            ).fetchone()
        ):
            raise ValueError("Finish, resume or resolve stopped production before making another copy")
        ordinal = db.execute("SELECT MAX(ordinal) FROM steps WHERE job_id=?", (job["id"],)).fetchone()[0] + 1
        store.add_step(
            db,
            job["id"],
            ordinal,
            "REFORMAT",
            {
                "source_id": source["id"],
                "source_sha256": source["sha256"],
                "orientation": value.orientation,
                "profile_version": 1,
            },
        )
        step_id = db.execute(
            "SELECT id FROM steps WHERE job_id=? AND ordinal=?", (job["id"], ordinal)
        ).fetchone()[0]
        db.execute("UPDATE jobs SET state='QUEUED',error=NULL WHERE id=?", (job["id"],))
        db.execute("UPDATE projects SET status='QUEUED',updated=? WHERE id=?", (time.time(), pid))
        store.event(
            db,
            pid,
            job["id"],
            "export_copy_requested",
            {"step": step_id, "source_id": source["id"], **value.model_dump()},
        )
        return {"step_id": step_id, "state": "READY", "reused": False}
