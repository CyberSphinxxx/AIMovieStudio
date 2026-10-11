from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from studio.domain import ProjectInput


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
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

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
                if json.loads(prior["spec"]) != spec.model_dump():
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
        with self.connect() as db:
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
            project["canon"] = [
                dict(r)
                for r in db.execute("SELECT * FROM canon WHERE project_id=? ORDER BY episode,rowid", (pid,))
            ]
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
            self.add_step(db, jid, 0, first, {"episode": episode})
            db.execute("UPDATE projects SET status='QUEUED',updated=? WHERE id=?", (time.time(), pid))
            self.event(db, pid, jid, "queued", {"episode": episode})
            return jid

    def add_step(self, db, jid, ordinal, stage, payload):
        db.execute(
            "INSERT OR IGNORE INTO steps(id,job_id,ordinal,stage,payload) VALUES(?,?,?,?,?)",
            (str(uuid4()), jid, ordinal, stage, json.dumps(payload)),
        )

    def control(self, pid: str, action: str):
        states = {"pause": "PAUSED", "cancel": "CANCELLED", "resume": "QUEUED"}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY episode DESC LIMIT 1", (pid,)
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
                if row["state"] == "FAILED":
                    db.execute(
                        "UPDATE jobs SET config=? WHERE id=?", (json.dumps(self.settings()), row["id"])
                    )
                    self.event(
                        db,
                        pid,
                        row["id"],
                        "configuration_updated_for_retry",
                        {"reason": "User requested retry with current settings"},
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
            "reserve_mb": 1024,
            "wangp": {},
        }
        with self.connect() as db:
            defaults.update({r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")})
        return defaults
