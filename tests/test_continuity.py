import json

import pytest

from studio.domain import CanonChange, KnowledgeUse, Prop, PropUse, continuity_errors, stable, validate_script
from studio.story import DemoStory
from studio.worker import Worker
from studio.storage import Store
from studio.api import create_app
from fastapi.testclient import TestClient
from tests.test_pipeline import produce_until, set_silent

FACT = "The signal comes from the hidden chamber."


def fixture_story(store, spec):
    spec.kind, spec.episodes, spec.target_seconds = "series", 2, 10
    pid, _ = store.create(spec)
    project = store.get(pid)
    plan = DemoStory().plan(project)
    plan.props = [
        Prop(
            id=stable(pid, "compass"),
            name="Silver compass",
            description="A silver compass with a cracked glass face",
            owner_id=plan.characters[0].id,
        )
    ]
    project["plan"] = plan.model_dump()
    return project, plan, DemoStory().script(project, 1)


def test_prop_transfer_and_learning_must_precede_use(store, spec):
    project, plan, script = fixture_story(store, spec)
    hero, guide = [c.id for c in plan.characters]
    prop = plan.props[0].id
    script.shots[0].required_props = [PropUse(prop_id=prop, character_id=hero)]
    script.shots[1].required_props = [PropUse(prop_id=prop, character_id=guide)]
    script.shots[1].required_knowledge = [KnowledgeUse(character_id=guide, fact=FACT)]
    errors = continuity_errors(script, [], plan)
    assert any("belongs" in e and "Shot 2" in e for e in errors)
    assert any("has not learned" in e for e in errors)
    script.proposed_changes = [
        CanonChange(
            after_shot=1,
            entity_id=prop,
            field="prop_owner",
            before_value=hero,
            value=guide,
            reason="Mara hands the compass to Eli.",
        ),
        CanonChange(
            after_shot=1,
            entity_id=guide,
            field="knowledge",
            before_value="unknown",
            value=FACT,
            reason="Mara shows Eli the signal's source.",
        ),
    ]
    validate_script(script, plan, 10)
    assert not continuity_errors(script, [], plan)
    script.proposed_changes[0].after_shot = 2
    assert any("transfer it before use" in e for e in continuity_errors(script, [], plan))
    script.proposed_changes[0].after_shot = 1
    script.proposed_changes[0].before_value = guide
    assert any("before-state" in e for e in continuity_errors(script, [], plan))


def test_future_knowledge_is_not_current_knowledge(store, spec):
    _, plan, script = fixture_story(store, spec)
    hero = plan.characters[0].id
    script.shots[0].required_knowledge = [KnowledgeUse(character_id=hero, fact=FACT)]
    future = [{"episode": 2, "entity_id": hero, "field": "knowledge", "value": FACT}]
    assert continuity_errors(script, future, plan)
    plan.characters[0].initial_knowledge = [FACT]
    assert not continuity_errors(script, future, plan)


def test_dead_offscreen_speaker_and_explicit_flashback(store, spec):
    _, plan, script = fixture_story(store, spec)
    hero, guide = [c.id for c in plan.characters]
    script.number = 2
    script.shots[0].character_ids = [guide]
    script.shots[0].speaker_id = hero
    death = [{"episode": 1, "entity_id": hero, "field": "alive", "value": "false"}]
    assert any(hero in e and "Shot 1" in e for e in continuity_errors(script, death, plan))
    script.shots[0].flashback_episode = 1
    script.shots[0].continuity_note = "Before the fatal journey in chapter one."
    validate_script(script, plan, 10)
    assert not continuity_errors(script, death, plan)
    script.proposed_changes = [
        CanonChange(
            after_shot=1,
            entity_id=hero,
            field="alive",
            before_value="false",
            value="true",
            reason="A memory does not revive the keeper.",
        )
    ]
    with pytest.raises(ValueError, match="Flashback changes"):
        validate_script(script, plan, 10)
    script.proposed_changes = []
    script.shots[0].flashback_episode = 2
    with pytest.raises(ValueError, match="earlier episode"):
        validate_script(script, plan, 10)


def test_declared_move_and_death_within_episode(store, spec):
    _, plan, script = fixture_story(store, spec)
    hero = plan.characters[0].id
    script.shots[1].character_ids = [hero]
    script.shots[1].speaker_id = hero
    script.shots[1].location_id = plan.locations[1].id
    events = [{"episode": 1, "entity_id": hero, "field": "location", "value": plan.locations[0].id}]
    script.number = 2
    assert any("declare a move" in e for e in continuity_errors(script, events, plan))
    script.proposed_changes = [
        CanonChange(
            after_shot=1,
            entity_id=hero,
            field="location",
            before_value=plan.locations[0].id,
            value=plan.locations[1].id,
            reason="Mara walks from the station into the chamber.",
        )
    ]
    assert not continuity_errors(script, events, plan)
    script.proposed_changes.append(
        CanonChange(
            after_shot=1,
            entity_id=hero,
            field="alive",
            before_value="true",
            value="false",
            reason="Mara dies after entering the chamber.",
        )
    )
    assert any("is dead" in e for e in continuity_errors(script, events, plan))


