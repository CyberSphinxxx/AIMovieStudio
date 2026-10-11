"""Observed CPU inference evidence, separate from deterministic provider tests."""

import json
import time
from pathlib import Path

from studio.domain import ProjectInput
from studio.local_story import SmallCPUStory
from studio.storage import Store, atomic_json


def main():
    store = Store(Path("data/story-smoke"))
    spec = ProjectInput(
        idea="A lighthouse keeper receives a message from a ship lost at sea and chooses to rescue its last survivor.",
        kind="clip",
        target_seconds=10,
        idempotency_key="real-cpu-smoke-v1",
        backend="local",
    )
    pid, _ = store.create(spec)
    project = store.get(pid)
    provider = SmallCPUStory()
    started = time.monotonic()
    result = provider.plan(project)
    elapsed = time.monotonic() - started
    report = {
        "backend": "llama.cpp CPU",
        "is_mock": False,
        "model": provider.model,
        "status": "STRUCTURED_PLAN_VALID",
        "elapsed_seconds": round(elapsed, 3),
        "episode_count": len(result.episodes),
        "plan": result.model_dump(),
        "quality_review": "Not performed. Small feasibility model; no cinematic/story-quality guarantee.",
    }
    atomic_json(Path("ops/evidence/real-story-plan.json"), report)
    print(json.dumps({k: v for k, v in report.items() if k != "plan"}, indent=2))


if __name__ == "__main__":
    main()
