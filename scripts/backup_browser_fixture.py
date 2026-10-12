"""Development-only watermarked media archive for graphical restore E2E."""

import json
import argparse
import os
import shutil
from pathlib import Path
from uuid import uuid4

from studio.backup import create_backup
from studio.domain import ProjectInput
from studio.storage import Store, atomic_json
from studio.worker import Worker
from studio import backup_import


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pending", action="store_true", help="Stage this sample for Settings Resume in the default studio"
    )
    args = parser.parse_args()
    directory = Path("data/browser-restore-fixtures") / str(uuid4())
    store = Store(directory / "source")
    with store.connect() as db:
        db.execute("INSERT INTO settings VALUES('speech','\"none\"')")
    spec = ProjectInput(
        idea=f"Restore {str(uuid4())[:8]} observatory finds a lost signal.",
        target_seconds=5,
        backend="demo",
        idempotency_key=str(uuid4()),
    )
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    while step := worker.claim():
        output = worker.execute(step)
        worker.verify(output)
        atomic_json(worker.directory(step) / "receipt.json", output)
        worker.complete(step, output)
    project = store.get(pid)
    if project["status"] != "COMPLETED":
        raise RuntimeError("Development fixture did not complete")
    archive = create_backup(store, directory / "fixture.zip")
    result = {
        "archive": str(archive.resolve()),
        "id": pid,
        "title": project["title"],
        "is_mock": True,
        "asset_hashes": {a["id"]: a["sha256"] for a in project["assets"]},
    }
    if args.pending:
        studio_root = Path(os.environ.get("STUDIO_DATA", Path(__file__).resolve().parents[1] / "data"))
        current = Store(studio_root)
        identity, operation = backup_import.begin_upload(current)
        shutil.copyfile(archive, operation / "upload.zip")
        backup_import.prepare_import(current, identity)
        result["operation_id"] = identity
    print(json.dumps(result))


if __name__ == "__main__":
    main()
