import os
import subprocess
import sys
import time

from studio.storage import Store


def await_condition(check, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.04)
    raise AssertionError("Timed out waiting for worker state")


def test_hard_kill_mid_ten_shots_preserves_committed_hashes(store, spec):
    spec.kind, spec.target_seconds = "drama", 50
    pid, _ = store.create(spec)
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('speech','\"none\"')")
    store.enqueue(pid)
    env = os.environ | {"STUDIO_DATA": str(store.root)}
    process = subprocess.Popen(
        [sys.executable, "-m", "studio.run_worker"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:

        def fifth_clip():
            assets = [a for a in store.get(pid)["assets"] if a["role"] == "clip"]
            return assets if len(assets) >= 5 else None

        committed = await_condition(fifth_clip)
        assert 5 <= len(committed) < 10
        process.kill()  # Windows TerminateProcess: no finally block, no graceful shutdown.
        process.wait(timeout=10)
        before = {a["id"]: a["sha256"] for a in committed}
        reopened = Store(store.root)
        restarted = subprocess.Popen(
            [sys.executable, "-m", "studio.run_worker"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await_condition(lambda: reopened.get(pid)["status"] == "COMPLETED", timeout=90)
            result = reopened.get(pid)
            clips = [a for a in result["assets"] if a["role"] == "clip"]
            assert len(clips) == 10 and len({a["id"] for a in clips}) == 10
            assert all(
                next(a for a in clips if a["id"] == aid)["sha256"] == sha for aid, sha in before.items()
            )
            assert len([a for a in result["assets"] if a["role"] == "soundtrack"]) == 1
            assert len(result["canon"]) == 1
        finally:
            restarted.kill()
            restarted.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
