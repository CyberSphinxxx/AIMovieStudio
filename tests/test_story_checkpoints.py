"""Declared chronology fixtures, not native writing or semantic prose proof."""

import json

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.canon_timing import with_timing
from studio.domain import (
    CanonChange,
    EpisodeScript,
    KnowledgeUse,
    Prop,
    PropUse,
    continuity_errors,
    stable,
    validate_script,
)
from studio.storage import Store, digest
from studio.story import DemoStory
from studio.worker import Worker
from tests.test_continuity import fixture_story
from tests.test_pipeline import produce_until, set_silent


def precise_flashback(store, spec, checkpoint):
    _, plan, original = fixture_story(store, spec)
    value = original.model_dump()
    value["number"] = 2
    value["shots"][0].update(
        flashback_episode=1,
        flashback_after_shot=checkpoint,
        continuity_note="An explicit memory after the compass changes hands.",
    )
    return plan, EpisodeScript.model_validate(value)


def test_precise_flashback_uses_acquired_prop_before_later_transfer(store, spec):
    plan, script = precise_flashback(store, spec, 1)
    hero, guide = [c.id for c in plan.characters]
    prop = plan.props[0].id
    script.shots[0].character_ids = [guide]
    script.shots[0].speaker_id = guide
    script.shots[0].required_props = [PropUse(prop_id=prop, character_id=guide)]
    events = [
        {"episode": 1, "after_shot": 1, "entity_id": prop, "field": "prop_owner", "value": guide},
        {"episode": 1, "after_shot": 2, "entity_id": prop, "field": "prop_owner", "value": hero},
    ]
    validate_script(script, plan, 10)
    assert not continuity_errors(script, events, plan, episode_lengths={1: 2})
    script.shots[0].flashback_after_shot = 2
    assert any("belongs" in e for e in continuity_errors(script, events, plan, episode_lengths={1: 2}))


def test_checkpoint_cannot_name_missing_past_shot(store, spec):
    plan, script = precise_flashback(store, spec, 3)
    errors = continuity_errors(script, [], plan, episode_lengths={1: 2})
    assert any("checkpoint" in e.lower() and "3" in e for e in errors)


@pytest.mark.parametrize("checkpoint,learned", [(0, False), (1, True), (2, True)])
def test_learning_checkpoint_does_not_leak_later_or_future_knowledge(store, spec, checkpoint, learned):
    plan, script = precise_flashback(store, spec, checkpoint)
    hero = plan.characters[0].id
    fact = "The compass points toward the hidden chamber."
    script.shots[0].required_knowledge = [KnowledgeUse(character_id=hero, fact=fact)]
    events = [
        {"episode": 1, "after_shot": 1, "entity_id": hero, "field": "knowledge", "value": fact},
        {
            "episode": 3,
            "after_shot": 0,
            "entity_id": hero,
            "field": "knowledge",
            "value": "An unrelated future secret.",
        },
    ]
    errors = continuity_errors(script, events, plan, episode_lengths={1: 2})
    assert any("has not learned" in e for e in errors) is not learned


def test_death_checkpoint_and_legacy_episode_start_are_distinct(store, spec):
    plan, script = precise_flashback(store, spec, 0)
    hero, guide = [c.id for c in plan.characters]
    script.shots[1].character_ids = [guide]
    script.shots[1].speaker_id = guide
    death = [{"episode": 1, "after_shot": 1, "entity_id": hero, "field": "alive", "value": "false"}]
    assert not continuity_errors(script, death, plan, episode_lengths={1: 2})
    script.shots[0].flashback_after_shot = 1
    assert any("is dead" in e for e in continuity_errors(script, death, plan, episode_lengths={1: 2}))
    script.shots[0].flashback_after_shot = None
    assert not continuity_errors(script, death, plan)


