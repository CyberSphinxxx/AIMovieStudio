"""Opt-in real CPU story integration; expected to stop at uninstalled GPU provider."""

import json
import time
from pathlib import Path
from uuid import uuid4

from studio.domain import ProjectInput
from studio.storage import Store, atomic_json
from studio.worker import Worker


def main():
    store = Store(Path("data/real-pipeline-smoke"))
    with store.connect() as db:
        for key, value in {"story_engine": "small_cpu", "story_model": "", "speech": "windows"}.items():
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))
    spec = ProjectInput(
        idea="A lighthouse keeper follows a mysterious light to rescue a lost sailor, then returns home.",
        target_seconds=10,
        backend="local",
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    started = time.monotonic()
    worker.start()
    try:
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            project = store.get(pid)
            if project["status"] == "FAILED":
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Real story worker did not settle")
        written = bool(project["plan"] and project["episodes"][0]["script"])
        assert not any(a["metadata"]["is_mock"] for a in project["assets"]), "No mock substitution permitted"
        report = {
            "status": "REAL_STORY_PERSISTED_GPU_BLOCKED" if written else "REAL_STORY_FAILED",
            "is_mock": False,
            "model": "Qwen2.5-0.5B-Instruct-Q4_K_M",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "project_id": pid,
            "stages": [{"stage": s["stage"], "state": s["state"]} for s in project["jobs"][0]["steps"]],
            "error": project["jobs"][0]["error"],
            "plan": project["plan"],
            "script": project["episodes"][0]["script"] if project["episodes"] else None,
            "image_video": "NOT TESTED in this fixture; GPU installation/test is separate",
        }
        atomic_json(Path("ops/evidence/real-pipeline-smoke.json"), report)
        print(json.dumps({k: v for k, v in report.items() if k not in {"plan", "script"}}, indent=2))
        assert written, "Real story/script were not persisted; failure evidence recorded"
        assert "LICENSE_REVIEW_REQUIRED" in project["jobs"][0]["error"], "Expected separate GPU gate"
    finally:
        worker.close()


if __name__ == "__main__":
    main()
