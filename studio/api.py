from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.background import BackgroundTask

from studio import media
from studio.domain import (
    CanonEvent,
    EpisodeScript,
    ProjectInput,
    SeasonPlan,
    StrictModel,
    validate_canon_value,
    validate_script,
    continuity_errors,
)
from studio.continuity import draft_events
from studio.storage import Store, digest
from studio.worker import Worker
from studio.providers import WanGPConfig, WanGPProvider
from studio.diagnostics import hardware
from studio.setup_status import classify, read_runtime_status
from studio.draft_editing import edit_eligibility
from studio.export_variants import ExportCopy, enqueue_copy
from studio.shot_revisions import RetakeRequest, enqueue_retake, discard_retake
from studio import backup_import

ROOT = Path(__file__).resolve().parents[1]


class SettingsInput(StrictModel):
    story_engine: str = Field(default="ollama", pattern=r"^(ollama|small_cpu|cpu_1_5b)$")
    story_model: str = Field(default="", max_length=100, pattern=r"^[\w.:/-]*$")
    speech: str = Field(default="windows", pattern=r"^(windows|none)$")
    reserve_mb: int = Field(default=1024, ge=100, le=102400)
    wangp: WanGPConfig = Field(default_factory=WanGPConfig)


class EpisodeRequest(StrictModel):
    episode: int = Field(default=1, ge=1, le=24)


class CanonRevision(StrictModel):
    revision: int = Field(ge=1)
    event: CanonEvent


class ShotDraftEdit(StrictModel):
    shot_id: str = Field(min_length=1, max_length=100)
    action: str | None = Field(default=None, min_length=5, max_length=1500)
    camera: str | None = Field(default=None, min_length=3, max_length=400)
    narration: str | None = Field(default=None, max_length=600)
    speaker_id: str | None = Field(default=None, min_length=1, max_length=100)


class DraftRevision(StrictModel):
    revision: int = Field(ge=1)
    edits: list[ShotDraftEdit] = Field(min_length=1, max_length=120)


