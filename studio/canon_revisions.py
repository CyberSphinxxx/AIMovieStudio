"""Explicit, append-only timing corrections; original facts remain immutable."""

from pydantic import Field, field_validator

from studio.canon_timing import saved_episode_lengths
from studio.domain import StrictModel


class CanonTimingRevision(StrictModel):
    revision: int = Field(ge=1, strict=True)
    after_shot: int | None = Field(ge=0, le=120, strict=True)
    reason: str = Field(min_length=8, max_length=500)

    @field_validator("reason")
    @classmethod
    def explicit_reason(cls, value):
        if len(value.strip()) < 8:
            raise ValueError("Explain the timing correction in at least eight characters")
        return value.strip()


def assign_timing(store, pid: str, identity: str, value: CanonTimingRevision):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        project = store.get(pid)
        event = next((event for event in project["canon"] if event["id"] == identity), None)
        if event is None:
            raise KeyError(identity)
        if value.revision != project["revision"]:
            raise ValueError("Story changed in another window. Reload before editing.")
        if event["field"] not in {"alive", "location", "prop_owner", "knowledge"}:
            raise ValueError("Episode outcomes do not have a scene timing correction")
        if (
            db.execute(
                "SELECT 1 FROM jobs WHERE project_id=? AND state IN ('RUNNING','QUEUED','PAUSED','WAITING_RESOURCES')",
                (pid,),
            ).fetchone()
            or db.execute(
                "SELECT 1 FROM steps s JOIN jobs j ON j.id=s.job_id WHERE j.project_id=? AND s.state='RUNNING'",
                (pid,),
            ).fetchone()
        ):
            raise ValueError("Finish or cancel the active production before revising canon timing")
        count = saved_episode_lengths(project).get(event["episode"])
        if count is None or (value.after_shot is not None and value.after_shot > count):
            raise ValueError("Canon timing requires a reviewed saved episode with that shot checkpoint")
        affected = [
            episode["number"] for episode in project["episodes"] if episode["number"] > event["episode"]
        ]
        revision = project["revision"] + 1
        store.event(
            db,
            pid,
            None,
            "canon_timing_revision",
            {
                "event_id": identity,
                "source_canon": {
                    key: event[key]
                    for key in ("episode", "entity_id", "field", "value", "reason", "revision")
                },
                "previous_timing": {
                    key: event[key] for key in ("after_shot", "timing_status", "timing_source_seq")
                },
                "after_shot": value.after_shot,
                "reason": value.reason,
                "revision": revision,
                "affected_episodes": affected,
            },
        )
        db.execute("UPDATE projects SET revision=?,updated=strftime('%s','now') WHERE id=?", (revision, pid))
        db.execute(
            "UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number>?",
            (pid, event["episode"]),
        )
    return store.get(pid)
