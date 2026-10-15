"""Explicit deterministic development fixtures; no model inference or quality proof."""

import json
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from scripts.story_plan_retest import prepare_plan_retest, read_plan_snapshot, reserve_retest_budget
from scripts.story_batch_smoke import run_writing_test
from studio.backup import create_backup, restore_backup
from studio.local_story import CPU_PROFILES
from studio.storage import atomic_json, digest
from studio.story import DemoStory
from studio.worker import Worker
from tests.test_pipeline import produce_until


@pytest.fixture
def failed_plan(store, spec, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studio.local_story.cpu_server", lambda *a, **kw: pytest.fail("Fixture attempted native inference")
    )
    spec.backend, spec.kind, spec.target_seconds = "local", "drama", 40
    pid, _ = store.create(spec)
    jid = store.enqueue(pid)
    worker = Worker(store, wait_for_resources=False)
    step = worker.claim()
    plan = DemoStory().plan(store.get(pid)).model_dump(mode="json")
    output = {"plan": plan, "artifacts": []}
    worker.complete(step, output)
    with store.connect() as db:
        db.execute(
            "UPDATE jobs SET state='FAILED',config=? WHERE id=?",
            (
                json.dumps({"story_engine": "cpu_4b", "speech": "none"}),
                jid,
            ),
        )
        db.execute("UPDATE projects SET status='FAILED' WHERE id=?", (pid,))
        db.execute(
            "UPDATE steps SET state='FAILED',attempts=1,error='timed out' WHERE job_id=? AND ordinal=1",
            (jid,),
        )
    report = tmp_path / "original-failed-native-fixture.json"
    atomic_json(
        report,
        {
            "development_fixture": True,
            "project_id": pid,
            "is_mock": False,
            "model": CPU_PROFILES["cpu_4b"][0],
            "status": "FAILED",
            "plan": plan,
            "script": None,
            "completed_steps": [{"id": step["id"], "stage": "PLAN"}],
            "elapsed_seconds": 269.719,
        },
    )
    return store, pid, report