def test_exact_checkpoint_refuses_only_relevant_unknown_history(store, spec):
    plan, script = precise_flashback(store, spec, 1)
    hero, guide = [c.id for c in plan.characters]
    unknown = [
        {"id": "unverified-death", "episode": 1, "entity_id": hero, "field": "alive", "value": "false"}
    ]
    script.shots[1].character_ids = [guide]
    script.shots[1].speaker_id = guide
    errors = continuity_errors(script, unknown, plan, episode_lengths={1: 2})
    assert any("unverified-death" in e and "no verified shot timing" in e for e in errors)
    script.shots[0].character_ids = [guide]
    script.shots[0].narration = ""  # Unused dead speaker must remain absent.
    assert not continuity_errors(script, unknown, plan, episode_lengths={1: 2})
    assert any("saved episode" in e for e in continuity_errors(script, [], plan))


def test_checkpoint_without_episode_and_changes_from_flashbacks_remain_invalid(store, spec):
    plan, script = precise_flashback(store, spec, 0)
    script.shots[0].flashback_episode = None
    with pytest.raises(ValueError, match="requires an earlier"):
        validate_script(script, plan, 10)
    script.shots[0].flashback_episode = 1
    script.proposed_changes = [
        CanonChange(
            after_shot=1,
            entity_id=plan.characters[0].id,
            field="alive",
            before_value="true",
            value="false",
            reason="A memory cannot kill the present character.",
        )
    ]
    with pytest.raises(ValueError, match="Flashback changes"):
        validate_script(script, plan, 10)


def test_linked_timing_requires_matching_immutable_source_and_handles_legacy_revisions():
    row = {
        "id": "death",
        "episode": 1,
        "entity_id": "hero",
        "field": "alive",
        "value": "false",
        "reason": "After shot 2: The keeper dies.",
        "revision": 1,
    }
    source = {
        "seq": 5,
        "kind": "canon_committed",
        "data": json.dumps(
            {
                "event_id": "death",
                "episode": 1,
                "change": {
                    "entity_id": "hero",
                    "field": "alive",
                    "value": "false",
                    "after_shot": 2,
                    "reason": "The keeper dies.",
                },
            }
        ),
    }
    result = with_timing([row], [source])[0]
    assert result["after_shot"] == 2 and result["timing_source_seq"] == 5
    assert row.keys() == {"id", "episode", "entity_id", "field", "value", "reason", "revision"}
    bad = json.loads(source["data"])
    bad["change"]["after_shot"] = 1
    assert with_timing([row], [source | {"data": json.dumps(bad)}])[0]["timing_status"] == "episode_only"
    assert with_timing([row], [source | {"data": "not JSON"}])[0]["timing_status"] == "episode_only"
    manual = row | {"id": "revision", "reason": "Correct the whole episode outcome.", "revision": 2}
    evidence = {
        "seq": 6,
        "kind": "canon_revision",
        "data": json.dumps(
            {
                "revision": 2,
                "event": {key: manual[key] for key in ("episode", "entity_id", "field", "value", "reason")},
            }
        ),
    }
    assert with_timing([manual], [evidence])[0]["timing_status"] == "episode_end"
    assert (
        with_timing([manual, manual | {"id": "ambiguous"}], [evidence])[0]["timing_status"] == "episode_only"
    )


def test_known_shot_time_wins_over_insertion_order_and_end_revision_stays_at_end(store, spec):
    plan, script = precise_flashback(store, spec, 1)
    hero, guide = [c.id for c in plan.characters]
    prop = plan.props[0].id
    script.shots[0].character_ids = [guide]
    script.shots[0].speaker_id = guide
    script.shots[0].required_props = [PropUse(prop_id=prop, character_id=guide)]
    events = [
        {
            "episode": 1,
            "after_shot": None,
            "timing_status": "episode_end",
            "entity_id": prop,
            "field": "prop_owner",
            "value": hero,
        },
        {"episode": 1, "after_shot": 1, "entity_id": prop, "field": "prop_owner", "value": guide},
    ]
    assert not continuity_errors(script, events, plan, episode_lengths={1: 2})
    script.shots[0].flashback_after_shot = 2
    assert any("belongs" in e for e in continuity_errors(script, events, plan, episode_lengths={1: 2}))


def api_fixture(store, spec):
    project, plan, script = fixture_story(store, spec)
    pid = project["id"]
    with store.connect() as db:
        db.execute("UPDATE projects SET plan=? WHERE id=?", (plan.model_dump_json(), pid))
        for outline in plan.episodes:
            db.execute(
                "INSERT INTO episodes VALUES(?,?,?,?,?,?)",
                (
                    stable(pid, f"episode:{outline.number}"),
                    pid,
                    outline.number,
                    outline.model_dump_json(),
                    script.model_dump_json() if outline.number == 1 else None,
                    "DRAFTED" if outline.number == 1 else "PLANNED",
                ),
            )
    return pid, plan, script


