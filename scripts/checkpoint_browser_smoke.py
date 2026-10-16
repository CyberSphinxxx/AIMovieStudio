"""Isolated low-resource UI verification: real API, explicit demo drafts, no models.

Only owns its new sample library/server/browser processes. It never starts the
main library, changes user settings, or terminates user applications.
"""

import json
import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from studio.diagnostics import memory_status, runtime_memory_known
from studio.domain import ProjectInput, stable
from studio.processes import owned_process
from studio.storage import Store, atomic_json, digest
from studio.story import DemoStory

ROOT = Path(__file__).resolve().parents[1]


def fixture(directory, *, legacy_timing=False):
    store = Store(directory)
    spec = ProjectInput(
        idea="DEVELOPMENT CHECKPOINT FIXTURE: A keeper remembers opening a door before returning home.",
        kind="series",
        episodes=2,
        target_seconds=12,
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    project = store.get(pid)
    plan = DemoStory().plan(project)
    project["plan"] = plan.model_dump()
    with store.connect() as db:
        db.execute(
            "UPDATE projects SET plan=?,title=?,status='PAUSED' WHERE id=?",
            (plan.model_dump_json(), "Development checkpoint fixture", pid),
        )
        for outline in plan.episodes:
            script = DemoStory().script(project, outline.number)
            if outline.number == 2:
                for shot, position in zip(script.shots, (None, 0, 1), strict=True):
                    shot.flashback_episode = 1
                    shot.flashback_after_shot = position
                    shot.continuity_note = "A saved memory in the earlier episode."
            db.execute(
                "INSERT INTO episodes VALUES(?,?,?,?,?,?)",
                (
                    stable(pid, f"episode:{outline.number}"),
                    pid,
                    outline.number,
                    outline.model_dump_json(),
                    script.model_dump_json(),
                    "DRAFTED",
                ),
            )
        if legacy_timing:
            db.execute(
                "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    pid,
                    plan.characters[0].id,
                    1,
                    "knowledge",
                    "The keeper recognizes the vanished ship.",
                    "A legacy sample fact without recorded scene timing.",
                    1,
                ),
            )
    return {
        "id": pid,
        "second_title": plan.episodes[1].title,
        "first_script": store.get(pid)["episodes"][0]["script"],
        "root": str(directory),
    }


