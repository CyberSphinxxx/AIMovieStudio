"""Observed CPU inference evidence, separate from deterministic provider tests."""

import json
import time
from pathlib import Path
from uuid import uuid4

from studio.domain import ProjectInput
from studio.domain import SeasonPlan, continuity_errors, validate_script
from studio.local_story import SmallCPUStory
from studio.storage import Store, atomic_json


def main():
    store = Store(Path("data/story-smoke"))
    spec = ProjectInput(
        idea="A lighthouse keeper receives a message from a ship lost at sea and chooses to rescue its last survivor.",
        kind="clip",
        target_seconds=10,
        idempotency_key=str(uuid4()),
        backend="local",
    )
    pid, _ = store.create(spec)
    project = store.get(pid)
    provider = SmallCPUStory()
    started = time.monotonic()
    report = {
        "backend": "llama.cpp CPU",
        "is_mock": False,
        "model": provider.model,
        "project_id": pid,
        "status": "STARTED",
        "stage": "PLAN",
        "quality_review": "Not performed. Small feasibility model; no cinematic/story-quality guarantee.",
    }
    try:
        result = provider.plan(project)
        report.update(
            elapsed_seconds=round(time.monotonic() - started, 3),
            episode_count=len(result.episodes),
            plan=result.model_dump(),
            stage="SCRIPT",
        )
        project["plan"] = result.model_dump()
        script_started = time.monotonic()
        script = provider.script(project, 1)
        report.update(
            script=script.model_dump(),
            script_elapsed_seconds=round(time.monotonic() - script_started, 3),
            stage="CONTINUITY",
        )
        validate_script(script, SeasonPlan.model_validate(project["plan"]), spec.target_seconds)
        conflicts = continuity_errors(script, [], result)
        if conflicts:
            raise RuntimeError("CANON_CONFLICT: " + "; ".join(conflicts))
        report.update(status="STRUCTURED_PLAN_AND_SCRIPT_VALID", stage="FINISHED")
    except Exception as error:
        report.update(status="FAILED", error=str(error))
        raise
    finally:
        report["total_elapsed_seconds"] = round(time.monotonic() - started, 3)
        atomic_json(Path("ops/evidence/real-story-plan.json"), report)
        atomic_json(Path(f"ops/evidence/real-story-runs/{pid}.json"), report)
        print(json.dumps({k: v for k, v in report.items() if k not in {"plan", "script"}}, indent=2))


if __name__ == "__main__":
    main()
