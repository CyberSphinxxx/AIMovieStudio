"""Deterministic development fixtures; these tests do not certify AI writing quality."""

import pytest
import json

from studio.backup import create_backup, restore_backup
from studio.domain import CanonChange, KnowledgeUse, SeasonPlan, stable, validate_script
from studio.story import DemoStory, OllamaStory
from studio.storage import Store, atomic_json
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


def test_ten_minute_sections_recover_receipt_and_reuse_in_portable_backup(store, spec, monkeypatch, tmp_path):
    spec.kind, spec.target_seconds = "film", 600
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    partial = produce_until(store, worker, pid, "SCRIPT_BATCH", 3)
    batches = [s for s in partial["jobs"][0]["steps"] if s["stage"] == "SCRIPT_BATCH"]
    assert len(batches) == 30
    saved = [s["output"] for s in batches[:3]]
    assert not partial["assets"] and not partial["canon"]

    step = worker.claim()
    assert step["payload"]["start"] == 12
    atomic_json(worker.directory(step) / "receipt.json", worker.execute(step))
    reopened = Store(store.root)
    recovery = Worker(reopened)
    recovery.recover()
    recovered = reopened.get(pid)
    assert recovered["jobs"][0]["steps"][4]["state"] == "SUCCEEDED"
    archive = create_backup(reopened, tmp_path / "sections.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    restored.control(pid, "resume")

    original = DemoStory.script_batch
    starts = []

    def continuing(self, project, number, start, count, previous):
        assert start >= 16, "A committed section was regenerated"
        assert count <= 4
        starts.append(start)
        return original(self, project, number, start, count, previous)

    monkeypatch.setattr(DemoStory, "script_batch", continuing)
    result = produce_until(restored, Worker(restored), pid, "SCRIPT", 1)
    script = result["episodes"][0]["script"]
    assert len(script["shots"]) == 120
    assert [s["number"] for s in script["shots"]] == list(range(1, 121))
    assert sum(s["duration"] for s in script["shots"]) == 600
    assert len(starts) == 26
    assert [s["output"] for s in result["jobs"][0]["steps"][1:4]] == saved
    assert not result["assets"] and not result["canon"]


def test_batched_season_drafts_are_reused_without_future_canon(store, spec, monkeypatch):
    spec.kind, spec.episodes, spec.target_seconds, spec.prewrite_season = "series", 3, 30, True
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    result = produce_until(store, worker, pid, "DRAFT", 3)
    assert all(e["status"] == "DRAFTED" for e in result["episodes"])
    assert len([s for s in result["jobs"][0]["steps"] if s["stage"] == "DRAFT_BATCH"]) == 6
    assert not result["canon"] and not result["assets"]
    saved = result["episodes"][1]["script"]
    monkeypatch.setattr(DemoStory, "script_batch", lambda *args: pytest.fail("Rewrote a saved episode"))
    produce_until(store, worker, pid)
    store.enqueue(pid, 2)
    result = produce_until(store, worker, pid)
    assert result["episodes"][1]["script"] == saved
    assert len(result["canon"]) == 2
    assert not any(s["stage"] == "SCRIPT_BATCH" for s in result["jobs"][-1]["steps"])


def test_knowledge_declared_in_first_section_applies_to_second(store, spec, monkeypatch):
    spec.kind, spec.target_seconds = "drama", 30
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    original = DemoStory.script_batch
    fact = "The signal comes from the underground chamber."

    def story(self, project, number, start, count, previous):
        section = original(self, project, number, start, count, previous)
        hero = project["plan"]["characters"][0]["id"]
        if start == 0:
            section.proposed_changes = [
                CanonChange(
                    after_shot=4,
                    entity_id=hero,
                    field="knowledge",
                    before_value="unknown",
                    value=fact,
                    reason="Mara identifies the source on the old map.",
                )
            ]
        else:
            assert previous[0].proposed_changes[0].value == fact
            section.shots[0].required_knowledge = [KnowledgeUse(character_id=hero, fact=fact)]
        return section

    monkeypatch.setattr(DemoStory, "script_batch", story)
    result = produce_until(store, worker, pid, "SCRIPT", 1)
    assert len(result["episodes"][0]["script"]["proposed_changes"]) == 1
    assert not result["canon"]


@pytest.mark.parametrize("fault", ["numbering", "duration", "unknown_fact", "missing_checkpoint"])
def test_bad_section_is_blocked_before_visuals(store, spec, monkeypatch, fault):
    spec.kind, spec.target_seconds = "drama", 30
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    produce_until(store, worker, pid, "SCRIPT_BATCH", 1)
    step = worker.claim()
    original = DemoStory.script_batch

    def broken(self, project, number, start, count, previous):
        section = original(self, project, number, start, count, previous)
        if fault == "numbering":
            section.shots[0].number = 1
        elif fault == "duration":
            section.shots[0].duration = 2
        else:
            section.shots[0].required_knowledge = [
                KnowledgeUse(character_id=section.shots[0].speaker_id, fact="An undiscovered future secret")
            ]
        return section

    monkeypatch.setattr(DemoStory, "script_batch", broken)
    if fault == "missing_checkpoint":
        with store.connect() as db:
            db.execute("UPDATE steps SET output=NULL WHERE id=?", (step["payload"]["previous_batch_ids"][0],))
    with pytest.raises((RuntimeError, ValueError), match="BAD_STORY|CANON_CONFLICT"):
        worker.execute(step)
    assert not store.get(pid)["assets"]


def test_local_schema_and_prompt_are_bounded_to_current_section(store, spec):
    spec.kind, spec.target_seconds = "film", 600
    pid, _ = store.create(spec)
    project = store.get(pid)
    project["plan"] = DemoStory().plan(project).model_dump()
    first = DemoStory().script_batch(project, 1, 0, 4, [])
    provider = OllamaStory("contract-fixture")

    def generated(schema, prompt):
        data = schema.model_json_schema()
        assert data["properties"]["shots"]["maxItems"] == 4
        assert data["properties"]["screenplay"]["maxLength"] == 1600
        shot = data["$defs"]["PinnedShot"]["properties"]
        assert shot["number"]["minimum"] == 5 and shot["number"]["maximum"] == 8
        assert shot["duration"]["maximum"] == 5
        assert shot["narration"]["maxLength"] == 60
        assert "shots 5 through 8 of 120" in prompt
        assert "episode_outline" in prompt and "earlier_episode_changes" in prompt
        return DemoStory().script_batch(project, 1, 4, 4, [first])

    provider.generate = generated
    section = provider.script_batch(project, 1, 4, 4, [first])
    assert section.shots[0].id == stable(pid, "episode:1:shot:4")
    assert section.shots[-1].number == 8
    with pytest.raises(ValueError, match="one to four"):
        provider.script_batch(project, 1, 4, 5, [first])


def test_legacy_script_step_without_batch_payload_still_runs(store, spec):
    spec.kind, spec.target_seconds = "drama", 30
    pid, _ = store.create(spec)
    project = store.get(pid)
    plan = DemoStory().plan(project)
    with store.connect() as db:
        db.execute("UPDATE projects SET plan=? WHERE id=?", (plan.model_dump_json(), pid))
        for e in plan.episodes:
            db.execute(
                "INSERT INTO episodes(id,project_id,number,outline) VALUES(?,?,?,?)",
                (stable(pid, f"episode:{e.number}"), pid, e.number, e.model_dump_json()),
            )
    jid = store.enqueue(pid)
    with store.connect() as db:
        db.execute("DELETE FROM steps WHERE job_id=?", (jid,))
        store.add_step(db, jid, 0, "SCRIPT", {"episode": 1})
    output = Worker(store).execute(Worker(store).claim())
    from studio.domain import EpisodeScript

    validate_script(
        EpisodeScript.model_validate(output["script"]), SeasonPlan.model_validate(project["plan"] or plan), 30
    )


def select_writer(store, engine):
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('story_engine',?)", (json.dumps(engine),))


@pytest.mark.parametrize("seconds,counts", [(15, [2, 1]), (20, [2, 2]), (40, [2, 2, 2, 2])])
def test_cpu_4b_new_sections_use_frozen_job_config_and_complete_runtime(store, spec, seconds, counts):
    # Demo backend explicitly exercises scheduling, never a claim of real writing quality.
    spec.kind, spec.target_seconds = "drama", seconds
    pid, _ = store.create(spec)
    select_writer(store, "cpu_4b")
    jid = store.enqueue(pid)
    select_writer(store, "ollama")
    result = produce_until(store, Worker(store), pid, "SCRIPT", 1)
    batches = [s for s in result["jobs"][0]["steps"] if s["stage"] == "SCRIPT_BATCH"]
    assert [s["payload"]["count"] for s in batches] == counts
    script = result["episodes"][0]["script"]
    assert [s["number"] for s in script["shots"]] == list(range(1, sum(counts) + 1))
    assert sum(s["duration"] for s in script["shots"]) == seconds
    assert not result["canon"] and not result["assets"]
    assert store.enqueue(pid) == jid


def test_new_settings_do_not_rewrite_existing_four_shot_payloads(store, spec):
    spec.kind, spec.target_seconds = "drama", 40
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    result = produce_until(store, worker, pid, "SCRIPT_BATCH", 1)
    saved = result["jobs"][0]["steps"]
    select_writer(store, "cpu_4b")
    result = produce_until(store, worker, pid, "SCRIPT", 1)
    batches = [s for s in result["jobs"][0]["steps"] if s["stage"] == "SCRIPT_BATCH"]
    assert [s["payload"]["count"] for s in batches] == [4, 4]
    assert batches[0]["output"] == saved[1]["output"]
    assert [s["id"] for s in result["jobs"][0]["steps"][: len(saved)]] == [s["id"] for s in saved]


def test_two_shot_drafts_recover_and_survive_backup_without_future_canon(store, spec, tmp_path):
    spec.kind, spec.episodes, spec.target_seconds, spec.prewrite_season = "series", 3, 20, True
    pid, _ = store.create(spec)
    select_writer(store, "cpu_4b")
    store.enqueue(pid)
    worker = Worker(store)
    produce_until(store, worker, pid, "DRAFT_BATCH", 1)
    step = worker.claim()
    assert step["payload"]["start"] == 2 and step["payload"]["count"] == 2
    atomic_json(worker.directory(step) / "receipt.json", worker.execute(step))
    recovery = Worker(Store(store.root))
    recovery.recover()
    saved = store.get(pid)["jobs"][0]["steps"][2]["output"]
    assert saved is not None
    archive = create_backup(store, tmp_path / "two-shots.zip")
    restored = restore_backup(archive, tmp_path / "restored-two-shots")
    select_writer(restored, "ollama")
    restored.control(pid, "resume")
    result = produce_until(restored, Worker(restored), pid, "SCRIPT", 1)
    assert all(e["script"] and len(e["script"]["shots"]) == 4 for e in result["episodes"])
    assert len([s for s in result["jobs"][0]["steps"] if s["stage"] == "DRAFT_BATCH"]) == 6
    assert result["jobs"][0]["steps"][2]["output"] == saved
    assert not result["canon"] and not result["assets"]
