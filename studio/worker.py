from __future__ import annotations

import json
import os
import shutil
import threading
import time

from studio import media
from studio.inference_lock import InferenceBusy
from studio.domain import EpisodeScript, SeasonPlan, continuity_errors, stable, validate_script
from studio.script_batches import merge_sections, validate_section
from studio.continuity import draft_events
from studio.canon_timing import saved_episode_lengths
from studio.storage import Store, atomic_json, digest
from studio.story import DemoStory, OllamaStory
from studio.providers import WanGPConfig, WanGPProvider
from studio.shot_revisions import MOVIE_ROLES, TAKE_STAGES, execute_retake
from studio.reference_variants import REFERENCE_ROLES, execute_variant, verified_asset
from studio.resource_wait import (
    ResourceReason,
    ResourceWait,
    WAIT_STATE,
    WAIT_SECONDS,
    RECHECK_SECONDS,
    load_wait,
    probe,
    busy_reason,
)

STAGES = {
    "PLAN": "Preparing your story",
    "SCRIPT": "Writing the screenplay",
    "DRAFT": "Prewriting the season",
    "SCRIPT_BATCH": "Writing screenplay scenes",
    "DRAFT_BATCH": "Prewriting episode scenes",
    "REFERENCE": "Creating character references",
    "REFERENCE_VARIANT": "Creating another reference view",
    "FRAME": "Composing shot keyframes",
    "CLIP": "Animating shots",
    "AUDIO": "Building the soundtrack",
    "EXPORT": "Finishing your movie",
    "REFORMAT": "Making an export copy",
    "RETAKE_FRAME": "Composing another take",
    "RETAKE_CLIP": "Animating another take",
    "RECUT": "Saving a new movie cut",
}


