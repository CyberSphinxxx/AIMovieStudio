from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from studio import media
from studio.domain import CanonEvent, ProjectInput, StrictModel
from studio.storage import Store, digest
from studio.worker import Worker
from studio.providers import WanGPConfig, WanGPProvider

ROOT = Path(__file__).resolve().parents[1]


class SettingsInput(StrictModel):
    story_engine: str = Field(default="ollama", pattern=r"^(ollama|small_cpu)$")
    story_model: str = Field(default="", max_length=100, pattern=r"^[\w.:/-]*$")
    speech: str = Field(default="windows", pattern=r"^(windows|none)$")
    reserve_mb: int = Field(default=1024, ge=100, le=102400)
    wangp: WanGPConfig = Field(default_factory=WanGPConfig)


class EpisodeRequest(StrictModel):
    episode: int = Field(default=1, ge=1, le=24)


class CanonRevision(StrictModel):
    revision: int = Field(ge=1)
    event: CanonEvent


def create_app(root: Path | None = None, run_worker=True) -> FastAPI:
    store = Store(root or Path(os.environ.get("STUDIO_DATA", ROOT / "data")))
    worker = Worker(store)

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
        if request.method in {"POST", "PUT", "PATCH"}:
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
        return {
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
                    "id": "windows-speech",
                    "name": "Installed Windows speech",
                    "available": os.name == "nt",
                    "is_mock": False,
                    "message": "Voice availability is checked at generation; no voice cloning.",
                },
            ]
        }

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

    for action in ("pause", "resume", "cancel"):

        def register(action):
            def control(pid: str):
                store.get(pid)
                store.control(pid, action)
                return store.get(pid)

            app.post(f"/api/projects/{{pid}}/{action}")(control)

        register(action)

    @app.post("/api/projects/{pid}/canon")
    def revise_canon(pid: str, value: CanonRevision):
        project = store.get(pid)
        if value.event.episode > project["spec"]["episodes"]:
            raise ValueError("Event episode is outside the planned season")
        entities = {pid} | {c["id"] for c in (project["plan"] or {}).get("characters", [])}
        if value.event.entity_id not in entities:
            raise ValueError("Canon event references an unknown character")
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
    async def events(pid: str, request: Request, after: int = 0):
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
