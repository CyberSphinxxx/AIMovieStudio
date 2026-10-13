"""Immutable view candidates and explicit visual choices; story canon is separate."""

from __future__ import annotations

import json
import shutil
import time
from typing import Literal

from pydantic import Field

from studio.domain import StrictModel

REFERENCE_ROLES = {"reference", "reference-variant"}
VIEW_PROMPTS = {
    "portrait": "Neutral front portrait, clear face, consistent lighting.",
    "side": "Side profile of the same character, clearly showing the face in profile.",
    "full_body": "Full body view of the same character, head and feet within frame.",
    "angle": "Another clear camera angle of the same location or object.",
}


class ReferenceVariant(StrictModel):
    source_reference_id: str = Field(min_length=36, max_length=36)
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    view: Literal["portrait", "side", "full_body", "angle"]
    seed: int = Field(ge=1, le=2147483647)


class ReferenceSelection(StrictModel):
    asset_id: str = Field(min_length=36, max_length=36)
    current_asset_id: str = Field(min_length=36, max_length=36)
    revision: int = Field(ge=1)


def entity_for(project, entity_id):
    plan = project.get("plan") or {}
    entity = next(
        (
            e
            for e in plan.get("characters", []) + plan.get("locations", []) + plan.get("props", [])
            if e["id"] == entity_id
        ),
        None,
    )
    if not entity:
        raise ValueError("Unknown story character, location or prop")
    return entity


def reference_choices(db, pid, assets):
    choices = {
        a["metadata"]["entity_id"]: {
            "asset_id": a["id"],
            "sha256": a["sha256"],
            "revision": a["metadata"].get("revision", 1),
        }
        for a in assets
        if a["role"] == "reference"
    }
    by_id = {a["id"]: a for a in assets}
    for row in db.execute(
        "SELECT data FROM events WHERE project_id=? AND kind='reference_selected' ORDER BY seq", (pid,)
    ):
        event = json.loads(row["data"])
        asset = by_id.get(event.get("asset_id"))
        if (
            not asset
            or asset["role"] not in REFERENCE_ROLES
            or asset["metadata"].get("entity_id") != event.get("entity_id")
            or asset["sha256"] != event.get("sha256")
        ):
            raise ValueError("A saved reference choice is missing or its lineage changed")
        choices[event["entity_id"]] = {
            "asset_id": asset["id"],
            "sha256": asset["sha256"],
            "revision": asset["metadata"].get("revision", 1),
        }
    return choices


def verified_asset(store, project, asset_id):
    from studio.storage import digest

    asset = next((a for a in project["assets"] if a["id"] == asset_id), None)
    if not asset or asset["role"] not in REFERENCE_ROLES:
        raise ValueError("Reference does not belong to this project")
    path, _ = store.asset_path(asset_id)
    if not path.is_file() or digest(path) != asset["sha256"]:
        raise RuntimeError("BAD_OUTPUT: Entity reference checksum changed")
    if asset["role"] == "reference-variant":
        parents = asset["metadata"].get("parent_asset_ids", [])
        parent = next((a for a in project["assets"] if len(parents) == 1 and a["id"] == parents[0]), None)
        if (
            not parent
            or parent["role"] != "reference"
            or parent["metadata"]["entity_id"] != asset["metadata"]["entity_id"]
            or asset["metadata"].get("parent_hashes") != [parent["sha256"]]
        ):
            raise RuntimeError("BAD_OUTPUT: Reference candidate lineage changed")
        source_path, _ = store.asset_path(parent["id"])
        if not source_path.is_file() or digest(source_path) != parent["sha256"]:
            raise RuntimeError("BAD_OUTPUT: Original reference checksum changed")
    return asset, path


def enqueue_variant(store, pid, entity_id, request: ReferenceVariant):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        project = store.get(pid)
        entity = entity_for(project, entity_id)
        for job in project["jobs"]:
            for step in job["steps"]:
                if (
                    step["stage"] == "REFERENCE_VARIANT"
                    and step["payload"]["request"]["idempotency_key"] == request.idempotency_key
                ):
                    if (
                        step["payload"]["request"] != request.model_dump()
                        or step["payload"]["entity"]["id"] != entity_id
                    ):
                        raise ValueError("This request key belongs to another reference view")
                    return {"step_id": step["id"], "episode": job["episode"], "reused": True}
        if request.revision != project["revision"]:
            raise ValueError("Story changed. Reload before requesting a reference view.")
        if not project["jobs"] or any(j["state"] != "SUCCEEDED" for j in project["jobs"]):
            raise ValueError("Finish or resolve unfinished production before adding reference views")
        job = project["jobs"][-1]
        episode = next(e for e in project["episodes"] if e["number"] == job["episode"])
        if episode["status"] != "COMPLETED":
            raise ValueError("Resolve this episode's story review first")
        source, _ = verified_asset(store, project, request.source_reference_id)
        if source["role"] != "reference" or source["metadata"]["entity_id"] != entity_id:
            raise ValueError("New views must use this entity's original reference")
        if source["metadata"]["is_mock"] != (project["spec"]["backend"] == "demo"):
            raise ValueError("Reference provider does not match this project")
        allowed = {"portrait", "side", "full_body"} if "appearance" in entity else {"angle"}
        if request.view not in allowed:
            raise ValueError("This view is not available for that kind of entity")
        used = sum(
            s["stage"] == "REFERENCE_VARIANT" and s["payload"]["entity"]["id"] == entity_id
            for j in project["jobs"]
            for s in j["steps"]
        )
        if used >= 3:
            raise ValueError(
                "This entity has used its three reference-view requests, including discarded requests"
            )
        ordinal = max(s["ordinal"] for s in job["steps"]) + 1
        step_id = store.add_step(
            db,
            job["id"],
            ordinal,
            "REFERENCE_VARIANT",
            {
                "request": request.model_dump(),
                "entity": entity,
                "source": {"id": source["id"], "sha256": source["sha256"]},
                "reference_revision": used + 2,
            },
        )
        db.execute("UPDATE jobs SET state='QUEUED',error=NULL WHERE id=?", (job["id"],))
        db.execute("UPDATE projects SET status='QUEUED',updated=? WHERE id=?", (time.time(), pid))
        store.event(
            db, pid, job["id"], "reference_view_requested", {"entity_id": entity_id, **request.model_dump()}
        )
        return {"step_id": step_id, "episode": job["episode"], "reused": False}