def create_app(root: Path | None = None, run_worker=True) -> FastAPI:
    store = Store(root or Path(os.environ.get("STUDIO_DATA", ROOT / "data")))
    worker = Worker(store)
    active_restores: set[str] = set()

    async def finish_owned_restore(function, *args):
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task  # Owned thread keeps its staging until it finishes.
            raise

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            worker.start()
        yield
        if run_worker:
            worker.close()

    app = FastAPI(title="AI Movie Studio", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse(
                {
                    "code": "INVALID_HOST",
                    "message": "Studio only accepts localhost requests.",
                    "retryable": False,
                },
                403,
            )
        origin = request.headers.get("origin")
        if origin and origin not in {
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }:
            return JSONResponse(
                {
                    "code": "INVALID_ORIGIN",
                    "message": "This origin cannot access Studio.",
                    "retryable": False,
                },
                403,
            )
        streaming_restore = request.method == "POST" and request.url.path == "/api/backup/restore"
        if request.method in {"POST", "PUT", "PATCH"} and not streaming_restore:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse(
                        {"code": "INPUT_TOO_LARGE", "message": "Request exceeds 64 KB.", "retryable": False},
                        413,
                    )
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; media-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "code": "INVALID_INPUT",
                "message": "Check your movie settings.",
                "details": [{"field": str(e["loc"][-1]), "message": e["msg"]} for e in exc.errors()],
                "retryable": False,
            },
            422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"code": "REQUEST_FAILED", "message": str(exc.detail), "retryable": exc.status_code >= 500},
            exc.status_code,
        )

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse(
            {"code": "NOT_FOUND", "message": "Project or asset not found.", "retryable": False}, 404
        )

    @app.exception_handler(ValueError)
    async def conflict(request, exc):
        return JSONResponse({"code": "CONFLICT", "message": str(exc), "retryable": False}, 409)

    @app.get("/api/health")
    def health():
        tools = {}
        for name in ("ffmpeg", "ffprobe"):
            try:
                tools[name] = {"available": bool(media.binary(name))}
            except RuntimeError as exc:
                tools[name] = {"available": False, "message": str(exc)}
        disk = shutil.disk_usage(store.root)
        with store.connect() as db:
            integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "service": "ready",
            "database": integrity,
            "media": tools,
            "free_disk_gb": round(disk.free / 1024**3, 1),
            "worker_alive": bool(worker.thread and worker.thread.is_alive()),
            "concurrency": 1,
            "privacy": "Localhost only; no cloud providers",
            "real_generation_verified": False,
            "native_export": "360×640 / 640×360 / 480×480, 24 fps",
            "hardware": hardware(),
        }

    @app.get("/api/providers")
    def providers():
        models = []
        config = WanGPConfig.model_validate(store.settings().get("wangp", {}))
        configured = WanGPProvider(config, store.root).configured()
        try:
            with httpx.Client(timeout=2, trust_env=False) as client:
                response = client.get("http://127.0.0.1:11434/api/tags")
                response.raise_for_status()
                models = [m["name"] for m in response.json()["models"]]
        except (httpx.HTTPError, KeyError):
            pass
        result = {
            "providers": [
                {
                    "id": "demo",
                    "name": "Development demo",
                    "available": True,
                    "is_mock": True,
                    "capabilities": ["story-template", "abstract-reference", "motion-storyboard"],
                },
                {
                    "id": "ollama",
                    "name": "Local story · Ollama",
                    "available": bool(models),
                    "is_mock": False,
                    "models": models,
                    "verified": False,
                },
                {
                    "id": "local-video",
                    "name": "Local image & video · WanGP",
                    "available": configured,
                    "is_mock": False,
                    "verified": False,
                    "message": "Configured installation; inference and 6 GB compatibility not yet verified."
                    if configured
                    else "No verified image/video model. Weight downloads and runtime setup require approval.",
                },
                {
                    "id": "small-cpu",
                    "name": "Small CPU story · Qwen 0.5B",
                    "available": (ROOT / "tools" / "story" / "llama-server.exe").exists()
                    and (ROOT / "tools" / "story" / "qwen2.5-0.5b-instruct-q4_k_m.gguf").exists(),
                    "is_mock": False,
                    "message": "Small feasibility model. Structured plan tested separately; story quality not established.",
                },
                {
                    "id": "cpu-1-5b",
                    "name": "CPU story · Qwen 1.5B experiment",
                    "available": (ROOT / "tools/story/llama-server.exe").is_file()
                    and (ROOT / "tools/story/qwen2.5-1.5b-instruct-q4_k_m.gguf").is_file(),
                    "is_mock": False,
                    "verified": False,
                    "message": "Installed CPU experiment; checksum is checked at load. Writing quality/performance unproven; requires 5 GiB free RAM."
                    if (ROOT / "tools/story/qwen2.5-1.5b-instruct-q4_k_m.gguf").is_file()
                    else "Separate 1.2 GB download approval required. CPU writing quality/performance unproven; requires 5 GiB free RAM.",
                },
                {
                    "id": "windows-speech",
                    "name": "Installed Windows speech",
                    "available": os.name == "nt",
                    "is_mock": False,
                    "message": "Voice availability is checked at generation; no voice cloning.",
                },
            ]
        }

        result["providers"] = classify(
            result["providers"], hardware()["memory"], read_runtime_status(ROOT), config.installation
        )
        return result

    @app.get("/api/settings")
    def settings():
        return store.settings()

    @app.patch("/api/settings")
    def update_settings(value: SettingsInput):
        with store.connect() as db:
            for key, item in value.model_dump().items():
                db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(item)))
        return store.settings()

    @app.post("/api/projects", status_code=201)
    def create(spec: ProjectInput):
        pid, created = store.create(spec)
        if created:
            store.enqueue(pid)
        return store.get(pid)

    @app.get("/api/projects")
    def projects():
        with store.connect() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT id,title,status,created,updated,spec FROM projects ORDER BY created DESC LIMIT 200"
                )
            ]
        for row in rows:
            row["spec"] = json.loads(row["spec"])
        return rows

    @app.get("/api/projects/{pid}")
    def project(pid: str):
        return store.get(pid)

    @app.post("/api/projects/{pid}/produce", status_code=202)
    def produce(pid: str, value: EpisodeRequest):
        return {"job_id": store.enqueue(pid, value.episode)}

    @app.post("/api/projects/{pid}/episodes/{number}/export-copy", status_code=202)
    def export_copy(pid: str, number: int, value: ExportCopy):
        return enqueue_copy(store, pid, number, value)

    @app.post("/api/projects/{pid}/episodes/{number}/shots/{shot_id}/retake", status_code=202)
    def retake(pid: str, number: int, shot_id: str, value: RetakeRequest):
        return enqueue_retake(store, pid, number, shot_id, value)

    @app.post("/api/projects/{pid}/episodes/{number}/discard-retake")
    def discard_take(pid: str, number: int):
        discard_retake(store, pid, number)
        return store.get(pid)

    for action in ("pause", "resume", "cancel"):

        def register(action):
            def control(pid: str):
                store.get(pid)
                store.control(pid, action)
                return store.get(pid)

            app.post(f"/api/projects/{{pid}}/{action}")(control)

            def episode_control(pid: str, number: int):
                store.get(pid)
                store.control(pid, action, number)
                return store.get(pid)

            app.post(f"/api/projects/{{pid}}/episodes/{{number}}/{action}")(episode_control)

        register(action)

    @app.get("/api/projects/{pid}/episodes/{number}/draft-history")
    def draft_history(pid: str, number: int):
        project = store.get(pid)
        if not 1 <= number <= project["spec"]["episodes"]:
            raise ValueError("Episode is outside the season plan")
        history = []
        with store.connect() as db:
            for row in db.execute(
                "SELECT data,created FROM events WHERE project_id=? AND kind='draft_revision' ORDER BY seq DESC LIMIT 500",
                (pid,),
            ):
                event = json.loads(row["data"])
                if event["episode"] == number:
                    history.append(
                        {
                            "before_revision": event["revision"],
                            "created": row["created"],
                            "screenplay": event["original_script"]["screenplay"],
                        }
                    )
                    if len(history) == 25:
                        break
        return {"revisions": history, "limit": 25}

    @app.patch("/api/projects/{pid}/episodes/{number}/draft")
    def edit_draft(pid: str, number: int, value: DraftRevision):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            project = store.get(pid)
            if value.revision != project["revision"]:
                raise ValueError("Story changed in another window. Reload before editing.")
            episode = next((e for e in project["episodes"] if e["number"] == number), None)
            allowed, reason = edit_eligibility(project, episode)
            if not allowed:
                raise ValueError(reason)
            original = episode["script"]
            script = EpisodeScript.model_validate(original)
            shots = {s.id: s for s in script.shots}
            if len({e.shot_id for e in value.edits}) != len(value.edits):
                raise ValueError("A shot may appear only once in a draft edit")
            for edit in value.edits:
                if edit.shot_id not in shots:
                    raise ValueError("Draft edit references an unknown shot")
                fields = edit.model_dump(exclude_none=True, exclude={"shot_id"})
                if not fields:
                    raise ValueError("Provide scene action, camera, spoken text or a speaker to edit")
                for field, content in fields.items():
                    setattr(shots[edit.shot_id], field, content)
            cast = {c["id"]: c["name"] for c in project["plan"]["characters"]}
            script.screenplay = (
                f"USER-EDITED SAVED DRAFT — Episode {number}. Scene timing and identities retained.\n\n"
                + "\n\n".join(
                    f"SCENE {s.number} — {s.camera}\n{s.action}\n{cast.get(s.speaker_id, 'Unknown speaker')} (offscreen): {s.narration}"
                    for s in script.shots
                )
            )
            script = EpisodeScript.model_validate(script.model_dump())
            plan = SeasonPlan.model_validate(project["plan"])
            validate_script(script, plan, project["spec"]["target_seconds"])
            conflicts = continuity_errors(script, draft_events(project, number), plan)
            if conflicts:
                raise ValueError("CANON_CONFLICT: " + "; ".join(conflicts))
            revision = project["revision"] + 1
            db.execute(
                "UPDATE episodes SET script=?,status='DRAFTED' WHERE project_id=? AND number=?",
                (script.model_dump_json(), pid, number),
            )
            db.execute(
                "UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number>? AND status IN ('DRAFTED','REVIEW_REQUIRED')",
                (pid, number),
            )
            db.execute(
                "UPDATE projects SET revision=?,updated=strftime('%s','now') WHERE id=?", (revision, pid)
            )
            store.event(
                db,
                pid,
                None,
                "draft_revision",
                {
                    "episode": number,
                    "revision": revision,
                    "original_script": original,
                    "edits": [e.model_dump(exclude_none=True) for e in value.edits],
                },
            )
            target = next((j for j in project["jobs"] if j["episode"] == number), None)
            if target:
                db.execute(
                    "UPDATE steps SET state='SUPERSEDED' WHERE job_id=? AND state IN ('READY','FAILED')",
                    (target["id"],),
                )
                ordinal = (
                    db.execute("SELECT MAX(ordinal) FROM steps WHERE job_id=?", (target["id"],)).fetchone()[0]
                    + 1
                )
                store.add_step(
                    db, target["id"], ordinal, "SCRIPT", {"episode": number, "reviewed_edit": True}
                )
                db.execute("UPDATE jobs SET state='PAUSED',error=NULL WHERE id=?", (target["id"],))
                db.execute("UPDATE projects SET status='PAUSED' WHERE id=?", (pid,))
                store.event(
                    db,
                    pid,
                    target["id"],
                    "production_steps_superseded",
                    {"episode": number, "revision": revision},
                )
        return store.get(pid)

    @app.post("/api/projects/{pid}/canon")
    def revise_canon(pid: str, value: CanonRevision):
        project = store.get(pid)
        if value.event.episode > project["spec"]["episodes"]:
            raise ValueError("Event episode is outside the planned season")
        entities = (
            {pid}
            | {c["id"] for c in (project["plan"] or {}).get("characters", [])}
            | {p["id"] for p in (project["plan"] or {}).get("props", [])}
        )
        if value.event.entity_id not in entities:
            raise ValueError("Canon event references an unknown character")
        if value.event.field != "outcome":
            if not project["plan"]:
                raise ValueError("Create the story plan before revising canon")
            validate_canon_value(
                SeasonPlan.model_validate(project["plan"]),
                value.event.entity_id,
                value.event.field,
                value.event.value,
            )
        elif value.event.entity_id != pid:
            raise ValueError("Outcome events belong to the project")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = db.execute("SELECT revision FROM projects WHERE id=?", (pid,)).fetchone()[0]
            if value.revision != revision:
                raise ValueError("Story changed in another window. Reload before editing.")
            active = db.execute(
                "SELECT 1 FROM jobs WHERE project_id=? AND state IN ('RUNNING','QUEUED','PAUSED')", (pid,)
            ).fetchone()
            if active:
                raise ValueError("Finish or cancel the active production before revising canon")
            from uuid import uuid4

            event = value.event
            db.execute(
                "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    pid,
                    event.entity_id,
                    event.episode,
                    event.field,
                    event.value,
                    event.reason,
                    revision + 1,
                ),
            )
            db.execute("UPDATE projects SET revision=revision+1 WHERE id=?", (pid,))
            affected = [
                r[0]
                for r in db.execute(
                    "SELECT number FROM episodes WHERE project_id=? AND number>?", (pid, event.episode)
                )
            ]
            db.execute(
                "UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number>?",
                (pid, event.episode),
            )
            self_data = {"event": event.model_dump(), "affected_episodes": affected, "revision": revision + 1}
            store.event(db, pid, None, "canon_revision", self_data)
        return self_data

    @app.get("/api/projects/{pid}/events")
    async def events(pid: str, request: Request, after: int = 0, follow: bool = True):
        store.get(pid)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(422, "Invalid event cursor")

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                with store.connect() as db:
                    rows = list(
                        db.execute(
                            "SELECT * FROM events WHERE project_id=? AND seq>? ORDER BY seq LIMIT 100",
                            (pid, cursor),
                        )
                    )
                for row in rows:
                    cursor = row["seq"]
                    yield f"id: {cursor}\ndata: {json.dumps({'kind': row['kind'], 'data': json.loads(row['data'])})}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                if not follow:
                    return
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/api/assets/{aid}/content")
    def content(aid: str, download: bool = False):
        path, asset = store.asset_path(aid)
        if not path.is_file() or digest(path) != asset["sha256"]:
            raise HTTPException(409, "Asset is missing or changed; review diagnostics.")
        metadata = json.loads(asset["metadata"])
        extension = path.suffix
        filename = f"movie-studio-episode-{metadata.get('episode', 1)}-{asset['role']}{extension}"
        types = {
            ".mp4": "video/mp4",
            ".png": "image/png",
            ".wav": "audio/wav",
            ".srt": "text/plain",
            ".json": "application/json",
        }
        return FileResponse(
            path,
            media_type=types.get(extension, "application/octet-stream"),
            filename=filename if download else None,
        )

    @app.get("/api/projects/{pid}/manifest")
    def manifest(pid: str):
        return JSONResponse(
            store.get(pid), headers={"Content-Disposition": 'attachment; filename="movie-project.json"'}
        )

    @app.get("/api/backup")
    def backup():
        from uuid import uuid4
        from studio.backup import create_backup

        path = store.root / "backups" / f"{uuid4()}.zip"
        create_backup(store, path)
        return FileResponse(
            path,
            media_type="application/zip",
            filename="movie-studio-backup.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @app.get("/api/backup/restores")
    def unfinished_restores():
        return {"operations": backup_import.pending_imports(store, active_restores)}

    @app.post("/api/backup/restores/{identity}/discard")
    async def discard_restore_upload(identity: str):
        if identity in active_restores:
            raise ValueError("This restore is still running")
        active_restores.add(identity)
        try:
            await finish_owned_restore(backup_import.discard_prepared, store, identity)
            return {"discarded": True}
        finally:
            active_restores.discard(identity)

    @app.post("/api/backup/restores/{identity}/resume")
    async def resume_restore(identity: str):
        if identity in active_restores:
            raise ValueError("This restore is still running")
        active_restores.add(identity)
        try:
            return await finish_owned_restore(backup_import.commit_import, store, identity)
        except (OSError, sqlite3.Error) as error:
            raise HTTPException(
                409, "Restore stopped. Keep the original ZIP and return to Settings to retry."
            ) from error
        finally:
            active_restores.discard(identity)

    @app.post("/api/backup/restore")
    async def restore(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/zip":
            raise HTTPException(415, "Choose a Movie Studio ZIP backup.")
        length = request.headers.get("content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                raise HTTPException(422, "Invalid backup size")
            if not 0 < declared <= backup_import.MAX_UPLOAD:
                raise HTTPException(413, "Backup must be between 1 byte and 20 GB.")
        if shutil.disk_usage(store.root).free < backup_import.RESERVE:
            raise HTTPException(409, "Restore requires a 1 GB free-space reserve.")
        identity, directory = backup_import.begin_upload(store)
        active_restores.add(identity)
        try:
            total = 0
            with (directory / "upload.zip").open("xb") as file:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > backup_import.MAX_UPLOAD:
                        raise HTTPException(413, "Backup exceeds the 20 GB upload limit.")
                    if shutil.disk_usage(store.root).free < len(chunk) + backup_import.RESERVE:
                        raise HTTPException(409, "Restore stopped to preserve 1 GB of free disk space.")
                    file.write(chunk)
                file.flush()
                os.fsync(file.fileno())
            if length is not None and total != declared:
                raise HTTPException(422, "Backup upload was incomplete. Choose the original ZIP again.")

            def finish_restore():
                backup_import.prepare_import(store, identity)
                return backup_import.commit_import(store, identity)

            return await finish_owned_restore(finish_restore)
        except (zipfile.BadZipFile, KeyError, sqlite3.Error) as error:
            raise HTTPException(
                409, "Backup is invalid or inconsistent; your current projects were left unchanged."
            ) from error
        except OSError as error:
            raise HTTPException(
                409,
                "Restore could not finish. Return to Settings to resume a prepared copy; keep the original ZIP.",
            ) from error
        finally:
            active_restores.discard(identity)
            backup_import.discard_unprepared(store, identity)

    dist = ROOT / "client" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="frontend-assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route")
        if not (dist / "index.html").exists():
            return JSONResponse(
                {"message": "Build the interface: cd client; npm install; npm run build"}, 503
            )
        return FileResponse(dist / "index.html")

    return app


app = create_app()
