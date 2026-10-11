"""Bounded real CPU writing test. No downloads or demo fallback; quality is separate."""

import json
import time
from pathlib import Path
from uuid import uuid4

from studio.diagnostics import memory_status
from studio.domain import ProjectInput
from studio.storage import Store, atomic_json
from studio.worker import Worker


def main():
    started = time.monotonic()
    store = Store(Path("data/cpu-writing-smoke"))
    spec = ProjectInput(
        idea="A lighthouse keeper receives a message from a ship lost at sea. She rescues its last survivor by giving up the lamp that guides ships home. End with the survivor safely ashore and the keeper facing the cost of her choice.",
        kind="drama",
        target_seconds=40,
        backend="local",
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('story_engine','\"cpu_1_5b\"')")
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")
    store.enqueue(pid)
    report = {
        "project_id": pid,
        "is_mock": False,
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",
        "profile": "CPU only; four threads;8192 context; max4 shots/section;three attempts/section",
        "status": "STARTED",
        "quality_review": "NOT_PERFORMED",
        "preflight_memory": memory_status(),
        "samples": 0,
        "sampled_peak_server_rss_bytes": None,
        "sampled_min_available_ram_gib": None,
        "completed_steps": [],
    }

    def observe(sample):
        report["samples"] += 1
        if sample["rss_bytes"] is not None:
            report["sampled_peak_server_rss_bytes"] = max(
                report["sampled_peak_server_rss_bytes"] or 0, sample["rss_bytes"]
            )
        free = sample["memory"].get("free_gb")
        if free is not None:
            previous = report["sampled_min_available_ram_gib"]
            report["sampled_min_available_ram_gib"] = free if previous is None else min(previous, free)
            if free < 2:
                raise RuntimeError("RESOURCE_BUSY: CPU writing test stopped below 2 GiB free RAM.")

    class BoundedWorker(Worker):
        def check(self, step):
            if time.monotonic() - started > 600:
                raise RuntimeError("TIMEOUT: CPU writing smoke reached its ten-minute ceiling.")
            super().check(step)

    worker = BoundedWorker(store, story_observer=observe)
    step = None
    try:
        while step := worker.claim():
            report["stage"] = step["stage"]
            if step["stage"] not in {"PLAN", "SCRIPT_BATCH", "SCRIPT"}:
                raise RuntimeError("Unexpected visual/audio stage in writing-only test")
            before = time.monotonic()
            output = worker.execute(step)
            atomic_json(worker.directory(step) / "receipt.json", output)
            worker.complete(step, output)
            report["completed_steps"].append(
                {"id": step["id"], "stage": step["stage"], "seconds": round(time.monotonic() - before, 3)}
            )
            if step["stage"] == "SCRIPT":
                report["status"] = "STRUCTURED_BATCHED_SCRIPT_VALID"
                break
    except Exception as error:
        report.update(status="FAILED", error=str(error))
        if step:
            with store.connect() as db:
                db.execute("UPDATE steps SET state='FAILED',error=? WHERE id=?", (str(error), step["id"]))
                db.execute("UPDATE jobs SET state='FAILED',error=? WHERE id=?", (str(error), step["job_id"]))
        raise
    finally:
        project = store.get(pid)
        if report["status"] != "FAILED":
            store.control(pid, "pause")
        report.update(
            elapsed_seconds=round(time.monotonic() - started, 3),
            plan=project["plan"],
            script=project["episodes"][0]["script"] if project["episodes"] else None,
        )
        atomic_json(Path(f"ops/evidence/cpu-writing-runs/{pid}.json"), report)
        atomic_json(Path("ops/evidence/real-cpu-batched-story.json"), report)
        print(json.dumps({k: v for k, v in report.items() if k not in {"plan", "script"}}, indent=2))


if __name__ == "__main__":
    main()