@pytest.mark.parametrize("fault", ["missing_script", "missing_shot", "outcome", "stale"])
def test_invalid_explicit_canon_timing_rolls_back_all_state(store, spec, fault):
    pid, plan, script = api_fixture(store, spec)
    event = {
        "entity_id": plan.characters[0].id,
        "episode": 1,
        "field": "alive",
        "value": "false",
        "reason": "The keeper dies after the gate closes.",
        "after_shot": 1,
    }
    revision = 1
    if fault == "missing_script":
        event["episode"] = 2
    elif fault == "missing_shot":
        event["after_shot"] = 3
    elif fault == "outcome":
        event.update(entity_id=pid, field="outcome", value="A new ending")
    elif fault == "stale":
        revision = 99
    before = store.get(pid)
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.post(f"/api/projects/{pid}/canon", json={"revision": revision, "event": event})
    assert result.status_code == 409, result.text
    assert store.get(pid) == before


def test_explicit_revision_timing_survives_reopen_and_backup_without_changing_original_script(
    store, spec, tmp_path
):
    pid, plan, script = api_fixture(store, spec)
    event = {
        "entity_id": plan.characters[0].id,
        "episode": 1,
        "field": "alive",
        "value": "false",
        "reason": "The keeper dies after the final door closes.",
        "after_shot": 2,
    }
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.post(f"/api/projects/{pid}/canon", json={"revision": 1, "event": event})
    assert result.status_code == 200, result.text
    project = Store(store.root).get(pid)
    assert project["canon"][0]["id"] == result.json()["event_id"]
    assert project["canon"][0]["after_shot"] == 2 and project["canon"][0]["timing_status"] == "after_shot"
    assert project["episodes"][0]["script"] == script.model_dump()
    assert project["episodes"][1]["status"] == "REVIEW_REQUIRED"
    archive = create_backup(store, tmp_path / "timed-revision.zip")
    restored = restore_backup(archive, tmp_path / "restored-revision")
    assert restored.get(pid)["canon"] == project["canon"]


def test_sparse_edit_preserves_the_checkpoint_and_readable_screenplay_time(store, spec):
    pid, plan, _ = api_fixture(store, spec)
    script = DemoStory().script(store.get(pid), 2)
    script.shots[0].flashback_episode = 1
    script.shots[0].flashback_after_shot = 1
    script.shots[0].continuity_note = "A memory after the first chamber visit."
    with store.connect() as db:
        db.execute(
            "UPDATE episodes SET script=?,status='DRAFTED' WHERE project_id=? AND number=2",
            (script.model_dump_json(), pid),
        )
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.patch(
            f"/api/projects/{pid}/episodes/2/draft",
            json={
                "revision": 1,
                "edits": [{"shot_id": script.shots[0].id, "narration": "I remember the door opening."}],
            },
        )
    assert result.status_code == 200, result.text
    edited = result.json()["episodes"][1]["script"]
    assert edited["shots"][0]["flashback_after_shot"] == 1
    assert "Flashback — Episode 1, after shot 1." in edited["screenplay"]
    assert edited["shots"][0]["id"] == script.shots[0].id
    with store.connect() as db:
        history = json.loads(db.execute("SELECT data FROM events WHERE kind='draft_revision'").fetchone()[0])
    assert history["original_script"] == script.model_dump()


@pytest.mark.parametrize("position", [True, -1, 121, 1.5, "1"])
def test_exact_shot_position_is_a_bounded_integer(store, spec, position):
    with pytest.raises(ValueError):
        precise_flashback(store, spec, position)