def test_isolated_plan_reuse_preserves_source_ids_errors_and_small_batches(
    failed_plan, tmp_path, monkeypatch
):
    source, pid, report = failed_plan
    original = source.get(pid)
    database_sha, report_sha = digest(source.database), digest(report)
    run_id = str(uuid4())
    clone, lineage = prepare_plan_retest(source.root, pid, report, tmp_path / "retest", run_id)
    copied = clone.get(pid)
    assert source.get(pid) == original
    assert digest(source.database) == database_sha and digest(report) == report_sha
    assert copied["plan"] == original["plan"]
    assert copied["episodes"] == original["episodes"]
    old_steps, new_steps = original["jobs"][0]["steps"], copied["jobs"][0]["steps"]
    assert new_steps[0] == old_steps[0]
    for before, after in zip(old_steps[1:], new_steps[1 : len(old_steps)], strict=True):
        assert after == {**before, "state": "SUPERSEDED"}
    batches = new_steps[len(old_steps) : -1]
    assert [s["payload"]["start"] for s in batches] == [0, 2, 4, 6]
    assert [s["payload"]["count"] for s in batches] == [2, 2, 2, 2]
    assert new_steps[-1]["payload"]["batch_ids"] == [s["id"] for s in batches]
    assert copied["jobs"][0]["state"] == "PAUSED"
    assert Worker(clone).claim() is None
    assert not copied["canon"] and not copied["assets"]
    assert lineage["plan_reused"] and not lineage["plan_generated_this_run"]
    assert lineage["source_report_sha256"] == report_sha and lineage["run_id"] != pid
    assert json.loads((tmp_path / "retest/preparation.json").read_text())["status"] == "PREPARED_NOT_RUN"

    # Explicit fixture executes the real scheduling/continuity code through SCRIPT,
    # proving that no saved PLAN is regenerated and no visual stage is executed.
    from studio.local_story import SmallCPUStory

    monkeypatch.setattr(SmallCPUStory, "plan", lambda *a: pytest.fail("Rewrote saved PLAN"))
    monkeypatch.setattr(SmallCPUStory, "script_batch", lambda self, *a: DemoStory().script_batch(*a))
    clone.control(pid, "resume")
    result = produce_until(clone, Worker(clone, wait_for_resources=False), pid, "SCRIPT", 1)
    clone.control(pid, "pause")
    script = result["episodes"][0]["script"]
    assert [s["number"] for s in script["shots"]] == list(range(1, 9))
    assert sum(s["duration"] for s in script["shots"]) == 40
    assert not result["canon"] and not result["assets"]
    assert source.get(pid) == original
    archive = create_backup(clone, tmp_path / "retest-result.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    assert restored.get(pid)["episodes"][0]["script"] == script
    assert restored.get(pid)["jobs"][0]["steps"][0]["output"] == old_steps[0]["output"]
    assert Worker(restored).claim() is None


@pytest.mark.parametrize(
    "fault",
    [
        "report_plan",
        "report_time",
        "report_mock",
        "script",
        "batch",
        "running",
        "visual",
        "canon",
        "config",
        "outline",
    ],
)
def test_refuse_unsafe_plan_reuse_before_creating_destination(failed_plan, tmp_path, fault):
    source, pid, report = failed_plan
    if fault.startswith("report_"):
        data = json.loads(report.read_text())
        if fault == "report_plan":
            data["plan"]["ending"] = "An unrelated ending"
        elif fault == "report_time":
            data["elapsed_seconds"] = 600
        else:
            data["is_mock"] = True
        atomic_json(report, data)
    else:
        with source.connect() as db:
            jid = db.execute("SELECT id FROM jobs").fetchone()[0]
            if fault == "script":
                db.execute("UPDATE episodes SET script='{}'")
            elif fault == "batch":
                db.execute("UPDATE steps SET state='SUCCEEDED',output='{}' WHERE ordinal=1")
            elif fault == "running":
                db.execute("UPDATE steps SET state='RUNNING' WHERE ordinal=1")
            elif fault == "visual":
                source.add_step(db, jid, 4, "AUDIO", {})
            elif fault == "canon":
                # A valid fixture event must still be rejected, never removed.
                character = source.get(pid)["plan"]["characters"][0]["id"]
                db.execute(
                    "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        pid,
                        character,
                        1,
                        "status",
                        '"dead"',
                        "Fixture",
                        1,
                    ),
                )
            elif fault == "config":
                db.execute("UPDATE jobs SET config='{}'")
            else:
                outline = source.get(pid)["episodes"][0]["outline"]
                outline["summary"] = "Changed outline"
                db.execute("UPDATE episodes SET outline=?", (json.dumps(outline),))
    destination = tmp_path / "rejected"
    with pytest.raises(ValueError):
        prepare_plan_retest(source.root, pid, report, destination, str(uuid4()))
    assert not destination.exists()


def test_destination_reuse_and_original_locations_are_refused(failed_plan, tmp_path):
    source, pid, report = failed_plan
    for destination in (source.root, source.root / "nested"):
        with pytest.raises(ValueError, match="separate"):
            prepare_plan_retest(source.root, pid, report, destination, str(uuid4()))
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "original.txt"
    sentinel.write_text("preserve")
    with pytest.raises(FileExistsError):
        prepare_plan_retest(source.root, pid, report, destination, str(uuid4()))
    assert sentinel.read_text() == "preserve"
    with pytest.raises(ValueError, match="new run ID"):
        prepare_plan_retest(source.root, pid, report, tmp_path / "same-id", pid)


def test_readonly_missing_source_does_not_create_database(tmp_path):
    missing = tmp_path / "missing"
    missing.mkdir()
    report = tmp_path / "report.json"
    report.write_text("{}")
    with pytest.raises(sqlite3.OperationalError):
        read_plan_snapshot(missing, str(uuid4()), report)
    assert not (missing / "studio.sqlite3").exists()


