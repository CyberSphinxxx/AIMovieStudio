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
    parser.add_argument(
        "--reuse-plan",
        action="store_true",
        help="Reuse the saved failed 4B plan in a new isolated experiment",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare the isolated saved-plan test without loading any model",
    )
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 600:
        parser.error("Writing test ceiling must be between 1 and 600 seconds")
    if args.prepare_only and not args.reuse_plan:
        parser.error("--prepare-only requires --reuse-plan")
    if args.reuse_plan and (args.profile != "cpu_4b" or args.max_seconds > 320):
        parser.error("Saved-plan reuse requires --profile cpu_4b --max-seconds 320 (or less)")
    if args.profile == "cpu_4b" and not args.reuse_plan:
        parser.error(
            "The 4B experiment already used 269.719 seconds; use --reuse-plan within its remaining allowance"
        )
    started = time.monotonic()
    lineage = None
    run_id = str(uuid4())
    if args.reuse_plan:
        from scripts.story_plan_retest import SOURCE_PROJECT, prepare_plan_retest, reserve_retest_budget
        from studio.local_story import require_startup_memory

        if not args.prepare_only:
            require_startup_memory("cpu_4b")
        store, lineage = prepare_plan_retest(
            Path("data/cpu-4b-writing-smoke"),
            SOURCE_PROJECT,
            Path(f"ops/evidence/cpu-writing-runs/{SOURCE_PROJECT}.json"),
            Path("data/cpu-4b-plan-retests") / run_id,
            run_id,
        )
        pid = SOURCE_PROJECT
        if args.prepare_only:
            print(
                json.dumps({"status": "PREPARED_NOT_RUN", "workspace": str(store.root), **lineage}, indent=2)
            )
            return
        reserve_retest_budget(
            Path("ops/evidence/cpu-4b-retest-reservation.json"),
            args.max_seconds,
            run_id,
            lineage,
        )
        store.control(pid, "resume")
    else:
        store, pid = create_sample(args.profile)
    run_writing_test(store, pid, args.profile, args.max_seconds, started, run_id if lineage else pid, lineage)


def create_sample(profile):
    store = Store(Path("data/cpu-4b-writing-smoke" if profile == "cpu_4b" else "data/cpu-writing-smoke"))
    spec = ProjectInput(
        idea="A lighthouse keeper receives a message from a ship lost at sea. She rescues its last survivor by giving up the lamp that guides ships home. End with the survivor safely ashore and the keeper facing the cost of her choice.",
        kind="drama",
        target_seconds=40,
        backend="local",
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('story_engine',?)", (json.dumps(profile),))
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")
    store.enqueue(pid)
    return store, pid


def run_writing_test(store, pid, profile, max_seconds, started, run_id, lineage=None):
    report_path = Path(f"ops/evidence/cpu-writing-runs/{run_id}.json")
    if report_path.exists() or (lineage and run_id == pid):
        raise ValueError("Refuse to overwrite an existing experiment report")
    batch_size = shots_per_request(store.settings())
    report = {
        "run_id": run_id,
        "project_id": pid,
        "is_mock": False,
        "model": CPU_PROFILES[profile][0],
        "profile": f"CPU only; four threads;8192 context; max{batch_size} shots/section;three attempts/section",
        "shots_per_request": batch_size,
        "max_seconds": max_seconds,
        "status": "STARTED",
        "quality_review": "NOT_PERFORMED",
        "preflight_memory": memory_status(),
        "samples": 0,
        "sampled_peak_server_rss_bytes": None,
        "sampled_min_available_ram_gib": None,
        "completed_steps": [],
        "lineage": lineage,
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
            if time.monotonic() - started > max_seconds:
                raise RuntimeError(f"TIMEOUT: CPU writing smoke reached its {max_seconds}-second ceiling.")
            super().check(step)

    worker = BoundedWorker(store, story_observer=observe, wait_for_resources=False)
    step = None
    try:
        while step := worker.claim():
            report["stage"] = step["stage"]
            if step["stage"] not in {"PLAN", "SCRIPT_BATCH", "SCRIPT"}:
                raise RuntimeError("Unexpected visual/audio stage in writing-only test")
            before = time.monotonic()
            worker.check(step)
            output = worker.execute(step)
            worker.check(step)
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
        if report["status"] != "STRUCTURED_BATCHED_SCRIPT_VALID":
            raise RuntimeError("INCOMPLETE_STORY: No complete screenplay was produced")
    except Exception as error:
        report.update(status="FAILED", error=str(error))
        if step:
            with store.connect() as db:
                db.execute("UPDATE steps SET state='FAILED',error=? WHERE id=?", (str(error), step["id"]))
                db.execute("UPDATE jobs SET state='FAILED',error=? WHERE id=?", (str(error), step["job_id"]))
                db.execute("UPDATE projects SET status='FAILED' WHERE id=?", (pid,))
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
        atomic_json(Path(f"ops/evidence/cpu-writing-runs/{run_id}.json"), report)
        atomic_json(
            Path(
                "ops/evidence/real-cpu-4b-batched-story.json"
                if profile == "cpu_4b"
                else "ops/evidence/real-cpu-batched-story.json"
            ),
            report,
        )
        print(json.dumps({k: v for k, v in report.items() if k not in {"plan", "script"}}, indent=2))


if __name__ == "__main__":
    main()
