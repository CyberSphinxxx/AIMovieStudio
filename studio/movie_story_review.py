"""Keep an explicitly reviewed existing movie after declared continuity checks.

This never rewrites footage or facts, and cannot assess prose or visual quality.
"""

import hashlib
import json
import math

from pydantic import Field

from studio import media
from studio.canon_timing import saved_episode_lengths
from studio.domain import EpisodeScript, SeasonPlan, StrictModel, continuity_errors, stable, validate_script
from studio.shot_revisions import latest_movie
from studio.storage import digest


class MovieStoryReview(StrictModel):
    revision: int = Field(ge=1, strict=True)
    source_export_id: str = Field(min_length=36, max_length=36)
    reviewed_movie: bool = Field(strict=True)


def candidate(project, number, request):
    if request.revision != project["revision"]:
        raise ValueError("Story changed in another window. Reload before reviewing this movie.")
    if not request.reviewed_movie:
        raise ValueError("Watch the existing movie and confirm you want to keep it before continuing")
    episode = next((episode for episode in project["episodes"] if episode["number"] == number), None)
    job = next((job for job in project["jobs"] if job["episode"] == number), None)
    if not episode or episode["status"] != "REVIEW_REQUIRED" or not episode["script"]:
        raise ValueError("Choose a saved produced episode that needs story review")
    if (
        not job
        or job["state"] != "SUCCEEDED"
        or any(step["state"] not in {"SUCCEEDED", "SUPERSEDED"} for step in job["steps"])
    ):
        raise ValueError("Finish or resolve the episode's unfinished production before reviewing its movie")
    checkpoint = next(
        (
            step
            for step in reversed(job["steps"])
            if step["stage"] == "SCRIPT" and step["state"] == "SUCCEEDED"
        ),
        None,
    )
    if (
        not checkpoint
        or not isinstance(checkpoint.get("output"), dict)
        or checkpoint["output"].get("script") != episode["script"]
    ):
        raise ValueError(
            "Saved screenplay differs from its produced checkpoint. Original movie retained; rewriting a produced story is not available yet."
        )
    if any(
        job["state"] in {"QUEUED", "RUNNING", "PAUSED", "WAITING_RESOURCES"}
        or any(step["state"] == "RUNNING" for step in job["steps"])
        for job in project["jobs"]
    ):
        raise ValueError("Finish or cancel active production before reviewing a retained movie")
    for earlier in range(1, number):
        source = next((ep for ep in project["episodes"] if ep["number"] == earlier), None)
        completed = next((job for job in project["jobs"] if job["episode"] == earlier), None)
        if (
            not source
            or source["status"] != "COMPLETED"
            or not completed
            or completed["state"] != "SUCCEEDED"
        ):
            raise ValueError("Review or finish the earlier episodes in order before keeping this movie")
    movie = latest_movie(project, number)
    if not movie or movie["id"] != request.source_export_id:
        raise ValueError("The movie cut changed. Reload before reviewing it.")
    if type(movie["metadata"].get("is_mock")) is not bool or movie["metadata"]["is_mock"] != (
        project["spec"]["backend"] == "demo"
    ):
        raise ValueError("Saved movie provider does not match the project's generation mode")
    return episode, job, movie


def check_declared_story(project, episode):
    script = EpisodeScript.model_validate(episode["script"])
    if script.number != episode["number"]:
        raise ValueError("Saved screenplay belongs to another episode")
    plan = SeasonPlan.model_validate(project["plan"])
    validate_script(script, plan, project["spec"]["target_seconds"])
    earlier = [event for event in project["canon"] if event["episode"] < episode["number"]]
    errors = continuity_errors(script, earlier, plan, episode_lengths=saved_episode_lengths(project))
    if errors:
        involved = {
            event["id"]
            for event in earlier
            if event["field"] != "outcome" and any(event["entity_id"] in error for error in errors)
        }
        evidence = f" Canon evidence: {', '.join(sorted(involved))}." if involved else ""
        raise ValueError("CANON_CONFLICT: " + "; ".join(errors) + evidence)
    expected = {}
    for index, change in enumerate(script.proposed_changes):
        expected[stable(project["id"], f"episode:{episode['number']}:change:{index}")] = (
            change.entity_id,
            change.field,
            change.value,
            f"After shot {change.after_shot}: {change.reason}",
            change.after_shot,
        )
    expected[stable(project["id"], f"outcome:{episode['number']}")] = (
        project["id"],
        "outcome",
        episode["outline"]["outcome"],
        "Completed episode production checkpoint",
        None,
    )
    own = [event for event in project["canon"] if event["episode"] == episode["number"]]
    if {event["id"] for event in own} != set(expected):
        raise ValueError(
            "CANON_CONFLICT: This episode's saved facts were revised or are missing; its original movie cannot be automatically kept"
        )
    for event in own:
        entity, field, value, reason, position = expected[event["id"]]
        if (event["entity_id"], event["field"], event["value"], event["reason"]) != (
            entity,
            field,
            value,
            reason,
        ):
            raise ValueError(f"CANON_CONFLICT: Saved fact {event['id']} differs from this movie's screenplay")
        if position is not None and not (
            event["timing_status"] == "after_shot"
            and event["after_shot"] == position
            or event["timing_status"] == "episode_end"
            and position == len(script.shots)
        ):
            raise ValueError(
                f"CANON_CONFLICT: Saved fact {event['id']} timing differs from this movie's screenplay"
            )
    return script


