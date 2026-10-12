"""Three bounded SQLite-only kill/reopen cycles; no real projects or media."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from studio.diagnostics import memory_status, process_rss
from studio.domain import ProjectInput
from studio.processes import owned_process
from studio.storage import Store, atomic_json

WRITER = """
import sqlite3, sys, time
from pathlib import Path
database, pid, marker = sys.argv[1:]
with sqlite3.connect(database, timeout=10) as db:
    db.execute('PRAGMA foreign_keys=ON')
    count = 0
    while count < 10000:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE projects SET updated=? WHERE id=?', (time.time(), pid))
        db.execute("INSERT INTO events(project_id,kind,data,created) VALUES(?,?,?,?)",
                   (pid,'sqlite_probe',str(count),time.time()))
        db.commit()
        count += 1
        if count == 1: Path(marker).write_text('committed')
        time.sleep(0.002)
"""


def error_details(error: BaseException, phase: str) -> dict:
    return {
        "phase": phase,
        "type": type(error).__name__,
        "message": str(error),
        "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
        "sqlite_errorname": getattr(error, "sqlite_errorname", None),
        "notes": getattr(error, "__notes__", []),
    }


def run_probe(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "STARTED",
        "is_mock": True,
        "scope": "SQLite-only sample; no media/inference",
        "sqlite_version": sqlite3.sqlite_version,
        "preflight": memory_status(),
        "rounds": [],
        "fixture": str(root.resolve()),
        "errors": [],
    }
    started = time.monotonic()
    phase = "preflight"

    def resource_check():
        memory = memory_status()
        if memory.get("available") and memory["free_gb"] < 0.5:
            raise RuntimeError("RESOURCE_BUSY: SQLite-only probe stopped below 0.5 GiB available RAM.")
        if time.monotonic() - started > 45:
            raise RuntimeError("TIMEOUT: SQLite-only probe reached 45 seconds.")

    try:
        resource_check()
        store = Store(root)
        pid, _ = store.create(
            ProjectInput(idea="SQLite-only restart diagnostic sample.", idempotency_key=str(uuid4()))
        )
        expected_spec = store.get(pid)["spec"]
        for repetition in range(3):
            resource_check()
            round_result = {"number": repetition + 1, "reads_before_kill": 0, "reads_after_restart": 0}
            report["rounds"].append(round_result)
            marker = root / f"writer-{repetition}.ready"
            phase = "writer_start"
            with (root / f"writer-{repetition}.log").open("wb") as log:
                process = subprocess.Popen(
                    [sys.executable, "-c", WRITER, str(store.database), pid, str(marker)],
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    with owned_process(process):
                        deadline = time.monotonic() + 10
                        while not marker.exists():
                            resource_check()
                            if process.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError(
                                    "Writer exited or failed to reach its first committed transaction."
                                )
                            time.sleep(0.005)
                        phase = "concurrent_read"
                        for _ in range(20):
                            assert store.get(pid)["spec"] == expected_spec
                            round_result["reads_before_kill"] += 1
                        round_result["sampled_writer_rss_bytes"] = process_rss(process.pid)
                        process.kill()
                        process.wait(timeout=5)
                        round_result["hard_kill_exit_code"] = process.returncode
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
            phase = "first_read_after_kill"
            previous_retries = store.read_retries
            assert store.get(pid)["spec"] == expected_spec
            round_result["first_read_truncate_retries"] = store.read_retries - previous_retries
            phase = "reopen_initialization"
            store = Store(root)
            round_result["startup_truncate_retries"] = store.initialization_retries
            phase = "read_after_reopen"
            for _ in range(20):
                resource_check()
                assert store.get(pid)["spec"] == expected_spec
                round_result["reads_after_restart"] += 1
            with store.connect() as db:
                round_result["integrity"] = db.execute("PRAGMA integrity_check").fetchone()[0]
                assert round_result["integrity"] == "ok"
            round_result["reopened_read_truncate_retries"] = store.read_retries
        observed_retries = sum(
            r["first_read_truncate_retries"]
            + r["startup_truncate_retries"]
            + r["reopened_read_truncate_retries"]
            for r in report["rounds"]
        )
        report["status"] = "PASS_RECOVERED_TRUNCATE" if observed_retries else "PASS_NO_ERROR_OBSERVED"
    except Exception as error:
        report["status"] = "BLOCKED_RESOURCE" if str(error).startswith("RESOURCE_BUSY") else "FAILED"
        report["errors"].append(error_details(error, phase))
    report["seconds"] = round(time.monotonic() - started, 3)
    atomic_json(root / "report.json", report)
    return report


def main():
    root = Path("data/sqlite-restart-probes") / str(uuid4())
    report = run_probe(root)
    atomic_json(Path("ops/evidence/sqlite-restart-probe.json"), report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
