"""Immutable visual retakes. Story, timing, references and canon stay pinned."""

import os
import shutil
import time

from pydantic import Field

from studio import media
from studio.domain import StrictModel, stable
from studio.providers import WanGPConfig, WanGPProvider
from studio.storage import Store, atomic_json, digest

MOVIE_ROLES = {"export", "export-edition"}
TAKE_STAGES = {"RETAKE_FRAME", "RETAKE_CLIP", "RECUT"}


class RetakeRequest(StrictModel):
    source_export_id: str = Field(min_length=36, max_length=36)
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    seed: int = Field(ge=0, le=2147483647)


def latest_movie(project: dict, episode: int):
    return next(
        (
            a
            for a in reversed(project["assets"])
            if a["role"] in MOVIE_ROLES and a["metadata"]["episode"] == episode
        ),
        None,
    )


def enqueue_retake(store: Store, pid: str, episode: int, shot_id: str, request: RetakeRequest) -> dict:
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        project = store.get(pid)
        job = next((j for j in project["jobs"] if j["episode"] == episode), None)
        if not job:
            raise ValueError("Finish this episode before requesting another take")
        for step in job["steps"]:
            if (
                step["stage"] == "RETAKE_FRAME"
                and step["payload"]["request"]["idempotency_key"] == request.idempotency_key
            ):
                if (
                    step["payload"]["request"] != request.model_dump()
                    or step["payload"]["shot"]["id"] != shot_id
                ):
                    raise ValueError("This request key belongs to a different take")
                return {"step_id": step["id"], "reused": True}
        movie = latest_movie(project, episode)
        if not movie:
            raise ValueError("Finish this episode before requesting another take")
        if request.revision != project["revision"] or request.source_export_id != movie["id"]:
            raise ValueError("This movie or its story changed. Reload before requesting another take.")
        ep = next(e for e in project["episodes"] if e["number"] == episode)
        if ep["status"] != "COMPLETED":
            raise ValueError("Resolve the episode's story review before regenerating footage")
        if any(j["state"] != "SUCCEEDED" for j in project["jobs"]):
            raise ValueError("Finish or stop and discard unfinished work before requesting another take")
        shot = next((s for s in ep["script"]["shots"] if s["id"] == shot_id), None)
        if not shot:
            raise ValueError("Unknown shot in this episode")
        used = sum(
            s["stage"] == "RETAKE_FRAME" and s["payload"]["shot"]["id"] == shot_id for s in job["steps"]
        )
        if used >= 2:
            raise ValueError("This shot has used its two retakes. Earlier cuts remain available.")
        assets = {a["id"]: a for a in project["assets"]}
        parents = [assets.get(aid) for aid in movie["metadata"]["parent_asset_ids"]]
        if any(a is None for a in parents):
            raise ValueError("Movie lineage is incomplete")
        clips = [a for a in parents if a["role"] in {"clip", "clip-revision"}]
        audio = next((a for a in parents if a["role"] == "soundtrack"), None)
        if not audio or [a["metadata"]["shot_id"] for a in clips] != [s["id"] for s in ep["script"]["shots"]]:
            raise ValueError("Movie lineage does not match the saved screenplay")
        clip = next(a for a in clips if a["metadata"]["shot_id"] == shot_id)
        frame = assets.get(clip["metadata"]["parent_asset_ids"][0])
        if not frame or frame["role"] not in {"keyframe", "keyframe-revision"}:
            raise ValueError("Shot keyframe lineage is missing")
        if request.seed == frame["metadata"]["seed"]:
            raise ValueError("Choose a different seed for another take")
        refs = [assets.get(aid) for aid in frame["metadata"]["parent_asset_ids"]]
        if not refs or any(a is None or a["role"] != "reference" for a in refs):
            raise ValueError("Pinned character/location references are missing")
        expected = set(
            shot["character_ids"]
            + [shot["location_id"]]
            + [p["prop_id"] for p in shot.get("required_props", [])]
        )
        if {a["metadata"]["entity_id"] for a in refs} != expected:
            raise ValueError("Pinned references do not match this shot")
        for asset, inputs in [(clip, [frame]), (frame, refs), (movie, parents)]:
            hashes = asset["metadata"].get("parent_hashes")
            if hashes is not None and hashes != [a["sha256"] for a in inputs]:
                raise ValueError("Pinned lineage checksums changed")
        if movie["metadata"]["is_mock"] != (project["spec"]["backend"] == "demo"):
            raise ValueError("Movie provider does not match this project's generation mode")

        def pin(asset):
            return {"id": asset["id"], "sha256": asset["sha256"]}

        payload = {
            "request": request.model_dump(),
            "shot": shot,
            "reference_inputs": [pin(a) for a in refs],
            "prompt": frame["metadata"]["prompt"],
            "source_export": pin(movie),
            "clip_inputs": [pin(a) for a in clips],
            "audio_input": pin(audio),
            "edition": movie["metadata"].get("edition", 1) + 1,
        }
        ordinal = max(s["ordinal"] for s in job["steps"]) + 1
        frame_step = store.add_step(db, job["id"], ordinal, "RETAKE_FRAME", payload)
        payload["frame_step_id"] = frame_step
        clip_step = store.add_step(db, job["id"], ordinal + 1, "RETAKE_CLIP", payload)
        payload["clip_step_id"] = clip_step
        store.add_step(db, job["id"], ordinal + 2, "RECUT", payload)
        db.execute("UPDATE jobs SET state='QUEUED',error=NULL WHERE id=?", (job["id"],))
        db.execute("UPDATE projects SET status='QUEUED',updated=? WHERE id=?", (time.time(), pid))
        store.event(
            db,
            pid,
            job["id"],
            "retake_requested",
            {"shot_id": shot_id, "edition": payload["edition"], **request.model_dump()},
        )
        return {"step_id": frame_step, "reused": False}