def movie_review_fixture(directory):
    """Produce/import sample movies privately; never change existing settings."""
    from studio.worker import Worker
    from studio.backup import create_backup
    from studio import backup_import

    workspace = ROOT / "data/movie-review-browser" / uuid4().hex
    fresh_library = not (directory / "studio.sqlite3").exists()
    store = Store(directory if fresh_library else workspace / "source")
    spec = ProjectInput(
        idea="DEVELOPMENT REVIEW: A keeper answers an old signal and returns home.",
        kind="series",
        episodes=3,
        target_seconds=5,
        prewrite_season=True,
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    worker = Worker(store)
    started = time.monotonic()
    original_check = worker.check

    def guarded(step):
        reading = memory_status()
        if not runtime_memory_known(reading) or reading["free_gb"] < 0.3 or time.monotonic() - started > 90:
            raise RuntimeError(
                "UI_TEST_RESOURCE_BUSY: Sample movie preparation stopped at its RAM/time guard"
            )
        original_check(step)

    worker.check = guarded
    for number in (1, 2):
        jid = store.enqueue(pid, number)
        with store.connect() as db:
            config = store.settings() | {"speech": "none", "reserve_mb": 1024}
            db.execute("UPDATE jobs SET config=? WHERE id=?", (json.dumps(config), jid))
        for _ in range(100):
            step = worker.claim()
            if not step:
                break
            worker.check(step)
            output = worker.execute(step)
            worker.verify(output)
            atomic_json(worker.directory(step) / "receipt.json", output)
            worker.complete(step, output)
        if store.get(pid)["episodes"][number - 1]["status"] != "COMPLETED":
            raise RuntimeError("Development movie review sample did not finish")
    # Explicit fixture state corresponding to an earlier outcome correction.
    with store.connect() as db:
        identity = str(uuid4())
        value, reason = (
            "The distant signal was answered.",
            "Development fixture: clarify the earlier outcome before movie review.",
        )
        db.execute(
            "INSERT INTO canon VALUES(?,?,?,?,?,?,?,?)", (identity, pid, pid, 1, "outcome", value, reason, 2)
        )
        db.execute(
            "UPDATE projects SET revision=2,title='Development movie review fixture' WHERE id=?", (pid,)
        )
        db.execute("UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number>1", (pid,))
        store.event(
            db,
            pid,
            None,
            "canon_revision",
            {
                "event_id": identity,
                "event": {
                    "entity_id": pid,
                    "episode": 1,
                    "field": "outcome",
                    "value": value,
                    "reason": reason,
                    "after_shot": None,
                },
                "revision": 2,
                "affected_episodes": [2, 3],
            },
        )
    archive = create_backup(store, workspace / "fixture.zip")
    target = store
    if not fresh_library:
        target = Store(directory)
        operation, path = backup_import.begin_upload(target)
        shutil.copyfile(archive, path / "upload.zip")
        backup_import.prepare_import(target, operation)
        backup_import.commit_import(target, operation)
    project = target.get(pid)
    return {
        "id": pid,
        "root": str(directory),
        "second_title": project["episodes"][1]["outline"]["title"],
        "source_archive": str(archive),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--canon-timing", action="store_true", help="Verify explicit legacy fact timing repair"
    )
    modes.add_argument("--all", action="store_true", help="Run the full demo UI suite in an isolated library")
    modes.add_argument("--movie-review", action="store_true", help="Verify keeping a reviewed sample movie")
    args = parser.parse_args()
    baseline = memory_status()
    minimum = 3 if args.all else 1.25 if args.movie_review else 0.75
    if not runtime_memory_known(baseline) or baseline["free_gb"] < minimum:
        raise RuntimeError(
            f"UI_TEST_RESOURCE_BUSY: Need {minimum} GiB free RAM for this isolated browser check; native model guards remain unchanged."
        )
    identity = uuid4().hex
    directory = ROOT / "data/checkpoint-browser" / identity
    directory.mkdir(parents=True)
    sample = (
        movie_review_fixture(directory / "library")
        if args.movie_review
        else fixture(directory / "library", legacy_timing=args.canon_timing)
    )
    sample_path = directory / "fixture.json"
    atomic_json(sample_path, sample)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = os.environ | {
        "STUDIO_DATA": sample["root"],
        "STUDIO_TEST_BASE_URL": url,
        "STUDIO_CHECKPOINT_FIXTURE": str(sample_path),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if args.all:
        # Each case creates its own sample; a shared fixture would mix modes.
        env.pop("STUDIO_CHECKPOINT_FIXTURE", None)
    previous = ROOT / "ops/evidence/browser-tests.json"
    report = {
        "scope": "Isolated explicit demo UI fixture, no model inference",
        "url": url,
        "fixture": str(sample_path),
        "baseline_memory": baseline,
        "minimum_free_gib": minimum,
        "samples": [],
        "status": "STARTED",
        "suite": "all"
        if args.all
        else "movie-review"
        if args.movie_review
        else "canon-timing"
        if args.canon_timing
        else "story-checkpoint",
    }
    if previous.exists():
        archive = ROOT / f"ops/evidence/browser-tests-before-checkpoint-{identity}.json"
        with archive.open("xb") as stream:
            stream.write(previous.read_bytes())
        report["previous_browser_report"] = {"path": str(archive), "sha256": digest(archive)}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    ceiling = 600 if args.all else 160
    report["wall_seconds_limit"] = ceiling
    started = time.monotonic()
    try:
        with (
            (directory / "server.log").open("wb") as server_log,
            (directory / "browser.log").open("wb") as browser_log,
            ExitStack() as stack,
        ):
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-s",
                    "-m",
                    "uvicorn",
                    "studio.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=env,
                stdout=server_log,
                stderr=server_log,
                creationflags=flags,
            )
            stack.enter_context(owned_process(server))
            deadline = time.monotonic() + 20
            while True:
                if server.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Isolated Studio server did not start")
                try:
                    with urllib.request.urlopen(f"{url}/api/projects/{sample['id']}", timeout=1) as response:
                        assert json.load(response)["id"] == sample["id"]
                    break
                except OSError:
                    time.sleep(0.2)
            node = shutil.which("node")
            if not node:
                raise RuntimeError("Node runtime unavailable for installed Playwright")
            browser = subprocess.Popen(
                [
                    node,
                    str(ROOT / "client/node_modules/@playwright/test/cli.js"),
                    "test",
                    *(
                        []
                        if args.all
                        else [
                            "e2e/movie-story-review.spec.ts"
                            if args.movie_review
                            else "e2e/canon-timing.spec.ts"
                            if args.canon_timing
                            else "e2e/story-checkpoint.spec.ts"
                        ]
                    ),
                ],
                cwd=ROOT / "client",
                env=env,
                stdout=browser_log,
                stderr=browser_log,
                creationflags=flags,
            )
            stack.enter_context(owned_process(browser))
            while browser.poll() is None:
                reading = memory_status()
                report["samples"].append({"seconds": round(time.monotonic() - started, 2), **reading})
                if not runtime_memory_known(reading) or reading["free_gb"] < 0.3:
                    raise RuntimeError(
                        "UI_TEST_RESOURCE_BUSY: Isolated verification stopped below 0.3 GiB or lost RAM counters"
                    )
                if time.monotonic() - started > ceiling:
                    raise RuntimeError(f"UI test exceeded its bounded {ceiling} seconds")
                time.sleep(0.5)
            if browser.returncode:
                raise RuntimeError(
                    "Browser assertions failed; inspect isolated browser.log and Playwright report"
                )
            report.update(status="PASS_DEMO_UI_NOT_INFERENCE", test_exit_code=browser.returncode)
    except BaseException as error:
        report.update(status="FAILED", error=str(error))
        raise
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["logs_directory"] = str(directory)
        atomic_json(ROOT / f"ops/evidence/checkpoint-browser-{identity}.json", report)
        print(
            json.dumps(
                {key: value for key, value in report.items() if key not in {"samples", "baseline_memory"}}
            )
        )


if __name__ == "__main__":
    main()