def test_budget_is_exclusive_and_survives_partial_reservation(tmp_path):
    path = tmp_path / "budget.json"
    lineage = {"prior_test_milliseconds": 269719, "source_report_sha256": "fixture"}
    result = reserve_retest_budget(path, 320, str(uuid4()), lineage)
    assert result["cumulative_reserved_milliseconds"] == 599719
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        reserve_retest_budget(path, 1, str(uuid4()), lineage)
    assert path.read_bytes() == before
    partial = tmp_path / "interrupted-budget.json"
    partial.write_bytes(b'{"run_id":')
    with pytest.raises(FileExistsError):
        reserve_retest_budget(partial, 320, str(uuid4()), lineage)
    for seconds in (0, 321, 600):
        with pytest.raises(ValueError):
            reserve_retest_budget(tmp_path / "invalid.json", seconds, str(uuid4()), lineage)
    assert not (tmp_path / "invalid.json").exists()


def test_reservation_remains_after_real_process_kill(tmp_path):
    path = tmp_path / "kill-reservation.json"
    code = (
        "from pathlib import Path; from scripts.story_plan_retest import reserve_retest_budget; "
        "import sys; reserve_retest_budget(Path(sys.argv[1]),320,sys.argv[2],"
        "{'prior_test_milliseconds':269719,'source_report_sha256':'development-fixture'}); "
        "print('RESERVED',flush=True); sys.stdin.read()"
    )
    process = subprocess.Popen(
        [sys.executable, "-s", "-c", code, str(path), str(uuid4())],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "RESERVED"
        process.kill()
        process.wait(timeout=10)
        with pytest.raises(FileExistsError):
            reserve_retest_budget(
                path,
                320,
                str(uuid4()),
                {
                    "prior_test_milliseconds": 269719,
                    "source_report_sha256": "development-fixture",
                },
            )
        assert json.loads(path.read_text())["cumulative_reserved_milliseconds"] == 599719
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.communicate(timeout=10)


@pytest.mark.parametrize("timeout", [False, True])
def test_bounded_runner_has_separate_report_and_never_executes_media(
    failed_plan, tmp_path, monkeypatch, timeout
):
    source, pid, report_path = failed_plan
    run_id = str(uuid4())
    clone, lineage = prepare_plan_retest(source.root, pid, report_path, tmp_path / "retest", run_id)
    original_report = report_path.read_bytes()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "studio.local_story.SmallCPUStory.script_batch", lambda self, *a: DemoStory().script_batch(*a)
    )
    clone.control(pid, "resume")
    started = time.monotonic() - (20 if timeout else 0)
    if timeout:
        with pytest.raises(RuntimeError, match="TIMEOUT"):
            run_writing_test(clone, pid, "cpu_4b", 1, started, run_id, lineage)
    else:
        run_writing_test(clone, pid, "cpu_4b", 320, started, run_id, lineage)
    saved = json.loads((tmp_path / f"ops/evidence/cpu-writing-runs/{run_id}.json").read_text())
    assert saved["status"] == ("FAILED" if timeout else "STRUCTURED_BATCHED_SCRIPT_VALID")
    assert saved["quality_review"] == "NOT_PERFORMED"
    assert saved["lineage"]["plan_reused"] and saved["run_id"] != pid
    assert all(s["stage"] in {"SCRIPT_BATCH", "SCRIPT"} for s in saved["completed_steps"])
    assert not clone.get(pid)["assets"] and not clone.get(pid)["canon"]
    assert clone.get(pid)["jobs"][0]["state"] == ("FAILED" if timeout else "PAUSED")
    assert source.get(pid)["episodes"][0]["script"] is None
    assert report_path.read_bytes() == original_report
    with pytest.raises(ValueError, match="overwrite"):
        run_writing_test(clone, pid, "cpu_4b", 320, time.monotonic(), run_id, lineage)