def test_prewrite_changes_remain_proposals_until_completed_export(store, spec, monkeypatch):
    spec.kind, spec.episodes, spec.target_seconds, spec.prewrite_season = "series", 2, 10, True
    original_plan, original_script = DemoStory.plan, DemoStory.script

    def plan_with_prop(self, project):
        plan = original_plan(self, project)
        plan.props = [
            Prop(
                id=stable(project["id"], "compass"),
                name="Silver compass",
                description="A silver compass with a cracked glass face",
                owner_id=plan.characters[0].id,
            )
        ]
        return plan

    def causal_script(self, project, number):
        script = original_script(self, project, number)
        hero, guide = [c["id"] for c in project["plan"]["characters"]]
        prop = project["plan"]["props"][0]["id"]
        if number == 1:
            script.shots[0].required_props = [PropUse(prop_id=prop, character_id=hero)]
            script.proposed_changes = [
                CanonChange(
                    after_shot=1,
                    entity_id=prop,
                    field="prop_owner",
                    before_value=hero,
                    value=guide,
                    reason="Mara hands the silver compass to Eli.",
                ),
                CanonChange(
                    after_shot=1,
                    entity_id=guide,
                    field="knowledge",
                    before_value="unknown",
                    value=FACT,
                    reason="Mara reveals the source of the signal.",
                ),
            ]
        else:
            script.shots[0].character_ids = [guide]
            script.shots[0].speaker_id = guide
        script.shots[1].required_props = [PropUse(prop_id=prop, character_id=guide)]
        script.shots[1].required_knowledge = [KnowledgeUse(character_id=guide, fact=FACT)]
        return script

    monkeypatch.setattr(DemoStory, "plan", plan_with_prop)
    monkeypatch.setattr(DemoStory, "script", causal_script)
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    drafted = produce_until(store, worker, pid, "DRAFT", 2)
    assert not drafted["canon"] and not drafted["assets"]
    saved = drafted["episodes"][1]["script"]
    completed = produce_until(store, worker, pid)
    assert len(completed["canon"]) == 3  # outcome + transfer + learned fact
    prop = completed["plan"]["props"][0]["id"]
    reference = next(
        a for a in completed["assets"] if a["role"] == "reference" and a["metadata"]["entity_id"] == prop
    )
    frame2 = next(a for a in completed["assets"] if a["role"] == "keyframe" and a["metadata"]["seed"] == 2)
    assert reference["id"] in frame2["metadata"]["parent_asset_ids"]
    assert spec.style in frame2["metadata"]["prompt"]
    assert "Close-up" in frame2["metadata"]["prompt"]
    reopened = Store(store.root)
    reopened.enqueue(pid, 2)
    result = produce_until(reopened, Worker(reopened), pid)
    assert result["episodes"][1]["script"] == saved
    assert len(result["canon"]) == 4
    with reopened.connect() as db:
        details = [
            json.loads(r[0]) for r in db.execute("SELECT data FROM events WHERE kind='canon_committed'")
        ]
    assert len(details) == 2
    assert all(d["source_step_id"] and d["change"]["before_value"] for d in details)


def test_corrupt_reference_is_rejected_before_keyframe_generation(store, spec):
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    project = produce_until(store, worker, pid, "REFERENCE", 4)
    reference = project["assets"][
        next(i for i, a in enumerate(project["assets"]) if a["role"] == "reference")
    ]
    path, _ = store.asset_path(reference["id"])
    path.write_bytes(b"changed reference")
    step = worker.claim()
    assert step["stage"] == "FRAME"
    with pytest.raises(RuntimeError, match="reference checksum"):
        worker.execute(step)


def test_manual_canon_revisions_validate_prop_owner_and_life_values(store, spec):
    project, plan, _ = fixture_story(store, spec)
    pid = project["id"]
    with store.connect() as db:
        db.execute("UPDATE projects SET plan=? WHERE id=?", (plan.model_dump_json(), pid))
    with TestClient(create_app(store.root, run_worker=False)) as client:

        def revise(entity, field, value):
            return client.post(
                f"/api/projects/{pid}/canon",
                json={
                    "revision": 1,
                    "event": {
                        "entity_id": entity,
                        "episode": 1,
                        "field": field,
                        "value": value,
                        "reason": "Explicit continuity correction",
                    },
                },
            )

        assert revise(plan.props[0].id, "prop_owner", "missing-actor").status_code == 409
        assert revise(plan.characters[0].id, "alive", "maybe").status_code == 409
        assert store.get(pid)["revision"] == 1 and not store.get(pid)["canon"]
        assert revise(plan.props[0].id, "prop_owner", plan.characters[1].id).status_code == 200
        assert store.get(pid)["revision"] == 2
