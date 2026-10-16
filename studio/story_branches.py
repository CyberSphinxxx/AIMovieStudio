"""Create a separate editable story, preserving every produced original.

Only validated text is copied. This does not copy completed canon, provider
settings, media or work queues, and never starts generation.
"""

from __future__ import annotations

import hashlib
import json
import time
from uuid import UUID, uuid4

from pydantic import Field

from studio.domain import EpisodeScript, ProjectInput, SeasonPlan, StrictModel, stable, validate_script


class StoryBranchRequest(StrictModel):
    revision: int = Field(ge=1, strict=True)
    idempotency_key: UUID


def text_hash(document) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def copy_story(source, new_id):
    plan = SeasonPlan.model_validate(source["plan"])
    spec = ProjectInput.model_validate(source["spec"])
    numbers = list(range(1, spec.episodes + 1))
    if [episode["number"] for episode in source["episodes"]] != numbers or [
        episode.number for episode in plan.episodes
    ] != numbers:
        raise ValueError("Saved episodes do not match the complete season plan")
    entities = [*plan.characters, *plan.locations, *plan.props]
    ids = {entity.id: stable(new_id, f"branch-entity:{entity.id}") for entity in entities}
    copied_plan = plan.model_dump()
    copied_plan["title"] = (plan.title[:106] + " — alternative")[:120]
    for group in ("characters", "locations", "props"):
        for entity in copied_plan[group]:
            entity["id"] = ids[entity["id"]]
            if group == "props" and entity["owner_id"]:
                entity["owner_id"] = ids[entity["owner_id"]]
    target_plan = SeasonPlan.model_validate(copied_plan)
    episodes, shot_map, source_hashes = [], [], {}
    for episode in source["episodes"]:
        number = episode["number"]
        outline = target_plan.episodes[number - 1].model_dump()
        script = None
        if episode["script"]:
            original = EpisodeScript.model_validate(episode["script"])
            if original.number != number:
                raise ValueError("Saved screenplay belongs to a different episode")
            validate_script(original, plan, spec.target_seconds)
            script = original.model_dump()
            source_hashes[str(number)] = text_hash(episode["script"])
            for shot in script["shots"]:
                old = shot["id"]
                shot["id"] = stable(new_id, f"branch-shot:{number}:{old}")
                shot_map.append({"episode": number, "source": old, "target": shot["id"]})
                shot["location_id"] = ids[shot["location_id"]]
                shot["character_ids"] = [ids[identity] for identity in shot["character_ids"]]
                shot["speaker_id"] = ids[shot["speaker_id"]]
                for required in shot["required_props"]:
                    required["prop_id"] = ids[required["prop_id"]]
                    required["character_id"] = ids[required["character_id"]]
                for required in shot["required_knowledge"]:
                    required["character_id"] = ids[required["character_id"]]
            for change in script["proposed_changes"]:
                change["entity_id"] = ids[change["entity_id"]]
                if change["field"] in {"location", "prop_owner"}:
                    for field in ("before_value", "value"):
                        if change[field]:
                            change[field] = ids[change[field]]
            validate_script(EpisodeScript.model_validate(script), target_plan, spec.target_seconds)
        episodes.append({"number": number, "outline": outline, "script": script})
    if not source_hashes:
        raise ValueError("Wait for a complete saved screenplay before making an alternative story")
    return target_plan, episodes, ids, shot_map, source_hashes


def create_story_branch(store, source_id: str, request: StoryBranchRequest):
    key = "story-branch:" + str(request.idempotency_key)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT id FROM projects WHERE key=?", (key,)).fetchone()
        if previous:
            evidence = db.execute(
                "SELECT data FROM events WHERE project_id=? AND kind='story_branch_created'",
                (previous["id"],),
            ).fetchone()
            if evidence:
                data = json.loads(evidence["data"])
                if (
                    data.get("source_project_id") == source_id
                    and data.get("source_revision") == request.revision
                ):
                    return previous["id"], False
            raise ValueError("Idempotency key already belongs to another story branch")
        source = store.get(source_id)
        if source["revision"] != request.revision:
            raise ValueError("Story changed in another window. Reload before making an alternative.")
        if any(
            job["state"] in {"QUEUED", "RUNNING", "PAUSED", "WAITING_RESOURCES"}
            or any(step["state"] == "RUNNING" for step in job["steps"])
            for job in source["jobs"]
        ):
            raise ValueError("Finish or cancel active production before making an alternative story")
        if not source["plan"]:
            raise ValueError("Wait for a complete saved story plan before making an alternative")
        new_id = str(uuid4())
        plan, episodes, entities, shots, source_hashes = copy_story(source, new_id)
        spec = ProjectInput.model_validate({**source["spec"], "idempotency_key": key})
        now = time.time()
        db.execute(
            "INSERT INTO projects(id,key,spec,title,status,plan,created,updated) VALUES(?,?,?,?,?,?,?,?)",
            (new_id, key, spec.model_dump_json(), plan.title, "DRAFTED", plan.model_dump_json(), now, now),
        )
        for episode in episodes:
            db.execute(
                "INSERT INTO episodes(id,project_id,number,outline,script,status) VALUES(?,?,?,?,?,?)",
                (
                    stable(new_id, f"episode:{episode['number']}"),
                    new_id,
                    episode["number"],
                    json.dumps(episode["outline"]),
                    json.dumps(episode["script"]) if episode["script"] else None,
                    "DRAFTED" if episode["script"] else "PLANNED",
                ),
            )
        store.event(
            db,
            new_id,
            None,
            "story_branch_created",
            {
                "source_project_id": source_id,
                "source_revision": request.revision,
                "source_plan_sha256": text_hash(source["plan"]),
                "source_script_sha256": source_hashes,
                "entity_id_map": entities,
                "shot_id_map": shots,
                "copied": "Finite plan and saved screenplays only",
                "not_copied": [
                    "media",
                    "jobs",
                    "completed_canon",
                    "manual_canon_corrections",
                    "provider_settings",
                ],
                "generation_started": False,
            },
        )
    return new_id, True