def test_isolated_browser_sample_contains_three_valid_readable_moments(tmp_path):
    from pathlib import Path
    from scripts.checkpoint_browser_smoke import fixture

    sample = fixture(tmp_path / "browser-library")
    store = Store(Path(sample["root"]))
    project = store.get(sample["id"])
    assert project["spec"]["backend"] == "demo" and not project["assets"] and not project["jobs"]
    assert [shot["flashback_after_shot"] for shot in project["episodes"][1]["script"]["shots"]] == [
        None,
        0,
        1,
    ]
    with TestClient(create_app(store.root, run_worker=False)) as client:
        result = client.patch(
            f"/api/projects/{sample['id']}/episodes/2/draft",
            json={
                "revision": 1,
                "edits": [
                    {
                        "shot_id": project["episodes"][1]["script"]["shots"][2]["id"],
                        "narration": "I remember the door opening.",
                    }
                ],
            },
        )
    assert result.status_code == 200, result.text
    assert result.json()["episodes"][0]["script"] == sample["first_script"]


def test_two_episode_prewrite_and_media_preserve_exact_flashback_and_prior_export(
    store, spec, monkeypatch, tmp_path
):
    spec.kind, spec.episodes, spec.target_seconds, spec.prewrite_season = "series", 2, 10, True
    original_plan, original_script = DemoStory.plan, DemoStory.script

    def plan_with_prop(self, project):
        plan = original_plan(self, project)
        plan.props = [
            Prop(
                id=stable(project["id"], "compass"),
                name="Silver compass",
                description="A silver compass with cracked glass",
                owner_id=plan.characters[0].id,
            )
        ]
        return plan

    def script_with_checkpoint(self, project, number):
        script = original_script(self, project, number)
        hero, guide = [c["id"] for c in project["plan"]["characters"]]
        prop = project["plan"]["props"][0]["id"]
        if number == 1:
            script.shots[1].character_ids = [guide]
            script.shots[1].speaker_id = guide
            script.shots[1].required_props = [PropUse(prop_id=prop, character_id=guide)]
            script.proposed_changes = [
                CanonChange(
                    after_shot=1,
                    entity_id=prop,
                    field="prop_owner",
                    before_value=hero,
                    value=guide,
                    reason="Mara hands Eli the compass.",
                ),
                CanonChange(
                    after_shot=2,
                    entity_id=prop,
                    field="prop_owner",
                    before_value=guide,
                    value=hero,
                    reason="Eli returns the compass to Mara.",
                ),
            ]
        else:
            shot = script.shots[0]
            shot.character_ids, shot.speaker_id = [guide], guide
            shot.flashback_episode, shot.flashback_after_shot = 1, 1
            shot.continuity_note = "A memory between receiving and returning the compass."
            shot.required_props = [PropUse(prop_id=prop, character_id=guide)]
        return script

    monkeypatch.setattr(DemoStory, "plan", plan_with_prop)
    monkeypatch.setattr(DemoStory, "script", script_with_checkpoint)
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    drafted = produce_until(store, worker, pid, "DRAFT", 2)
    assert not drafted["canon"] and not drafted["assets"]
    assert drafted["episodes"][1]["script"]["shots"][0]["flashback_after_shot"] == 1
    first = produce_until(store, worker, pid)
    assert first["status"] == "COMPLETED"
    movie = next(a for a in first["assets"] if a["role"] == "export")
    old_hash = digest(store.asset_path(movie["id"])[0])
    old_script = first["episodes"][0]["script"]
    changes = [e for e in first["canon"] if e["field"] == "prop_owner"]
    assert [e["after_shot"] for e in changes] == [1, 2]
    reopened = Store(store.root)
    monkeypatch.setattr(DemoStory, "script", lambda *a, **k: pytest.fail("Rewrote a saved precise draft"))
    reopened.enqueue(pid, 2)
    complete = produce_until(reopened, Worker(reopened), pid)
    assert all(e["status"] == "COMPLETED" for e in complete["episodes"])
    assert complete["episodes"][0]["script"] == old_script
    assert digest(reopened.asset_path(movie["id"])[0]) == old_hash
    assert len([a for a in complete["assets"] if a["role"] == "export"]) == 2
    restored = restore_backup(
        create_backup(reopened, tmp_path / "timed-movies.zip"), tmp_path / "restored-movies"
    )
    assert restored.get(pid)["canon"] == complete["canon"]
    assert restored.get(pid)["episodes"][1]["script"] == complete["episodes"][1]["script"]
