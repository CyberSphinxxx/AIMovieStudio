from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from studio.domain import ProjectInput
from studio.draft_editing import edit_eligibility


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "studio.sqlite3"
        self.initialization_retries = 0
        self.read_retries = 0
        for attempt in range(3):
            try:
                self.migrate()
                break
            except sqlite3.Error as error:
                # A killed Windows process can briefly retain a WAL file handle.
                # Retry only the observed truncate error, using a fresh connection.
                # Never delete/replace WAL files or retry corruption/write failures.
                if (
                    os.name == "nt"
                    and error.sqlite_errorcode == sqlite3.SQLITE_IOERR_TRUNCATE
                    and attempt < 2
                ):
                    self.initialization_retries += 1
                    logging.getLogger(__name__).warning(
                        "Retrying SQLite startup file truncation (%s), attempt %s",
                        error.sqlite_errorname,
                        attempt + 1,
                    )
                    time.sleep(0.1 * (attempt + 1))
                    continue
                error.add_note(f"SQLite initialization: {error.sqlite_errorname} ({error.sqlite_errorcode})")
                raise

    def migrate(self):
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS projects(
                  id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, spec TEXT NOT NULL,
                  title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'QUEUED', revision INTEGER DEFAULT 1,
                  plan TEXT, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS episodes(
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                  number INTEGER NOT NULL, outline TEXT NOT NULL, script TEXT,
                  status TEXT NOT NULL DEFAULT 'PLANNED', UNIQUE(project_id,number));
                CREATE TABLE IF NOT EXISTS jobs(
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                  episode INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'QUEUED', error TEXT,
                  created REAL NOT NULL, UNIQUE(project_id,episode));
                CREATE TABLE IF NOT EXISTS steps(
                  id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), ordinal INTEGER NOT NULL,
                  stage TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'READY',
                  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
                  heartbeat REAL, output TEXT, error TEXT, UNIQUE(job_id,ordinal));
                CREATE TABLE IF NOT EXISTS assets(
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                  step_id TEXT NOT NULL REFERENCES steps(id), role TEXT NOT NULL, path TEXT NOT NULL,
                  sha256 TEXT NOT NULL, metadata TEXT NOT NULL, UNIQUE(step_id,role));
                CREATE TABLE IF NOT EXISTS events(
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id),
                  project_id TEXT NOT NULL REFERENCES projects(id), kind TEXT NOT NULL,
                  data TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS canon(
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                  entity_id TEXT NOT NULL, episode INTEGER NOT NULL, field TEXT NOT NULL,
                  value TEXT NOT NULL, reason TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO migrations VALUES(1,?)", (time.time(),))
            columns = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
            if "config" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN config TEXT NOT NULL DEFAULT '{}'")
            db.execute("INSERT OR IGNORE INTO migrations VALUES(2,?)", (time.time(),))

    @contextmanager
    def connect(self):
        db, original_error = None, None
        try:
            db = sqlite3.connect(self.database, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException as error:
            original_error = error
            if isinstance(error, sqlite3.Error):
                error.add_note(
                    f"SQLite connection: {getattr(error, 'sqlite_errorname', 'UNKNOWN')} "
                    f"({getattr(error, 'sqlite_errorcode', 'UNKNOWN')})"
                )
            if db is not None:
                try:
                    db.rollback()
                except Exception as cleanup_error:
                    error.add_note(f"SQLite rollback also failed: {cleanup_error!r}")
            raise
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as cleanup_error:
                    if original_error is None:
                        raise
                    original_error.add_note(f"SQLite close also failed: {cleanup_error!r}")

    def event(self, db, pid: str, jid: str | None, kind: str, data: dict):
        db.execute(
            "INSERT INTO events(job_id,project_id,kind,data,created) VALUES(?,?,?,?,?)",
            (jid, pid, kind, json.dumps(data), time.time()),
        )

    def create(self, spec: ProjectInput) -> tuple[str, bool]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM projects WHERE key=?", (spec.idempotency_key,)).fetchone()
            if prior:
                if ProjectInput.model_validate_json(prior["spec"]).model_dump() != spec.model_dump():
                    raise ValueError("Idempotency key already belongs to a different idea")
                return prior["id"], False
            pid = str(uuid4())
            title = " ".join(spec.idea.split()[:7]).rstrip(".,!?")
            db.execute(
                "INSERT INTO projects(id,key,spec,title,created,updated) VALUES(?,?,?,?,?,?)",
                (pid, spec.idempotency_key, spec.model_dump_json(), title, time.time(), time.time()),
            )
            self.event(db, pid, None, "project_created", {"title": title})
        return pid, True

    def get(self, pid: str) -> dict:
        for attempt in range(3):
            try:
                return self._project_snapshot(pid)
            except sqlite3.Error as error:
                # Reproduced first-read recovery truncation after TerminateProcess.
                # Only this read-only snapshot is safe to restart; never replay writes.
                if (
                    os.name == "nt"
                    and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_IOERR_TRUNCATE
                    and attempt < 2
                ):
                    self.read_retries += 1
                    logging.getLogger(__name__).warning(
                        "Retrying SQLite project snapshot truncation (%s), attempt %s",
                        error.sqlite_errorname,
                        attempt + 1,
                    )
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise

    def _project_snapshot(self, pid: str) -> dict:
        with self.connect() as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if not row:
                raise KeyError(pid)
            project = dict(row)
            project["spec"] = json.loads(project["spec"])
            project["plan"] = json.loads(project["plan"]) if project["plan"] else None
            project["episodes"] = [
                dict(r)
                for r in db.execute("SELECT * FROM episodes WHERE project_id=? ORDER BY number", (pid,))
            ]
            for ep in project["episodes"]:
                ep["outline"] = json.loads(ep["outline"])
                ep["script"] = json.loads(ep["script"]) if ep["script"] else None
            project["jobs"] = [
                dict(r) for r in db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY episode", (pid,))
            ]
            for job in project["jobs"]:
                job["resource_wait"] = None
                if job["state"] == "WAITING_RESOURCES":
                    from studio.resource_wait import load_wait

                    try:
                        wait = load_wait(db, job["id"])
                        if wait is None:
                            raise ValueError("Missing resource wait snapshot")
                        job["resource_wait"] = wait.model_dump()
                    except ValueError:
                        job["error"] = (
                            "Saved resource waiting needs review. Pause and resume after reviewing Settings."
                        )
                job["steps"] = [
                    dict(r)
                    for r in db.execute("SELECT * FROM steps WHERE job_id=? ORDER BY ordinal", (job["id"],))
                ]
                for step in job["steps"]:
                    step["payload"] = json.loads(step["payload"])
                    step["output"] = json.loads(step["output"]) if step["output"] else None
            project["assets"] = [
                dict(r) for r in db.execute("SELECT * FROM assets WHERE project_id=? ORDER BY rowid", (pid,))
            ]
            for asset in project["assets"]:
                asset["metadata"] = json.loads(asset["metadata"])
                del asset["path"]
            from studio.reference_variants import reference_choices

            project["reference_choices"] = reference_choices(db, pid, project["assets"])
            project["canon"] = [
                dict(r)
                for r in db.execute("SELECT * FROM canon WHERE project_id=? ORDER BY episode,rowid", (pid,))
            ]
            from studio.canon_timing import with_timing

            project["canon"] = with_timing(
                project["canon"],
                db.execute(
                    "SELECT seq,kind,data FROM events WHERE project_id=? AND kind IN ('canon_committed','canon_revision') ORDER BY seq",
                    (pid,),
                ),
            )
            for episode in project["episodes"]:
                episode["can_edit_draft"], episode["draft_edit_reason"] = edit_eligibility(project, episode)
            return project

    def enqueue(self, pid: str, episode: int = 1) -> str:
        project = self.get(pid)
        config = self.settings()
        if not 1 <= episode <= project["spec"]["episodes"]:
            raise ValueError("Episode is outside the season plan")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM jobs WHERE project_id=? AND episode=?", (pid, episode)
            ).fetchone()
            if previous:
                return previous["id"]
            if db.execute(
                "SELECT 1 FROM jobs WHERE project_id=? AND state!='SUCCEEDED' LIMIT 1", (pid,)
            ).fetchone():
                raise ValueError("Finish or resolve unfinished work before producing another episode")
            if episode > 1:
                prior = db.execute(
                    "SELECT state FROM jobs WHERE project_id=? AND episode=?", (pid, episode - 1)
                ).fetchone()
                if not prior or prior["state"] != "SUCCEEDED":
                    raise ValueError("Finish the previous episode so its canon is available")
            jid = str(uuid4())
            db.execute(
                "INSERT INTO jobs(id,project_id,episode,created,config) VALUES(?,?,?,?,?)",
                (jid, pid, episode, time.time(), json.dumps(config)),
            )
            first = "PLAN" if not project["plan"] else "SCRIPT"
            if first == "PLAN":
                self.add_step(db, jid, 0, first, {"episode": episode})
            else:
                saved = next(e for e in project["episodes"] if e["number"] == episode)
                self.add_story_steps(
                    db,
                    jid,
                    0,
                    episode,
                    project["spec"],
                    reuse=saved["status"] == "DRAFTED" and bool(saved["script"]),
                )
            db.execute("UPDATE projects SET status='QUEUED',updated=? WHERE id=?", (time.time(), pid))
            self.event(db, pid, jid, "queued", {"episode": episode})
            return jid

    def add_step(self, db, jid, ordinal, stage, payload):
        sid = str(uuid4())
        db.execute(
            "INSERT OR IGNORE INTO steps(id,job_id,ordinal,stage,payload) VALUES(?,?,?,?,?)",
            (sid, jid, ordinal, stage, json.dumps(payload)),
        )
        return db.execute("SELECT id FROM steps WHERE job_id=? AND ordinal=?", (jid, ordinal)).fetchone()[
            "id"
        ]

    def add_story_steps(self, db, jid, ordinal, episode, spec, *, draft=False, reuse=False):
        from studio.story_budget import shots_per_request

        stage = "DRAFT" if draft else "SCRIPT"
        total = math.ceil(spec["target_seconds"] / 5)
        # Use the enqueued job's configuration even if Settings changed while planning.
        config = json.loads(db.execute("SELECT config FROM jobs WHERE id=?", (jid,)).fetchone()["config"])
        batch_size = shots_per_request(config)
        batches = []
        if total > batch_size and not reuse:
            for start in range(0, total, batch_size):
                payload = {
                    "episode": episode,
                    "start": start,
                    "count": min(batch_size, total - start),
                    "total": total,
                    "previous_batch_ids": list(batches),
                }
                batches.append(self.add_step(db, jid, ordinal, stage + "_BATCH", payload))
                ordinal += 1
        self.add_step(db, jid, ordinal, stage, {"episode": episode, "batch_ids": batches})
        return ordinal + 1

    def control(self, pid: str, action: str, episode: int | None = None):
        states = {"pause": "PAUSED", "cancel": "CANCELLED", "resume": "QUEUED"}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE project_id=? AND (? IS NULL OR episode=?) ORDER BY episode DESC LIMIT 1",
                (pid, episode, episode),
            ).fetchone()
            if not row:
                raise ValueError("There is no production job to control")
            if row["state"] == "SUCCEEDED":
                raise ValueError("This episode has already finished")
            if row["state"] == "CANCELLED" and action == "resume":
                raise ValueError("Cancelled jobs are terminal; create a new project")
            if action == "resume":
                exhausted = db.execute(
                    "SELECT 1 FROM steps WHERE job_id=? AND state='FAILED' AND attempts>=max_attempts",
                    (row["id"],),
                ).fetchone()
                if exhausted:
                    raise ValueError(
                        "Retry budget exhausted. Review diagnostics before creating a new production."
                    )
                db.execute(
                    "UPDATE steps SET state='READY',error=NULL WHERE job_id=? AND state='FAILED'",
                    (row["id"],),
                )
                if row["state"] == "FAILED" or not json.loads(row["config"]):
                    db.execute(
                        "UPDATE jobs SET config=? WHERE id=?", (json.dumps(self.settings()), row["id"])
                    )
                    self.event(
                        db,
                        pid,
                        row["id"],
                        "configuration_updated_for_retry",
                        {
                            "reason": "User requested retry with current settings"
                            if row["state"] == "FAILED"
                            else "User resumed imported/legacy job with current settings"
                        },
                    )
            db.execute("UPDATE jobs SET state=?,error=NULL WHERE id=?", (states[action], row["id"]))
            db.execute(
                "UPDATE projects SET status=?,updated=? WHERE id=?", (states[action], time.time(), pid)
            )
            self.event(db, pid, row["id"], action, {})

    def resolve(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Path is outside the asset store")
        return path

    def asset_path(self, aid: str) -> tuple[Path, dict]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
        if not row:
            raise KeyError(aid)
        return self.resolve(row["path"]), dict(row)

    def settings(self) -> dict:
        defaults = {
            "story_model": "",
            "story_engine": "ollama",
            "speech": "windows",
            "sound_effects": True,
            "balanced_audio": True,
            "reserve_mb": 1024,
            "wangp": {},
        }
        with self.connect() as db:
            defaults.update({r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")})
        return defaults