def select_reference(store, pid, entity_id, request: ReferenceSelection):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        project = store.get(pid)
        entity_for(project, entity_id)
        if request.revision != project["revision"]:
            raise ValueError("Story changed. Reload before choosing a reference.")
        if any(j["state"] != "SUCCEEDED" for j in project["jobs"]):
            raise ValueError("Finish or resolve unfinished production before changing future references")
        asset, _ = verified_asset(store, project, request.asset_id)
        if asset["metadata"]["entity_id"] != entity_id:
            raise ValueError("Reference belongs to another entity")
        if asset["metadata"]["is_mock"] != (project["spec"]["backend"] == "demo"):
            raise ValueError("Reference provider does not match this project")
        current = project["reference_choices"].get(entity_id, {}).get("asset_id")
        if current == asset["id"]:
            return {"asset_id": asset["id"], "reused": True}
        if current != request.current_asset_id:
            raise ValueError("Current reference changed. Reload before choosing a view.")
        store.event(
            db,
            pid,
            None,
            "reference_selected",
            {
                "entity_id": entity_id,
                "asset_id": asset["id"],
                "sha256": asset["sha256"],
                "previous_asset_id": current,
                "story_revision": project["revision"],
            },
        )
        db.execute("UPDATE projects SET updated=? WHERE id=?", (time.time(), pid))
        return {"asset_id": asset["id"], "reused": False}


def execute_variant(worker, project, step, settings):
    from studio import media
    from studio.providers import WanGPConfig, WanGPProvider

    payload = step["payload"]
    if (
        project["revision"] != payload["request"]["revision"]
        or entity_for(project, payload["entity"]["id"]) != payload["entity"]
    ):
        raise RuntimeError("CANON_CONFLICT: Story changed after requesting this reference view")
    source, path = verified_asset(worker.store, project, payload["source"]["id"])
    if (
        source["sha256"] != payload["source"]["sha256"]
        or source["role"] != "reference"
        or source["metadata"]["entity_id"] != payload["entity"]["id"]
    ):
        raise RuntimeError("BAD_OUTPUT: Original reference lineage changed")
    if source["metadata"]["is_mock"] != (project["spec"]["backend"] == "demo"):
        raise RuntimeError("BAD_OUTPUT: Reference provider does not match this project")
    if shutil.disk_usage(worker.store.root).free < settings["reserve_mb"] * 1024**2 + 16 * 1024**2:
        raise RuntimeError("DISK_FULL: Reference view needs 16 MB above the configured reserve")
    view, seed = payload["request"]["view"], payload["request"]["seed"]
    prompt = (
        source["metadata"]["prompt"]
        + ". "
        + VIEW_PROMPTS[view]
        + " Keep the same identity, age, hair, clothing, colors, object condition, time and weather. No redesign."
    )
    directory, size = worker.directory(step), media.SIZES[project["spec"]["orientation"]]
    output = directory / "image.png"

    def check():
        worker.check(step)

    metadata = {
        **source["metadata"],
        "entity_id": payload["entity"]["id"],
        "revision": payload["reference_revision"],
        "requested_view": view,
        "seed": seed,
        "prompt": prompt,
        "parent_asset_ids": [source["id"]],
        "parent_hashes": [source["sha256"]],
        "quality": "View/identity review not performed; candidate requires explicit selection",
    }
    if project["spec"]["backend"] == "demo":
        media.demo_image(output, size, payload["entity"]["name"] + " · " + view, prompt, seed)
    else:
        provider = WanGPProvider(WanGPConfig.model_validate(settings.get("wangp", {})), worker.store.root)
        output, native = provider.image(prompt, directory, size, check, references=[path], seed=seed)
        metadata.update(native)
    from PIL import Image

    with Image.open(output) as image:
        image.verify()
    with Image.open(output) as image:
        if image.size != size:
            raise RuntimeError("BAD_OUTPUT: Reference view dimensions do not match the requested aspect")
    return {"artifacts": [worker.artifact(step, "reference-variant", output, metadata)]}
