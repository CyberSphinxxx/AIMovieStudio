"""Isolated low-resource UI verification: real API, explicit demo drafts, no models.

Only owns its new sample library/server/browser processes. It never starts the
main library, changes user settings, or terminates user applications.
"""

import json
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


def fixture(directory):
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
    return {
        "id": pid,
        "second_title": plan.episodes[1].title,
        "first_script": store.get(pid)["episodes"][0]["script"],
        "root": str(directory),
    }


def main():
    baseline = memory_status()
    if not runtime_memory_known(baseline) or baseline["free_gb"] < 0.75:
        raise RuntimeError(
            "UI_TEST_RESOURCE_BUSY: Need 0.75 GiB free RAM for this isolated browser check; native model guards remain unchanged."
        )
    identity = uuid4().hex
    directory = ROOT / "data/checkpoint-browser" / identity
    directory.mkdir(parents=True)
    sample = fixture(directory / "library")
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
    previous = ROOT / "ops/evidence/browser-tests.json"
    report = {
        "scope": "Isolated explicit demo UI fixture, no model inference",
        "url": url,
        "fixture": str(sample_path),
        "baseline_memory": baseline,
        "samples": [],
        "status": "STARTED",
    }
    if previous.exists():
        archive = ROOT / f"ops/evidence/browser-tests-before-checkpoint-{identity}.json"
        with archive.open("xb") as stream:
            stream.write(previous.read_bytes())
        report["previous_browser_report"] = {"path": str(archive), "sha256": digest(archive)}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
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
                    "e2e/story-checkpoint.spec.ts",
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
                if time.monotonic() - started > 160:
                    raise RuntimeError("UI test exceeded its bounded 160 seconds")
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