def discard_retake(store: Store, pid: str, episode: int):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        project = store.get(pid)
        job = next((j for j in project["jobs"] if j["episode"] == episode), None)
        if not job or not latest_movie(project, episode):
            raise ValueError("There is no completed movie to keep")
        if job["state"] not in {"PAUSED", "FAILED", "CANCELLED"} or any(
            s["state"] == "RUNNING" for s in job["steps"]
        ):
            raise ValueError("Pause the take and wait for its current step to finish before discarding")
        pending = [s for s in job["steps"] if s["state"] not in {"SUCCEEDED", "SUPERSEDED"}]
        if not pending or any(s["stage"] not in TAKE_STAGES for s in pending):
            raise ValueError("Only an unfinished visual take can be discarded")
        db.execute(
            "UPDATE steps SET state='SUPERSEDED' WHERE job_id=? AND state IN ('READY','FAILED','CANCELLED')",
            (job["id"],),
        )
        db.execute("UPDATE jobs SET state='SUCCEEDED',error=NULL WHERE id=?", (job["id"],))
        db.execute("UPDATE projects SET status='COMPLETED',updated=? WHERE id=?", (time.time(), pid))
        store.event(db, pid, job["id"], "retake_discarded", {"episode": episode})


def execute_retake(worker, project: dict, step: dict, settings: dict) -> dict:
    store, payload = worker.store, step["payload"]
    directory, size = worker.directory(step), media.SIZES[project["spec"]["orientation"]]

    def check():
        worker.check(step)

    assets = {a["id"]: a for a in project["assets"]}

    def verified(pin):
        asset = assets.get(pin["id"])
        if not asset or asset["sha256"] != pin["sha256"]:
            raise RuntimeError("BAD_OUTPUT: Pinned take input is missing or changed")
        path, _ = store.asset_path(asset["id"])
        if not path.is_file() or digest(path) != pin["sha256"]:
            raise RuntimeError("BAD_OUTPUT: Pinned take input checksum changed")
        return asset, path

    source, _ = verified(payload["source_export"])
    if project["revision"] != payload["request"]["revision"]:
        raise RuntimeError("CANON_CONFLICT: Story changed after this take was requested")
    if shutil.disk_usage(store.root).free < settings["reserve_mb"] * 1024**2 + 64 * 1024**2:
        raise RuntimeError("DISK_FULL: Retake needs 64 MB above the configured reserve")
    shot, seed = payload["shot"], payload["request"]["seed"]
    if source["metadata"]["is_mock"] != (project["spec"]["backend"] == "demo"):
        raise RuntimeError("BAD_OUTPUT: Retake provider does not match this project's generation mode")
    episode = next(e for e in project["episodes"] if e["number"] == step["episode"])
    if shot != next(s for s in episode["script"]["shots"] if s["id"] == shot["id"]):
        raise RuntimeError("CANON_CONFLICT: Saved shot changed after this take was requested")
    metadata = {
        **source["metadata"],
        "shot_id": shot["id"],
        "number": shot["number"],
        "duration": shot["duration"],
        "seed": seed,
        "edition": payload["edition"],
        "source_export_id": source["id"],
        "request_key": payload["request"]["idempotency_key"],
    }
    provider = WanGPProvider(WanGPConfig.model_validate(settings.get("wangp", {})), store.root)
    if step["stage"] == "RETAKE_FRAME":
        # Fail before expensive inference if the saved edit can no longer be rebuilt.
        for pin in [*payload["clip_inputs"], payload["audio_input"]]:
            verified(pin)
        refs = [verified(pin) for pin in payload["reference_inputs"]]
        path = directory / "image.png"
        if source["metadata"]["is_mock"]:
            media.demo_image(path, size, shot["camera"], payload["prompt"], seed)
        else:
            path, native = provider.image(
                payload["prompt"], directory, size, check, references=[path for _, path in refs], seed=seed
            )
            metadata.update(native)
        metadata.update(
            prompt=payload["prompt"],
            parent_asset_ids=[a["id"] for a, _ in refs],
            parent_hashes=[a["sha256"] for a, _ in refs],
        )
        return {"artifacts": [worker.artifact(step, "keyframe-revision", path, metadata)]}
    if step["stage"] == "RETAKE_CLIP":
        frame = assets[stable(payload["frame_step_id"], "keyframe-revision")]
        _, path = verified({"id": frame["id"], "sha256": frame["sha256"]})
        partial = directory / "clip.partial.mp4"
        if source["metadata"]["is_mock"]:
            media.demo_clip(path, partial, shot["duration"], size, check)
            final = directory / "clip.mp4"
            os.replace(partial, final)
        else:
            final, native = provider.video(
                shot["action"] + ". " + shot["camera"],
                path,
                directory,
                size,
                shot["duration"],
                check,
                seed=seed,
            )
            metadata.update(native)
        media.validate_video(final, size, shot["duration"], check=check)
        metadata.update(parent_asset_ids=[frame["id"]], parent_hashes=[frame["sha256"]])
        return {"artifacts": [worker.artifact(step, "clip-revision", final, metadata)]}
    clips = [verified(pin) for pin in payload["clip_inputs"]]
    new_clip = assets[stable(payload["clip_step_id"], "clip-revision")]
    replacement = verified({"id": new_clip["id"], "sha256": new_clip["sha256"]})
    clips = [replacement if a["metadata"]["shot_id"] == shot["id"] else (a, path) for a, path in clips]
    audio, audio_path = verified(payload["audio_input"])
    partial, final, subtitle = (
        directory / "movie.partial.mp4",
        directory / "movie.mp4",
        directory / "subtitles.srt",
    )
    media.assemble(
        [path for _, path in clips], audio_path, subtitle, audio["metadata"]["timeline"], partial, check
    )
    validation = media.validate_video(
        partial, size, project["spec"]["target_seconds"], audio=True, check=check
    )
    os.replace(partial, final)
    metadata = {
        **source["metadata"],
        "edition": payload["edition"],
        "source_export_id": source["id"],
        "retaken_shot_id": shot["id"],
        "parent_asset_ids": [a["id"] for a, _ in clips] + [audio["id"]],
        "parent_hashes": [a["sha256"] for a, _ in clips] + [audio["sha256"]],
    }
    movie = worker.artifact(step, "export-edition", final, metadata)
    manifest = directory / "manifest.json"
    atomic_json(
        manifest,
        {
            "schema_version": 1,
            "export": movie,
            "source_export_id": source["id"],
            "edit_decision_list": next(
                e["script"]["shots"] for e in project["episodes"] if e["number"] == step["episode"]
            ),
            "media_probe": validation,
        },
    )
    result = [movie, worker.artifact(step, "manifest-edition", manifest, metadata)]
    if audio["metadata"]["timeline"]:
        result.append(worker.artifact(step, "subtitles-edition", subtitle, metadata))
    return {"artifacts": result}
