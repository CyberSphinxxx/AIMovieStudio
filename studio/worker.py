from __future__ import annotations

import json
import os
import shutil
import threading
import time

from studio import media
from studio.domain import SeasonPlan, continuity_errors, stable, validate_script
from studio.storage import Store, atomic_json, digest
from studio.story import DemoStory, OllamaStory
from studio.providers import WanGPConfig, WanGPProvider

STAGES = {
    "PLAN": "Preparing your story",
    "SCRIPT": "Writing the screenplay",
    "DRAFT": "Prewriting the season",
    "REFERENCE": "Creating character references",
    "FRAME": "Composing shot keyframes",
    "CLIP": "Animating shots",
    "AUDIO": "Building the soundtrack",
    "EXPORT": "Finishing your movie",
}


class Worker:
    def __init__(self, store: Store):
        self.store = store
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.lockfile = None
        self.last_heartbeat = 0.0

    def start(self):
        self.lockfile = (self.store.root / "worker.lock").open("a+b")
        self.lockfile.seek(0)
        self.lockfile.write(b"0")
        self.lockfile.flush()
        self.lockfile.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            self.lockfile.close()
            raise RuntimeError("Another Studio worker owns this data directory") from e
        self.recover()
        self.thread = threading.Thread(target=self.loop, name="studio-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
        if self.lockfile and (not self.thread or not self.thread.is_alive()):
            self.lockfile.close()

    def recover(self):
        # Exclusive OS lock proves the previous worker exited; no arbitrary age assumption.
        with self.store.connect() as db:
            steps = [
                dict(r)
                for r in db.execute(
                    "SELECT s.*,j.project_id,j.episode FROM steps s JOIN jobs j ON j.id=s.job_id WHERE s.state='RUNNING'"
                )
            ]
        for step in steps:
            receipt = self.directory(step) / "receipt.json"
            if receipt.exists():
                try:
                    output = json.loads(receipt.read_text(encoding="utf-8"))
                    self.verify(output)
                    self.complete(step, output)
                    continue
                except (ValueError, OSError, RuntimeError):
                    pass
            with self.store.connect() as db:
                state = "READY" if step["attempts"] < step["max_attempts"] else "FAILED"
                db.execute(
                    "UPDATE steps SET state=?,error=? WHERE id=?",
                    (state, "Interrupted; recovered from durable checkpoint", step["id"]),
                )
                if state == "FAILED":
                    db.execute(
                        "UPDATE jobs SET state='FAILED',error='Interrupted step exhausted retry budget' WHERE id=? AND state NOT IN ('PAUSED','CANCELLED')",
                        (step["job_id"],),
                    )
                else:
                    db.execute(
                        "UPDATE jobs SET state='QUEUED' WHERE id=? AND state='RUNNING'", (step["job_id"],)
                    )
                self.store.event(
                    db, step["project_id"], step["job_id"], "recovered", {"step": step["id"], "state": state}
                )

    def directory(self, step):
        directory = self.store.root / step["project_id"] / step["job_id"] / step["id"]
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def claim(self):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT s.*, j.project_id, j.episode, j.config FROM steps s JOIN jobs j ON j.id=s.job_id
                WHERE s.state='READY' AND j.state IN ('QUEUED','RUNNING') AND s.attempts<s.max_attempts
                AND NOT EXISTS(SELECT 1 FROM steps p WHERE p.job_id=s.job_id AND p.ordinal<s.ordinal AND p.state!='SUCCEEDED')
                ORDER BY j.created,s.ordinal LIMIT 1""").fetchone()
            if not row:
                return None
            step = dict(row)
            db.execute(
                "UPDATE steps SET state='RUNNING',attempts=attempts+1,heartbeat=? WHERE id=?",
                (time.time(), step["id"]),
            )
            db.execute("UPDATE jobs SET state='RUNNING' WHERE id=?", (step["job_id"],))
            db.execute(
                "UPDATE projects SET status=?,updated=? WHERE id=?",
                (step["stage"], time.time(), step["project_id"]),
            )
            self.store.event(
                db,
                step["project_id"],
                step["job_id"],
                "stage_started",
                {"stage": step["stage"], "label": STAGES[step["stage"]]},
            )
            step["attempts"] += 1
            step["payload"] = json.loads(step["payload"])
            return step

    def check(self, step):
        if self.stop.is_set():
            raise media.Interrupted("Shutdown requested")
        if time.monotonic() - self.last_heartbeat > 0.5:
            with self.store.connect() as db:
                row = db.execute("SELECT state FROM jobs WHERE id=?", (step["job_id"],)).fetchone()
                if row["state"] == "CANCELLED":
                    raise media.Interrupted("Cancelled")
                db.execute("UPDATE steps SET heartbeat=? WHERE id=?", (time.time(), step["id"]))
            self.last_heartbeat = time.monotonic()

    def loop(self):
        while not self.stop.is_set():
            step = self.claim()
            if not step:
                self.stop.wait(0.3)
                continue
            try:
                self.check(step)
                output = self.execute(step)
                self.check(step)
                self.verify(output)
                atomic_json(self.directory(step) / "receipt.json", output)
                self.complete(step, output)
            except media.Interrupted:
                with self.store.connect() as db:
                    job = db.execute("SELECT state FROM jobs WHERE id=?", (step["job_id"],)).fetchone()
                    db.execute(
                        "UPDATE steps SET state=? WHERE id=?",
                        ("CANCELLED" if job["state"] == "CANCELLED" else "READY", step["id"]),
                    )
            except Exception as e:
                message = str(e)[:2400]
                with self.store.connect() as db:
                    db.execute("UPDATE steps SET state='FAILED',error=? WHERE id=?", (message, step["id"]))
                    db.execute(
                        "UPDATE jobs SET state='FAILED',error=? WHERE id=? AND state!='CANCELLED'",
                        (message, step["job_id"]),
                    )
                    db.execute(
                        "UPDATE projects SET status='FAILED' WHERE id=? AND status!='CANCELLED'",
                        (step["project_id"],),
                    )
                    self.store.event(
                        db,
                        step["project_id"],
                        step["job_id"],
                        "failed",
                        {"message": message, "attempt": step["attempts"]},
                    )

    def artifact(self, step, role, path, metadata):
        return {
            "id": stable(step["id"], role),
            "role": role,
            "path": str(path.relative_to(self.store.root)),
            "sha256": digest(path),
            "metadata": {"episode": step["episode"], "schema_version": 1, **metadata},
        }

    def verify(self, output):
        for artifact in output.get("artifacts", []):
            path = self.store.resolve(artifact["path"])
            if not path.is_file() or digest(path) != artifact["sha256"]:
                raise RuntimeError("BAD_OUTPUT: A checkpoint asset is missing or its checksum changed.")

    def execute(self, step):
        project = self.store.get(step["project_id"])
        spec, stage = project["spec"], step["stage"]
        settings = self.store.settings() | json.loads(step.get("config", "{}"))
        reserve = settings["reserve_mb"] * 1024 * 1024
        if shutil.disk_usage(self.store.root).free < reserve:
            raise RuntimeError(
                "DISK_FULL: Free disk space is below the configured reserve. Free space and resume."
            )
        directory = self.directory(step)

        def check():
            self.check(step)

        if stage not in {"PLAN", "SCRIPT", "DRAFT"} or spec["backend"] == "demo":
            provider = DemoStory()
        elif settings["story_engine"] == "small_cpu":
            from studio.local_story import SmallCPUStory

            provider = SmallCPUStory(check=check)
        else:
            provider = OllamaStory(settings["story_model"], check=check)
        base = {
            "provider": "demo" if spec["backend"] == "demo" else "WanGP",
            "model": "deterministic-fixture-v1"
            if spec["backend"] == "demo"
            else "see-parent-inference-assets",
            "is_mock": spec["backend"] == "demo",
            "license": "Original app-owned development fixture"
            if spec["backend"] == "demo"
            else "WanGP Community License 2.0; individual model rights reviewed by user. Credit WanGP where required.",
            "prompt_template_version": 1,
        }
        if stage == "PLAN":
            plan = provider.plan(project)
            if len(plan.episodes) != spec["episodes"]:
                raise RuntimeError("BAD_STORY: Model did not plan the requested number of episodes.")
            return {"plan": plan.model_dump(), "artifacts": []}
        if stage in {"SCRIPT", "DRAFT"}:
            number = step["payload"]["episode"] if stage == "DRAFT" else step["episode"]
            episode = next(e for e in project["episodes"] if e["number"] == number)
            if stage == "SCRIPT" and episode["status"] == "DRAFTED" and episode["script"]:
                from studio.domain import EpisodeScript

                script = EpisodeScript.model_validate(episode["script"])
            else:
                script = provider.script(project, number)
            if script.number != number:
                raise RuntimeError("BAD_STORY: Script belongs to a different episode.")
            validate_script(script, SeasonPlan.model_validate(project["plan"]), spec["target_seconds"])
            conflicts = continuity_errors(script, project["canon"])
            if conflicts:
                raise RuntimeError("CANON_CONFLICT: " + "; ".join(conflicts))
            return {"script": script.model_dump(), "artifacts": []}
        real_provider = WanGPProvider(WanGPConfig.model_validate(settings.get("wangp", {})), self.store.root)
        size = media.SIZES[spec["orientation"]]
        payload = step["payload"]
        script = next(e["script"] for e in project["episodes"] if e["number"] == step["episode"])
        if stage in {"REFERENCE", "FRAME"}:
            path = directory / "image.png"
            if stage == "REFERENCE":
                entity = payload["entity"]
                title = entity["name"]
                prompt = entity.get("appearance", entity.get("description"))
                metadata = {"entity_id": entity["id"], "revision": 1, "prompt": prompt, "seed": 0}
            else:
                shot = payload["shot"]
                title, prompt = shot["camera"], shot["action"]
                refs = [
                    a
                    for a in project["assets"]
                    if a["role"] == "reference"
                    and a["metadata"]["entity_id"] in shot["character_ids"] + [shot["location_id"]]
                ]
                metadata = {
                    "shot_id": shot["id"],
                    "prompt": prompt,
                    "seed": shot["number"],
                    "parent_asset_ids": [a["id"] for a in refs],
                    "parent_hashes": [a["sha256"] for a in refs],
                    "reference_revision": 1,
                }
            if spec["backend"] == "demo":
                media.demo_image(path, size, title, prompt, metadata["seed"])
            else:
                references = [self.store.asset_path(aid)[0] for aid in metadata.get("parent_asset_ids", [])]
                path, real_metadata = real_provider.image(
                    prompt, directory, size, check, references=references, seed=metadata["seed"]
                )
                metadata.update(real_metadata)
            return {
                "artifacts": [
                    self.artifact(
                        step,
                        "reference" if stage == "REFERENCE" else "keyframe",
                        path,
                        {**base, **metadata, "width": size[0], "height": size[1]},
                    )
                ]
            }
        if stage == "CLIP":
            shot = payload["shot"]
            frame = next(
                a
                for a in project["assets"]
                if a["role"] == "keyframe" and a["metadata"]["shot_id"] == shot["id"]
            )
            source, _ = self.store.asset_path(frame["id"])
            if digest(source) != frame["sha256"]:
                raise RuntimeError("BAD_OUTPUT: Keyframe checksum changed")
            path = directory / "clip.partial.mp4"
            real_metadata = {}
            if spec["backend"] == "demo":
                media.demo_clip(source, path, shot["duration"], size, check)
                final = directory / "clip.mp4"
                os.replace(path, final)
            else:
                final, real_metadata = real_provider.video(
                    shot["action"] + ". " + shot["camera"],
                    source,
                    directory,
                    size,
                    shot["duration"],
                    check,
                    seed=shot["number"],
                )
            return {
                "artifacts": [
                    self.artifact(
                        step,
                        "clip",
                        final,
                        {
                            **base,
                            **real_metadata,
                            "shot_id": shot["id"],
                            "number": shot["number"],
                            "duration": shot["duration"],
                            "width": size[0],
                            "height": size[1],
                            "fps": 24,
                            "parent_asset_ids": [frame["id"]],
                            "parent_hashes": [frame["sha256"]],
                        },
                    )
                ]
            }
        if stage == "AUDIO":
            path = directory / "soundtrack.wav"
            enabled = settings["speech"] == "windows"
            timeline = media.soundtrack(script, project["plan"], path, directory, enabled, check)
            metadata = {
                "provider": "windows-speech+synthetic-ambience" if enabled else "synthetic-ambience",
                "is_mock": False,
                "dialogue_present": enabled,
                "music": "none",
                "license": "Installed Windows speech; original synthetic ambience. Voice redistribution rights require review before distribution.",
                "timeline": timeline,
                "duration": spec["target_seconds"],
            }
            return {"artifacts": [self.artifact(step, "soundtrack", path, metadata)]}
        if stage == "EXPORT":
            clips = sorted(
                [
                    a
                    for a in project["assets"]
                    if a["role"] == "clip" and a["metadata"]["episode"] == step["episode"]
                ],
                key=lambda a: a["metadata"]["number"],
            )
            if len(clips) != len(script["shots"]):
                raise RuntimeError("BAD_OUTPUT: Shot inventory incomplete")
            audio = next(
                a
                for a in project["assets"]
                if a["role"] == "soundtrack" and a["metadata"]["episode"] == step["episode"]
            )
            for asset in clips + [audio]:
                path, _ = self.store.asset_path(asset["id"])
                if digest(path) != asset["sha256"]:
                    raise RuntimeError("BAD_OUTPUT: Source media checksum changed")
            path, subtitle = directory / "movie.partial.mp4", directory / "subtitles.srt"
            media.assemble(
                [self.store.asset_path(a["id"])[0] for a in clips],
                self.store.asset_path(audio["id"])[0],
                subtitle,
                audio["metadata"]["timeline"],
                path,
                check,
            )
            validation = media.validate_video(path, size, spec["target_seconds"], audio=True)
            final = directory / "movie.mp4"
            os.replace(path, final)
            metadata = {
                **base,
                "width": size[0],
                "height": size[1],
                "duration": float(validation["format"]["duration"]),
                "fps": 24,
                "quality": "Draft demo; abstract motion storyboard, not AI generated"
                if spec["backend"] == "demo"
                else "Real local inference; draft edit; cinematic review not performed",
                "cinematic_review": "not performed",
                "parent_asset_ids": [a["id"] for a in clips] + [audio["id"]],
                "dialogue_present": audio["metadata"]["dialogue_present"],
            }
            movie = self.artifact(step, "export", final, metadata)
            manifest = directory / "manifest.json"
            atomic_json(
                manifest,
                {
                    "schema_version": 1,
                    "project": project,
                    "export": movie,
                    "edit_decision_list": script["shots"],
                    "media_probe": validation,
                },
            )
            artifacts = [movie, self.artifact(step, "manifest", manifest, base)]
            if audio["metadata"]["timeline"]:
                artifacts.append(
                    self.artifact(
                        step, "subtitles", subtitle, {"provider": "speech-timing", "is_mock": False}
                    )
                )
            return {"artifacts": artifacts}
        raise ValueError(f"Unknown stage {stage}")

    def complete(self, step, output):
        pid, jid = step["project_id"], step["job_id"]
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()
            if job["state"] == "CANCELLED":
                db.execute("UPDATE steps SET state='CANCELLED' WHERE id=?", (step["id"],))
                return
            for asset in output.get("artifacts", []):
                db.execute(
                    "INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?,?)",
                    (
                        asset["id"],
                        pid,
                        step["id"],
                        asset["role"],
                        asset["path"],
                        asset["sha256"],
                        json.dumps(asset["metadata"]),
                    ),
                )
            if step["stage"] == "PLAN":
                plan = output["plan"]
                db.execute(
                    "UPDATE projects SET plan=?,title=? WHERE id=?", (json.dumps(plan), plan["title"], pid)
                )
                for episode in plan["episodes"]:
                    db.execute(
                        "INSERT OR IGNORE INTO episodes(id,project_id,number,outline) VALUES(?,?,?,?)",
                        (
                            stable(pid, f"episode:{episode['number']}"),
                            pid,
                            episode["number"],
                            json.dumps(episode),
                        ),
                    )
                spec = json.loads(
                    db.execute("SELECT spec FROM projects WHERE id=?", (pid,)).fetchone()["spec"]
                )
                ordinal = step["ordinal"] + 1
                if spec.get("prewrite_season") and len(plan["episodes"]) > 1:
                    for episode in plan["episodes"]:
                        self.store.add_step(db, jid, ordinal, "DRAFT", {"episode": episode["number"]})
                        ordinal += 1
                self.store.add_step(db, jid, ordinal, "SCRIPT", {"episode": step["episode"]})
            elif step["stage"] == "DRAFT":
                script = output["script"]
                db.execute(
                    "UPDATE episodes SET script=?,status='DRAFTED' WHERE project_id=? AND number=?",
                    (json.dumps(script), pid, script["number"]),
                )
            elif step["stage"] == "SCRIPT":
                script = output["script"]
                db.execute(
                    "UPDATE episodes SET script=?,status='PRODUCING' WHERE project_id=? AND number=?",
                    (json.dumps(script), pid, step["episode"]),
                )
                plan = json.loads(
                    db.execute("SELECT plan FROM projects WHERE id=?", (pid,)).fetchone()["plan"]
                )
                references = {
                    json.loads(r["metadata"])["entity_id"]
                    for r in db.execute(
                        "SELECT metadata FROM assets WHERE project_id=? AND role='reference'", (pid,)
                    )
                }
                ordinal = step["ordinal"] + 1
                for entity in plan["characters"] + plan["locations"]:
                    if entity["id"] not in references:
                        self.store.add_step(db, jid, ordinal, "REFERENCE", {"entity": entity})
                        ordinal += 1
                for shot in script["shots"]:
                    for stage in ("FRAME", "CLIP"):
                        self.store.add_step(db, jid, ordinal, stage, {"shot": shot})
                        ordinal += 1
                self.store.add_step(db, jid, ordinal, "AUDIO", {})
                self.store.add_step(db, jid, ordinal + 1, "EXPORT", {})
            elif step["stage"] == "EXPORT":
                outline = json.loads(
                    db.execute(
                        "SELECT outline FROM episodes WHERE project_id=? AND number=?", (pid, step["episode"])
                    ).fetchone()["outline"]
                )
                db.execute(
                    "INSERT OR IGNORE INTO canon VALUES(?,?,?,?,?,?,?,?)",
                    (
                        stable(pid, f"outcome:{step['episode']}"),
                        pid,
                        pid,
                        step["episode"],
                        "outcome",
                        outline["outcome"],
                        "Completed episode production checkpoint",
                        1,
                    ),
                )
                db.execute(
                    "UPDATE episodes SET status='COMPLETED' WHERE project_id=? AND number=?",
                    (pid, step["episode"]),
                )
                db.execute("UPDATE jobs SET state='SUCCEEDED',error=NULL WHERE id=?", (jid,))
                db.execute("UPDATE projects SET status='COMPLETED',updated=? WHERE id=?", (time.time(), pid))
            db.execute(
                "UPDATE steps SET state='SUCCEEDED',output=?,error=NULL WHERE id=?",
                (json.dumps(output), step["id"]),
            )
            self.store.event(db, pid, jid, "stage_completed", {"stage": step["stage"], "step": step["id"]})
