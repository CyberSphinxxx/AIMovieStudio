"""Explicit deterministic story fixtures; no native writing or cinematic-quality proof."""

import pytest

from studio.domain import CanonChange, KnowledgeUse, continuity_errors, validate_script
from studio.story import DemoStory
from studio.worker import Worker
from studio.storage import digest
from studio.backup import create_backup, restore_backup
from tests.test_continuity import fixture_story, FACT
from tests.test_pipeline import produce_until, set_silent


@pytest.mark.parametrize("narration", ["", " \t\n "])
def test_silent_offscreen_placeholder_does_not_make_dead_character_present(store, spec, narration):
    _, plan, script = fixture_story(store, spec)
    hero, guide = [c.id for c in plan.characters]
    script.number = 2
    for shot in script.shots:
        shot.character_ids, shot.speaker_id, shot.narration = [guide], hero, narration
    death = [{"episode": 1, "entity_id": hero, "field": "alive", "value": "false"}]
    validate_script(script, plan, 10)
    assert not continuity_errors(script, death, plan)


@pytest.mark.parametrize("narration", ["", " \t "])
def test_silent_absent_placeholder_cannot_be_used_for_knowledge_assertions(store, spec, narration):
    _, plan, script = fixture_story(store, spec)
    hero, guide = [c.id for c in plan.characters]
    shot = script.shots[0]
    shot.character_ids, shot.speaker_id, shot.narration = [guide], hero, narration
    shot.required_knowledge = [KnowledgeUse(character_id=hero, fact=FACT)]
    with pytest.raises(ValueError, match="outside the shot"):
        validate_script(script, plan, 10)


def test_actual_dead_speech_and_visible_silent_death_remain_blocked(store, spec):
    _, plan, script = fixture_story(store, spec)
    hero, guide = [c.id for c in plan.characters]
    script.number = 2
    death = [{"episode": 1, "entity_id": hero, "field": "alive", "value": "false"}]
    shot = script.shots[0]
    shot.character_ids, shot.speaker_id, shot.narration = [guide], hero, "The light is still burning."
    assert any("Shot 1" in e and "is dead" in e for e in continuity_errors(script, death, plan))
    shot.character_ids, shot.narration = [hero], ""
    assert any("Shot 1" in e and "is dead" in e for e in continuity_errors(script, death, plan))
    shot.flashback_episode, shot.continuity_note = 1, "The keeper before the fatal voyage."
    assert not continuity_errors(script, death, plan)


def test_two_episode_silent_scene_survives_reopen_and_backup_without_reviving_actor(
    store, spec, monkeypatch, tmp_path
):
    spec.kind, spec.episodes, spec.target_seconds = "series", 2, 10
    original = DemoStory.script

    def causal_script(self, project, number):
        script = original(self, project, number)
        hero, guide = [c["id"] for c in project["plan"]["characters"]]
        if number == 1:
            script.proposed_changes = [
                CanonChange(
                    after_shot=2,
                    entity_id=hero,
                    field="alive",
                    before_value="true",
                    value="false",
                    reason="The keeper dies after the rescue is completed.",
                )
            ]
        else:
            for shot in script.shots:
                shot.character_ids, shot.speaker_id, shot.narration = [guide], hero, ""
                shot.action = "Eli silently examines the empty seat and then walks toward the shore."
            script.screenplay = (
                "DEMO SILENT SCREENPLAY. Development continuity fixture only.\n"
                "SCENE 1 — Eli watches the empty harbor. The keeper's chair remains empty. No one speaks; the light moves across the abandoned room.\n"
                "SCENE 2 — Eli closes the lighthouse door and walks toward the shore. Only wind and footsteps accompany the image. No narration is heard."
            )
        return script

    monkeypatch.setattr(DemoStory, "script", causal_script)
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    first = produce_until(store, Worker(store), pid)
    first_export = next(a for a in first["assets"] if a["role"] == "export")
    original_script = first["episodes"][0]["script"]
    store.enqueue(pid, 2)
    second = produce_until(store, Worker(store), pid)
    assert second["status"] == "COMPLETED" and len(second["canon"]) == 3
    assert second["episodes"][0]["script"] == original_script
    assert digest(store.asset_path(first_export["id"])[0]) == first_export["sha256"]
    assert [e["value"] for e in second["canon"] if e["field"] == "alive"] == ["false"]
    archive = create_backup(store, tmp_path / "silent-continuation.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    assert restored.get(pid)["episodes"] == second["episodes"]
    assert restored.get(pid)["canon"] == second["canon"]


@pytest.mark.parametrize("silence", [True, False])
def test_review_editor_cleans_only_unused_offscreen_knowledge_and_keeps_audit(
    store, spec, monkeypatch, tmp_path, silence
):
    import json
    from fastapi.testclient import TestClient
    from studio.api import create_app

    spec.review_story = True
    old_plan, old_script = DemoStory.plan, DemoStory.script

    def plan(self, project):
        result = old_plan(self, project)
        for character in result.characters:
            character.initial_knowledge = [FACT]
        return result

    def script(self, project, number):
        result = old_script(self, project, number)
        hero, guide = [c["id"] for c in project["plan"]["characters"]]
        first = result.shots[0]
        first.character_ids, first.speaker_id = [guide], hero
        first.required_knowledge = [KnowledgeUse(character_id=c, fact=FACT) for c in (hero, guide)]
        return result

    monkeypatch.setattr(DemoStory, "plan", plan)
    monkeypatch.setattr(DemoStory, "script", script)
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    before = produce_until(store, Worker(store), pid)
    first = before["episodes"][0]["script"]["shots"][0]
    assert before["status"] == "PAUSED" and not before["assets"] and not before["canon"]
    narration = "" if silence else "The hidden chamber holds the source of the signal."
    with TestClient(create_app(store.root, run_worker=False)) as client:
        response = client.patch(
            f"/api/projects/{pid}/episodes/1/draft",
            json={
                "revision": 1,
                "edits": [
                    {
                        "shot_id": first["id"],
                        "narration": narration,
                        "action": "Eli examines the old map and locates the hidden chamber.",
                    }
                ],
            },
        )
    assert response.status_code == 200, response.text
    edited = response.json()
    saved = edited["episodes"][0]["script"]
    expected = first["required_knowledge"][1:] if silence else first["required_knowledge"]
    assert saved["shots"][0]["required_knowledge"] == expected
    assert saved["shots"][0]["id"] == first["id"]
    if silence:
        assert "No spoken line." in saved["screenplay"]
    assert edited["status"] == "PAUSED" and not edited["assets"] and not edited["canon"]
    with store.connect() as db:
        event = json.loads(db.execute("SELECT data FROM events WHERE kind='draft_revision'").fetchone()[0])
    assert event["original_script"] == before["episodes"][0]["script"]
    assert bool(event["continuity_cleanup"]) == silence
    if silence:
        assert event["continuity_cleanup"][0]["unused_knowledge_removed"] == first["required_knowledge"][:1]
    store.control(pid, "resume")
    completed = produce_until(store, Worker(store), pid)
    assert completed["status"] == "COMPLETED" and len(completed["canon"]) == 1
    archive = create_backup(store, tmp_path / "edited-silent.zip")
    restored = restore_backup(archive, tmp_path / "restored-edit")
    assert restored.get(pid)["episodes"][0]["script"] == saved
