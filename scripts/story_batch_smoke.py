"""Bounded real CPU writing test. No downloads or demo fallback; quality is separate."""

import json
import argparse
import time
from pathlib import Path
from uuid import uuid4

from studio.diagnostics import memory_status
from studio.domain import ProjectInput
from studio.storage import Store, atomic_json
from studio.worker import Worker
from studio.local_story import CPU_PROFILES
from studio.story_budget import shots_per_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-seconds", type=int, default=600, help="Shorter test ceiling, at most 600 seconds"
    )
    parser.add_argument("--profile", choices=["cpu_1_5b", "cpu_4b"], default="cpu_1_5b")
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 600:
        parser.error("Writing test ceiling must be between 1 and 600 seconds")
    started = time.monotonic()
    store = Store(Path("data/cpu-4b-writing-smoke" if args.profile == "cpu_4b" else "data/cpu-writing-smoke"))
    spec = ProjectInput(
        idea="A lighthouse keeper receives a message from a ship lost at sea. She rescues its last survivor by giving up the lamp that guides ships home. End with the survivor safely ashore and the keeper facing the cost of her choice.",
        kind="drama",
        target_seconds=40,
        backend="local",
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('story_engine',?)", (json.dumps(args.profile),))
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")
    store.enqueue(pid)
    batch_size = shots_per_request(store.settings())
    report = {
        "project_id": pid,
        "is_mock": False,
        "model": CPU_PROFILES[args.profile][0],
        "profile": f"CPU only; four threads;8192 context; max{batch_size} shots/section;three attempts/section",
        "shots_per_request": batch_size,
        "max_seconds": args.max_seconds,
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
            if time.monotonic() - started > args.max_seconds:
                raise RuntimeError(
                    f"TIMEOUT: CPU writing smoke reached its {args.max_seconds}-second ceiling."
                )
            super().check(step)

    worker = BoundedWorker(store, story_observer=observe, wait_for_resources=False)
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
                {
                    "id": step["id"],
                    "stage": step["stage"],
                    "seconds": round(time.monotonic() - before, 3),
                    "start": step["payload"].get("start"),
                    "count": step["payload"].get("count"),
                }
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
        atomic_json(
            Path(
                "ops/evidence/real-cpu-4b-batched-story.json"
                if args.profile == "cpu_4b"
                else "ops/evidence/real-cpu-batched-story.json"
            ),
            report,
        )
        print(json.dumps({k: v for k, v in report.items() if k not in {"plan", "script"}}, indent=2))


if __name__ == "__main__":
    main()