def verify_retained_media(store, project, episode, movie):
    assets = {asset["id"]: asset for asset in project["assets"]}
    parents = [assets.get(identity) for identity in movie["metadata"].get("parent_asset_ids", [])]
    if not parents or any(parent is None for parent in parents):
        raise ValueError("Retained movie lineage is incomplete")
    clips = [parent for parent in parents if parent["role"] in {"clip", "clip-revision"}]
    audio = [parent for parent in parents if parent["role"] == "soundtrack"]
    if (
        len(parents) != len(clips) + 1
        or len(audio) != 1
        or [parent["metadata"].get("shot_id") for parent in clips]
        != [shot["id"] for shot in episode["script"]["shots"]]
    ):
        raise ValueError("Retained movie lineage does not match the saved screenplay")
    expected_hashes = movie["metadata"].get("parent_hashes")
    if expected_hashes is not None and expected_hashes != [parent["sha256"] for parent in parents]:
        raise ValueError("Retained movie lineage checksums changed")
    for parent, seconds in [
        (clip, shot["duration"]) for clip, shot in zip(clips, episode["script"]["shots"], strict=True)
    ] + [(audio[0], project["spec"]["target_seconds"])]:
        duration = parent["metadata"].get("duration")
        if (
            parent["metadata"].get("episode") != episode["number"]
            or type(duration) not in {int, float}
            or not math.isfinite(duration)
            or abs(duration - seconds) > 0.15
        ):
            raise ValueError("Retained movie source timing does not match the saved screenplay")
    for asset in [movie, *parents]:
        path, _ = store.asset_path(asset["id"])
        if not path.is_file() or digest(path) != asset["sha256"]:
            raise ValueError("Retained movie or its source media is missing or changed")
    try:
        media.validate_video(
            store.asset_path(movie["id"])[0],
            media.SIZES[project["spec"]["orientation"]],
            project["spec"]["target_seconds"],
            audio=True,
        )
    except RuntimeError as error:
        raise ValueError(f"Retained movie could not be verified: {error}") from error


def review_movie(store, pid, number, request):
    # Slow file verification stays outside the SQLite write transaction.
    project = store.get(pid)
    episode, _, movie = candidate(project, number, request)
    check_declared_story(project, episode)
    verify_retained_media(store, project, episode, movie)
    source_script = episode["script"]
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = store.get(pid)
        saved, job, retained = candidate(current, number, request)
        if saved["script"] != source_script or retained != movie:
            raise ValueError("The saved movie or screenplay changed. Reload before reviewing it.")
        check_declared_story(current, saved)
        revision = current["revision"] + 1
        store.event(
            db,
            pid,
            job["id"],
            "movie_story_review",
            {
                "episode": number,
                "reviewed_movie": True,
                "previous_revision": current["revision"],
                "revision": revision,
                "source_export_id": movie["id"],
                "source_export_sha256": movie["sha256"],
                "source_script_step_id": next(
                    step["id"]
                    for step in reversed(job["steps"])
                    if step["stage"] == "SCRIPT" and step["state"] == "SUCCEEDED"
                ),
                "script_sha256": hashlib.sha256(
                    json.dumps(source_script, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "canon_evidence": [
                    {
                        key: event[key]
                        for key in ("id", "revision", "after_shot", "timing_status", "timing_source_seq")
                    }
                    for event in current["canon"]
                    if event["episode"] <= number
                ],
                "scope": "Explicit human keep decision; declared continuity and saved media checks, no automated prose or cinematic assessment",
            },
        )
        db.execute("UPDATE episodes SET status='COMPLETED' WHERE project_id=? AND number=?", (pid, number))
        db.execute("UPDATE projects SET revision=?,updated=strftime('%s','now') WHERE id=?", (revision, pid))
    return store.get(pid)