class Worker:
    def __init__(self, store: Store, story_observer=None, *, wait_for_resources=True, resource_probe=None):
        self.store = store
        self.story_observer = story_observer
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.lockfile = None
        self.last_heartbeat = 0.0
        self.wait_for_resources = wait_for_resources
        self.resource_probe = resource_probe
        self.resource_rechecks = {}

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
        gpu_snapshot = None

        def gpu_reader():
            nonlocal gpu_snapshot
            if gpu_snapshot is None:
                from studio.diagnostics import hardware

                gpu_snapshot = hardware(refresh=True)["gpu"]
            return gpu_snapshot

        for _ in range(32):
            if self.stop.is_set():
                return None
            now = time.time()
            self.resource_rechecks = {jid: due for jid, due in self.resource_rechecks.items() if due > now}
            excluded = list(self.resource_rechecks)
            with self.store.connect() as db:
                row = db.execute(
                    """SELECT s.*,j.project_id,j.episode,j.config,j.state AS job_state,p.spec AS project_spec
                    FROM steps s JOIN jobs j ON j.id=s.job_id JOIN projects p ON p.id=j.project_id
                    WHERE s.state='READY' AND j.state IN ('QUEUED','RUNNING','WAITING_RESOURCES')
                    AND s.attempts<s.max_attempts
                    AND NOT (j.state='WAITING_RESOURCES' AND j.id IN (SELECT value FROM json_each(?)))
                    AND NOT EXISTS(SELECT 1 FROM steps p WHERE p.job_id=s.job_id AND p.ordinal<s.ordinal AND p.state NOT IN ('SUCCEEDED','SUPERSEDED'))
                    ORDER BY j.created,s.ordinal LIMIT 1""",
                    (json.dumps(excluded),),
                ).fetchone()
                if not row:
                    return None
                step = dict(row)
                try:
                    previous = load_wait(db, step["job_id"]) if step["job_state"] == WAIT_STATE else None
                    if step["job_state"] == WAIT_STATE and previous is None:
                        previous = "invalid"
                except ValueError:
                    previous = "invalid"
            expired = previous == "invalid" or (
                previous is not None and (previous.step_id != step["id"] or now >= previous.deadline)
            )
            reason = None
            preflight_error = None
            if not expired and self.wait_for_resources:
                try:
                    settings = self.store.settings() | json.loads(step["config"])
                    spec = json.loads(step["project_spec"])
                    reason = (
                        self.resource_probe(step, settings, spec)
                        if self.resource_probe
                        else probe(step, settings, spec, gpu_reader)
                    )
                    if reason is not None:
                        reason = ResourceReason.model_validate(reason)
                except Exception as error:
                    # A bad saved setup must fail this job, not kill the scheduler or
                    # silently turn a configuration error into a 24-hour wait.
                    preflight_error = f"RESOURCE_PREFLIGHT_FAILED: Review Settings and retry. {error}"[:2400]
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                fresh = db.execute(
                    "SELECT s.state,j.state AS job_state,j.config FROM steps s JOIN jobs j ON j.id=s.job_id WHERE s.id=?",
                    (step["id"],),
                ).fetchone()
                if (
                    not fresh
                    or fresh["state"] != "READY"
                    or fresh["job_state"] != step["job_state"]
                    or fresh["config"] != step["config"]
                    or self.stop.is_set()
                ):
                    return None
                if expired or preflight_error:
                    message = (
                        preflight_error
                        or "RESOURCE_WAIT_EXPIRED: Resource waiting ended. Review Settings and retry; your completed work is safe."
                    )
                    db.execute("UPDATE steps SET state='FAILED',error=? WHERE id=?", (message, step["id"]))
                    db.execute("UPDATE jobs SET state='FAILED',error=? WHERE id=?", (message, step["job_id"]))
                    db.execute(
                        "UPDATE projects SET status='FAILED',updated=? WHERE id=?", (now, step["project_id"])
                    )
                    self.store.event(
                        db,
                        step["project_id"],
                        step["job_id"],
                        "resource_preflight_failed" if preflight_error else "resource_wait_expired",
                        {"message": message},
                    )
                    self.resource_rechecks.pop(step["job_id"], None)
                    continue
                if reason is not None:
                    wait = ResourceWait(
                        **reason.model_dump(),
                        step_id=step["id"],
                        stage=step["stage"],
                        since=previous.since if previous else now,
                        deadline=previous.deadline if previous else now + WAIT_SECONDS,
                    )
                    if previous is None or previous.code != wait.code or previous.message != wait.message:
                        self.store.event(
                            db, step["project_id"], step["job_id"], "resource_wait", wait.model_dump()
                        )
                    db.execute(
                        "UPDATE jobs SET state='WAITING_RESOURCES',error=NULL WHERE id=?", (step["job_id"],)
                    )
                    db.execute(
                        "UPDATE projects SET status='WAITING_RESOURCES',updated=? WHERE id=?",
                        (now, step["project_id"]),
                    )
                    self.resource_rechecks[step["job_id"]] = min(now + RECHECK_SECONDS, wait.deadline)
                    continue
                if previous:
                    self.store.event(
                        db, step["project_id"], step["job_id"], "resources_ready", {"step": step["id"]}
                    )
                db.execute(
                    "UPDATE steps SET state='RUNNING',attempts=attempts+1,heartbeat=? WHERE id=?",
                    (now, step["id"]),
                )
                db.execute("UPDATE jobs SET state='RUNNING',error=NULL WHERE id=?", (step["job_id"],))
                db.execute(
                    "UPDATE projects SET status=?,updated=? WHERE id=?",
                    (step["stage"], now, step["project_id"]),
                )
                self.store.event(
                    db,
                    step["project_id"],
                    step["job_id"],
                    "stage_started",
                    {"stage": step["stage"], "label": STAGES[step["stage"]]},
                )
                self.resource_rechecks.pop(step["job_id"], None)
                step["attempts"] += 1
                step["payload"] = json.loads(step["payload"])
                step["resource_wait_before_claim"] = previous.model_dump() if previous else None
                return step
        return None

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

    def defer_inference(self, step):
        """Refund only a claim that lost ownership before any inference started."""
        now = time.time()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT s.state,s.attempts,s.output,j.state AS job_state FROM steps s "
                "JOIN jobs j ON j.id=s.job_id WHERE s.id=? AND s.job_id=?",
                (step["id"], step["job_id"]),
            ).fetchone()
            if not row or row["state"] != "RUNNING" or row["attempts"] != step["attempts"] or row["output"]:
                return
            state = "CANCELLED" if row["job_state"] == "CANCELLED" else "READY"
            db.execute(
                "UPDATE steps SET state=?,attempts=attempts-1,heartbeat=NULL,error=NULL WHERE id=?",
                (state, step["id"]),
            )
            if row["job_state"] not in {"RUNNING", "WAITING_RESOURCES"}:
                return  # Explicit Pause/Stop is authoritative.
            old = step.get("resource_wait_before_claim")
            previous = ResourceWait.model_validate(old) if old else None
            if previous and now >= previous.deadline:
                message = "RESOURCE_WAIT_EXPIRED: Review Settings and retry; your completed work is safe."
                db.execute("UPDATE jobs SET state='FAILED',error=? WHERE id=?", (message, step["job_id"]))
                db.execute("UPDATE projects SET status='FAILED' WHERE id=?", (step["project_id"],))
                db.execute("UPDATE steps SET state='FAILED',error=? WHERE id=?", (message, step["id"]))
                self.store.event(
                    db, step["project_id"], step["job_id"], "resource_wait_expired", {"message": message}
                )
                return
            wait = ResourceWait(
                **busy_reason().model_dump(),
                step_id=step["id"],
                stage=step["stage"],
                since=previous.since if previous else now,
                deadline=previous.deadline if previous else now + WAIT_SECONDS,
            )
            self.store.event(db, step["project_id"], step["job_id"], "resource_wait", wait.model_dump())
            db.execute("UPDATE jobs SET state='WAITING_RESOURCES',error=NULL WHERE id=?", (step["job_id"],))
            db.execute(
                "UPDATE projects SET status='WAITING_RESOURCES',updated=? WHERE id=?",
                (now, step["project_id"]),
            )
            self.resource_rechecks[step["job_id"]] = min(now + RECHECK_SECONDS, wait.deadline)

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
            except InferenceBusy:
                self.defer_inference(step)
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

        def story_provider():
            if spec["backend"] == "demo":
                return DemoStory()
            if settings["story_engine"] in {"small_cpu", "cpu_1_5b", "cpu_4b"}:
                from studio.local_story import SmallCPUStory

                return SmallCPUStory(
                    check=check, profile=settings["story_engine"], observer=self.story_observer
                )
            return OllamaStory(settings["story_model"], check=check)

        base = {
            "provider": "demo" if spec["backend"] == "demo" else "WanGP",
            "model": "deterministic-fixture-v1"
            if spec["backend"] == "demo"
            else "see-parent-inference-assets",
            "is_mock": spec["backend"] == "demo",
            "license": "Original app-owned development fixture"
            if spec["backend"] == "demo"
            else "WanGP Community License 2.0; individual model rights reviewed by user. Credit WanGP where required.",
            "prompt_template_version": 3,
        }
        if stage == "PLAN":
            plan = story_provider().plan(project)
            if len(plan.episodes) != spec["episodes"]:
                raise RuntimeError("BAD_STORY: Model did not plan the requested number of episodes.")
            return {"plan": plan.model_dump(), "artifacts": []}
        if stage in {"SCRIPT", "DRAFT", "SCRIPT_BATCH", "DRAFT_BATCH"}:
            number = step["payload"]["episode"] if stage.startswith("DRAFT") else step["episode"]
            episode = next(e for e in project["episodes"] if e["number"] == number)
            payload = step["payload"]
            sections = []
            for sid in payload.get("previous_batch_ids", payload.get("batch_ids", [])):
                with self.store.connect() as db:
                    row = db.execute(
                        "SELECT * FROM steps WHERE id=? AND job_id=?", (sid, step["job_id"])
                    ).fetchone()
                if not row or row["state"] != "SUCCEEDED" or not row["output"]:
                    raise RuntimeError("BAD_STORY: A required screenplay section checkpoint is missing.")
                sections.append(EpisodeScript.model_validate(json.loads(row["output"])["script"]))
            if stage == "SCRIPT" and episode["status"] == "DRAFTED" and episode["script"]:
                script = EpisodeScript.model_validate(episode["script"])
            elif stage.endswith("_BATCH"):
                section = story_provider().script_batch(
                    project, number, payload["start"], payload["count"], sections
                )
                if section.number != number:
                    raise RuntimeError("BAD_STORY: Screenplay section belongs to another episode.")
                validate_section(
                    section,
                    SeasonPlan.model_validate(project["plan"]),
                    payload["start"],
                    payload["count"],
                    spec["target_seconds"] / payload["total"],
                )
                script = merge_sections(sections + [section], number)
            elif sections:
                script = merge_sections(sections, number)
            else:
                script = story_provider().script(project, number)
            if script.number != number:
                raise RuntimeError("BAD_STORY: Script belongs to a different episode.")
            plan = SeasonPlan.model_validate(project["plan"])
            validate_script(
                script,
                plan,
                sum(s.duration for s in script.shots) if stage.endswith("_BATCH") else spec["target_seconds"],
            )
            events = project["canon"]
            if stage.startswith("DRAFT"):
                events = draft_events(project, number)
            conflicts = continuity_errors(
                script, events, plan, episode_lengths=saved_episode_lengths(project)
            )
            if conflicts:
                raise RuntimeError("CANON_CONFLICT: " + "; ".join(conflicts))
            return {"script": (section if stage.endswith("_BATCH") else script).model_dump(), "artifacts": []}
        if stage == "REFERENCE_VARIANT":
            return execute_variant(self, project, step, settings)
        if stage in TAKE_STAGES:
            return execute_retake(self, project, step, settings)
        if stage == "REFORMAT":
            # Budget beyond the reserved free space for the bounded draft copy.
            if shutil.disk_usage(self.store.root).free < reserve + 64 * 1024**2:
                raise RuntimeError("DISK_FULL: Export copy needs 64 MB above the configured disk reserve.")
            source = next((a for a in project["assets"] if a["id"] == step["payload"]["source_id"]), None)
            if (
                not source
                or source["role"] not in MOVIE_ROLES
                or source["metadata"]["episode"] != step["episode"]
            ):
                raise RuntimeError("BAD_OUTPUT: Export copy source does not belong to this episode.")
            path, _ = self.store.asset_path(source["id"])
            if not path.is_file() or digest(path) != step["payload"]["source_sha256"]:
                raise RuntimeError("BAD_OUTPUT: Original movie is missing or its checksum changed.")
            original = source["metadata"]
            source_probe = media.validate_video(
                path, (original["width"], original["height"]), original["duration"], audio=True, check=check
            )
            size = media.SIZES[step["payload"]["orientation"]]
            partial, final = directory / "copy.partial.mp4", directory / "copy.mp4"
            media.reformat(path, partial, size, check)
            validation = media.validate_video(partial, size, original["duration"], audio=True, check=check)
            source_subtitles = sum(s["codec_type"] == "subtitle" for s in source_probe["streams"])
            if sum(s["codec_type"] == "subtitle" for s in validation["streams"]) != source_subtitles:
                raise RuntimeError("BAD_OUTPUT: Export copy lost an embedded subtitle track.")
            os.replace(partial, final)
            metadata = {
                **original,
                "width": size[0],
                "height": size[1],
                "orientation": step["payload"]["orientation"],
                "reframe": "fit with black bars",
                "profile_version": 1,
                "parent_asset_ids": [source["id"]],
                "parent_hashes": [source["sha256"]],
            }
            movie = self.artifact(step, "export-variant", final, metadata)
            manifest = directory / "manifest.json"
            atomic_json(
                manifest,
                {
                    "schema_version": 1,
                    "export": movie,
                    "source_asset_id": source["id"],
                    "media_probe": validation,
                },
            )
            return {"artifacts": [movie, self.artifact(step, "manifest-variant", manifest, metadata)]}
        real_provider = WanGPProvider(WanGPConfig.model_validate(settings.get("wangp", {})), self.store.root)
        size = media.SIZES[spec["orientation"]]
        payload = step["payload"]
        script = next(e["script"] for e in project["episodes"] if e["number"] == step["episode"])
        if stage in {"REFERENCE", "FRAME"}:
            path = directory / "image.png"
            if stage == "REFERENCE":
                entity = payload["entity"]
                title = entity["name"]
                prompt = spec["style"] + ". " + entity.get("appearance", entity.get("description"))
                metadata = {"entity_id": entity["id"], "revision": 1, "prompt": prompt, "seed": 0}
            else:
                shot = payload["shot"]
                title, prompt = shot["camera"], f"{spec['style']}. {shot['camera']}. {shot['action']}"
                refs = [
                    a
                    for a in project["assets"]
                    if a["role"] == "reference"
                    and a["metadata"]["entity_id"]
                    in shot["character_ids"]
                    + [shot["location_id"]]
                    + [p["prop_id"] for p in shot.get("required_props", [])]
                ]
                if "reference_inputs" in payload:
                    refs = []
                    for pin in payload["reference_inputs"]:
                        reference = next((a for a in project["assets"] if a["id"] == pin["id"]), None)
                        if (
                            not reference
                            or reference["role"] not in REFERENCE_ROLES
                            or reference["metadata"]["entity_id"] != pin["entity_id"]
                            or (pin.get("sha256") and pin["sha256"] != reference["sha256"])
                        ):
                            raise RuntimeError("BAD_OUTPUT: Pinned reference snapshot changed")
                        refs.append(reference)
                    expected = set(
                        shot["character_ids"]
                        + [shot["location_id"]]
                        + [p["prop_id"] for p in shot.get("required_props", [])]
                    )
                    if len(refs) != len(expected) or {a["metadata"]["entity_id"] for a in refs} != expected:
                        raise RuntimeError("BAD_OUTPUT: Pinned reference snapshot does not match the shot")
                for reference in refs:
                    verified_asset(self.store, project, reference["id"])
                metadata = {
                    "shot_id": shot["id"],
                    "prompt": prompt,
                    "seed": shot["number"],
                    "parent_asset_ids": [a["id"] for a in refs],
                    "parent_hashes": [a["sha256"] for a in refs],
                    "reference_revision": 1,
                    "reference_versions": {
                        a["metadata"]["entity_id"]: a["metadata"].get("revision", 1) for a in refs
                    },
                }
            if spec["backend"] == "demo":
                media.demo_image(path, size, title, prompt, metadata["seed"])
                metadata["demo_layout_version"] = media.DEMO_LAYOUT_VERSION
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
            from studio.sound_effects import ProceduralSound, RIGHTS, VERSION

            # Older jobs without the frozen option retain their original audio behavior.
            cues = (
                ProceduralSound().cues(script["shots"])
                if json.loads(step.get("config", "{}")).get("sound_effects", False)
                else []
            )
            effect_path = directory / "sound-effects.wav" if cues else None
            if effect_path:
                ProceduralSound().render(cues, spec["target_seconds"], effect_path, check)
            normalize_audio = json.loads(step.get("config", "{}")).get("balanced_audio", False)
            mix_path = directory / "unbalanced-mix.wav" if normalize_audio else path
            timeline = media.soundtrack(
                script, project["plan"], mix_path, directory, enabled, check, effects=effect_path
            )
            from studio.loudness import balance

            loudness = balance(mix_path, path, bool(timeline), check) if normalize_audio else None
            metadata = {
                "provider": "windows-speech+synthetic-ambience" if timeline else "synthetic-ambience",
                "is_mock": False,
                "dialogue_present": bool(timeline),
                "music": "none",
                "loudness": loudness,
                "sound_effects": [c.model_dump() for c in cues],
                "sound_library": VERSION if cues else None,
                "sound_effects_rights": RIGHTS if cues else None,
                "sound_effects_method": "Conservative action matching; original procedural synthesis; no AI sound model"
                if cues
                else "none",
                "license": "Installed Windows speech; original synthetic ambience. Voice redistribution rights require review before distribution.",
                "timeline": timeline,
                "duration": spec["target_seconds"],
            }
            stems = [
                self.artifact(
                    step,
                    role,
                    directory / filename,
                    {
                        "provider": "windows-speech" if role.startswith("voice-") else "studio-audio",
                        "is_mock": False,
                        "audio_kind": role,
                        "license": metadata["license"],
                        **timing,
                    },
                )
                for role, filename, timing in [
                    (
                        "dialogue",
                        "dialogue.wav",
                        {"duration": spec["target_seconds"], "dialogue_present": bool(timeline)},
                    ),
                    ("ambience", "ambience.wav", {"duration": spec["target_seconds"]}),
                    *[
                        (
                            f"voice-{t['shot_number']}",
                            t["raw_voice_file"],
                            {
                                "speaker_id": t["speaker_id"],
                                "shot_number": t["shot_number"],
                                "text": t["text"],
                                "duration": t["raw_duration"],
                                "tempo": t["tempo"],
                            },
                        )
                        for t in timeline
                    ],
                ]
            ]
            if effect_path:
                stems.append(
                    self.artifact(
                        step,
                        "sound-effects",
                        effect_path,
                        {
                            "provider": VERSION,
                            "is_mock": False,
                            "audio_kind": "sound-effects",
                            "license": RIGHTS,
                            "duration": spec["target_seconds"],
                            "cues": [c.model_dump() for c in cues],
                        },
                    )
                )
            if normalize_audio:
                stems.append(
                    self.artifact(
                        step,
                        "unbalanced-mix",
                        mix_path,
                        {
                            "provider": "studio-audio",
                            "is_mock": False,
                            "audio_kind": "unbalanced-mix",
                            "license": metadata["license"],
                            "duration": spec["target_seconds"],
                            "parent_asset_ids": [a["id"] for a in stems],
                            "parent_hashes": [a["sha256"] for a in stems],
                        },
                    )
                )
            metadata.update(
                parent_asset_ids=[a["id"] for a in stems], parent_hashes=[a["sha256"] for a in stems]
            )
            return {"artifacts": [*stems, self.artifact(step, "soundtrack", path, metadata)]}
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
                "sound_effects_present": bool(audio["metadata"].get("sound_effects")),
                "loudness": audio["metadata"].get("loudness"),
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
            if step["stage"] == "REFERENCE_VARIANT":
                payload = (
                    step["payload"] if isinstance(step["payload"], dict) else json.loads(step["payload"])
                )
                revision = db.execute("SELECT revision FROM projects WHERE id=?", (pid,)).fetchone()[0]
                if revision != payload["request"]["revision"]:
                    raise RuntimeError("CANON_CONFLICT: Story changed before publishing this reference view")
                source, _ = verified_asset(self.store, self.store.get(pid), payload["source"]["id"])
                if source["sha256"] != payload["source"]["sha256"]:
                    raise RuntimeError("BAD_OUTPUT: Original reference changed before publication")
            if step["stage"] in TAKE_STAGES:
                payload = step["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                revision = db.execute("SELECT revision FROM projects WHERE id=?", (pid,)).fetchone()[0]
                source = db.execute(
                    "SELECT a.id FROM assets a JOIN steps s ON s.id=a.step_id "
                    "WHERE a.project_id=? AND s.job_id=? AND a.role IN ('export','export-edition') "
                    "ORDER BY a.rowid DESC LIMIT 1",
                    (pid, jid),
                ).fetchone()
                if (
                    revision != payload["request"]["revision"]
                    or not source
                    or source[0] != payload["source_export"]["id"]
                ):
                    raise RuntimeError("CANON_CONFLICT: Movie or story changed before publishing this take")
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
                        ordinal = self.store.add_story_steps(
                            db, jid, ordinal, episode["number"], spec, draft=True
                        )
                self.store.add_story_steps(
                    db,
                    jid,
                    ordinal,
                    step["episode"],
                    spec,
                    reuse=bool(spec.get("prewrite_season") and len(plan["episodes"]) > 1),
                )
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
                snapshot = self.store.get(pid)
                references = {
                    entity_id: {"entity_id": entity_id, "id": choice["asset_id"], "sha256": choice["sha256"]}
                    for entity_id, choice in snapshot["reference_choices"].items()
                }
                ordinal = step["ordinal"] + 1
                # Speech timing is cheap to check before any GPU visual generation.
                self.store.add_step(db, jid, ordinal, "AUDIO", {})
                ordinal += 1
                for entity in plan["characters"] + plan["locations"] + plan.get("props", []):
                    if entity["id"] not in references:
                        reference_step = self.store.add_step(
                            db, jid, ordinal, "REFERENCE", {"entity": entity}
                        )
                        references[entity["id"]] = {
                            "entity_id": entity["id"],
                            "id": stable(reference_step, "reference"),
                            "sha256": None,
                        }
                        ordinal += 1
                for shot in script["shots"]:
                    entities = list(
                        dict.fromkeys(
                            shot["character_ids"]
                            + [shot["location_id"]]
                            + [p["prop_id"] for p in shot.get("required_props", [])]
                        )
                    )
                    for stage in ("FRAME", "CLIP"):
                        self.store.add_step(
                            db,
                            jid,
                            ordinal,
                            stage,
                            {"shot": shot, "reference_inputs": [references[eid] for eid in entities]},
                        )
                        ordinal += 1
                self.store.add_step(db, jid, ordinal, "EXPORT", {})
                spec = json.loads(
                    db.execute("SELECT spec FROM projects WHERE id=?", (pid,)).fetchone()["spec"]
                )
                if spec.get("review_story") and not step["payload"].get("reviewed_edit"):
                    db.execute("UPDATE jobs SET state='PAUSED' WHERE id=?", (jid,))
                    db.execute("UPDATE projects SET status='PAUSED' WHERE id=?", (pid,))
                    self.store.event(db, pid, jid, "story_review_ready", {"episode": step["episode"]})
            elif step["stage"] in {"REFORMAT", "RECUT", "REFERENCE_VARIANT"}:
                # Export-only work never recommits story facts or episode outcomes.
                db.execute("UPDATE jobs SET state='SUCCEEDED',error=NULL WHERE id=?", (jid,))
                db.execute("UPDATE projects SET status='COMPLETED',updated=? WHERE id=?", (time.time(), pid))
            elif step["stage"] == "EXPORT":
                episode_row = db.execute(
                    "SELECT outline,script FROM episodes WHERE project_id=? AND number=?",
                    (pid, step["episode"]),
                ).fetchone()
                outline = json.loads(episode_row["outline"])
                script = json.loads(episode_row["script"])
                revision = db.execute("SELECT revision FROM projects WHERE id=?", (pid,)).fetchone()[
                    "revision"
                ]
                changes = sorted(
                    enumerate(script.get("proposed_changes", [])), key=lambda item: item[1]["after_shot"]
                )
                for index, change in changes:
                    event_id = stable(pid, f"episode:{step['episode']}:change:{index}")
                    inserted = db.execute(
                        "INSERT OR IGNORE INTO canon VALUES(?,?,?,?,?,?,?,?)",
                        (
                            event_id,
                            pid,
                            change["entity_id"],
                            step["episode"],
                            change["field"],
                            change["value"],
                            f"After shot {change['after_shot']}: {change['reason']}",
                            revision,
                        ),
                    )
                    # Source/before-state details stay in the append-only event log and script.
                    if inserted.rowcount:
                        self.store.event(
                            db,
                            pid,
                            jid,
                            "canon_committed",
                            {
                                "event_id": event_id,
                                "source_step_id": step["id"],
                                "episode": step["episode"],
                                "change": change,
                            },
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
