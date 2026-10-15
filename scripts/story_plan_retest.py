"""Isolated, writing-only reuse of a failed native experiment's saved plan.

No source database, report, entity ID or successful checkpoint is rewritten.
This is a developer experiment tool, not a way to revise user productions.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path
from uuid import UUID

from studio.backup import TABLES, restore_backup, validate_document
from studio.domain import ProjectInput, SeasonPlan
from studio.local_story import CPU_PROFILES
from studio.storage import atomic_json, digest

SOURCE_PROJECT = "a88e242a-120d-4856-b338-187c4e42b5d0"
PRIOR_TEST_MILLISECONDS = 269719
EXPERIMENT_MILLISECONDS = 600000
CLEANUP_MILLISECONDS = 10000


def read_plan_snapshot(source: Path, pid: str, report_path: Path) -> tuple[dict, dict]:
    """Read one coherent SQLite snapshot through a read-only connection."""
    if str(UUID(pid)) != pid:
        raise ValueError("Invalid source project ID")
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    database = source.resolve() / "studio.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        tables = {}
        for table, fields in TABLES.items():
            # Column/table names are constants, never provided by a model or user.
            if table == "projects":
                predicate = "id=?"
            elif table == "steps":
                predicate = "job_id IN (SELECT id FROM jobs WHERE project_id=?)"
            else:
                predicate = "project_id=?"
            tables[table] = [
                dict(row)
                for row in db.execute(
                    f"SELECT {','.join(fields.split())} FROM {table} WHERE {predicate}", (pid,)
                )
            ]
    document = {
        "format": "ai-movie-studio-backup",
        "version": 1,
        "created": time.time(),
        "tables": tables,
    }
    validate_document(document)
    if len(tables["projects"]) != 1 or len(tables["jobs"]) != 1 or len(tables["episodes"]) != 1:
        raise ValueError("Plan reuse requires exactly one failed, single-episode experiment")
    project, job, episode = tables["projects"][0], tables["jobs"][0], tables["episodes"][0]
    spec = ProjectInput.model_validate_json(project["spec"])
    if (
        spec.backend != "local"
        or spec.kind != "drama"
        or spec.target_seconds != 40
        or spec.episodes != 1
        or spec.prewrite_season
        or job["episode"] != 1
        or job["state"] != "FAILED"
        or json.loads(job["config"]).get("story_engine") != "cpu_4b"
        or episode["script"]
        or episode["number"] != 1
        or tables["assets"]
        or tables["canon"]
    ):
        raise ValueError("Only the unproduced, failed native 4B writing sample can be reused")
    steps = tables["steps"]
    plans = [s for s in steps if s["stage"] == "PLAN"]
    if (
        len(plans) != 1
        or plans[0]["state"] != "SUCCEEDED"
        or plans[0]["ordinal"] != 0
        or any(s["stage"] not in {"PLAN", "SCRIPT_BATCH", "SCRIPT"} for s in steps)
        or any(s["state"] not in {"READY", "FAILED"} or s["output"] for s in steps if s not in plans)
    ):
        raise ValueError("Refuse to discard completed, running or unexpected work")
    plan = SeasonPlan.model_validate_json(project["plan"]).model_dump(mode="json")
    output = json.loads(plans[0]["output"])
    if (
        output != {"plan": plan, "artifacts": []}
        or len(plan["episodes"]) != 1
        or plan["episodes"][0] != json.loads(episode["outline"])
        or report.get("project_id") != pid
        or report.get("is_mock") is not False
        or report.get("status") != "FAILED"
        or report.get("script") is not None
        or report.get("model") != CPU_PROFILES["cpu_4b"][0]
        or report.get("plan") != plan
        or [s.get("id") for s in report.get("completed_steps", [])] != [plans[0]["id"]]
        or round(report.get("elapsed_seconds", 0) * 1000) != PRIOR_TEST_MILLISECONDS
    ):
        raise ValueError("Saved plan, source checkpoint and original native report must agree")
    # Machine-specific settings are never restored from an archive.
    job["config"] = "{}"
    lineage = {
        "source_project_id": pid,
        "source_job_id": job["id"],
        "source_plan_step_id": plans[0]["id"],
        "source_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "source_plan_sha256": hashlib.sha256(
            json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "prior_test_milliseconds": PRIOR_TEST_MILLISECONDS,
        "plan_reused": True,
        "plan_generated_this_run": False,
    }
    return document, lineage


def prepare_plan_retest(source: Path, pid: str, report_path: Path, destination: Path, run_id: str):
    """Preserve all original steps and append new two-shot steps only in a clone."""
    if str(UUID(run_id)) != run_id or run_id == pid:
        raise ValueError("Retest needs a new run ID, distinct from the preserved project ID")
    document, lineage = read_plan_snapshot(source, pid, report_path)
    destination = destination.resolve()
    if destination == source.resolve() or destination.is_relative_to(source.resolve()):
        raise ValueError("Retest destination must be separate from the original experiment")
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / "original-plan.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as handle:
        handle.writestr("studio.json", json.dumps(document, ensure_ascii=False).encode("utf-8"))
    clone = restore_backup(archive, destination / "workspace")
    job = document["tables"]["jobs"][0]
    jid = job["id"]
    config = {**clone.settings(), "story_engine": "cpu_4b", "speech": "none"}
    with clone.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR REPLACE INTO settings VALUES('story_engine','\"cpu_4b\"')")
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")
        db.execute("UPDATE jobs SET config=? WHERE id=?", (json.dumps(config), jid))
        db.execute("UPDATE steps SET state='SUPERSEDED' WHERE job_id=? AND stage!='PLAN'", (jid,))
        ordinal = db.execute("SELECT MAX(ordinal)+1 FROM steps WHERE job_id=?", (jid,)).fetchone()[0]
        clone.add_story_steps(db, jid, ordinal, 1, clone.get(pid)["spec"])
        clone.event(db, pid, jid, "native_plan_retest_prepared", {"run_id": run_id, **lineage})
    lineage.update(run_id=run_id, source_archive_sha256=digest(archive))
    atomic_json(
        destination / "preparation.json",
        {
            "status": "PREPARED_NOT_RUN",
            "is_mock": False,
            "quality_review": "NOT_PERFORMED",
            "shots_per_request": 2,
            **lineage,
        },
    )
    return clone, lineage


def reserve_retest_budget(path: Path, max_seconds: int, run_id: str, lineage: dict):
    """One exclusive, durable reservation. A killed run never silently refunds time."""
    if not 1 <= max_seconds <= 320:
        raise ValueError("Saved-plan retest is limited to 320 seconds plus cleanup reserve")
    total = PRIOR_TEST_MILLISECONDS + max_seconds * 1000 + CLEANUP_MILLISECONDS
    if total > EXPERIMENT_MILLISECONDS or lineage["prior_test_milliseconds"] != PRIOR_TEST_MILLISECONDS:
        raise ValueError("Approved cumulative 600-second writing experiment would be exceeded")
    path.parent.mkdir(parents=True, exist_ok=True)
    reservation = {
        "run_id": run_id,
        "prior_test_milliseconds": PRIOR_TEST_MILLISECONDS,
        "reserved_test_milliseconds": max_seconds * 1000,
        "reserved_cleanup_milliseconds": CLEANUP_MILLISECONDS,
        "cumulative_reserved_milliseconds": total,
        "created": time.time(),
        "source_report_sha256": lineage["source_report_sha256"],
        "policy": "No automatic reuse or refund after interruption or failure",
    }
    # Exclusive creation prevents concurrent tools from each claiming the same allowance.
    # Partial writes also remain blocking evidence rather than restoring allowance.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(reservation, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    return reservation
