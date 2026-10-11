from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.domain import ProjectInput


def test_create_reopen_and_idempotency(tmp_path, spec):
    app = create_app(tmp_path, run_worker=False)
    with TestClient(app) as client:
        first = client.post("/api/projects", json=spec.model_dump())
        assert first.status_code == 201, first.text
        pid = first.json()["id"]
        assert client.post("/api/projects", json=spec.model_dump()).json()["id"] == pid
        different = spec.model_dump() | {"idea": "A completely different movie idea."}
        assert client.post("/api/projects", json=different).status_code == 409
        assert len(client.get("/api/projects").json()) == 1
    with TestClient(create_app(tmp_path, run_worker=False)) as client:
        assert client.get(f"/api/projects/{pid}").json()["spec"]["idea"] == spec.idea


def test_input_security_and_errors(tmp_path, spec):
    with TestClient(create_app(tmp_path, run_worker=False)) as client:
        assert client.post("/api/projects", json=spec.model_dump() | {"idea": " "}).status_code == 422
        assert (
            client.post("/api/projects", json=spec.model_dump() | {"target_seconds": 31}).status_code == 422
        )
        assert (
            client.post(
                "/api/projects", json=spec.model_dump(), headers={"Origin": "https://hostile.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/health", headers={"Host": "hostile.example"}).status_code == 403
        assert client.post("/api/projects", content=b"x" * 65537).status_code == 413
        assert client.get("/api/assets/does-not-exist/content").status_code == 404
        assert client.get("/api/nonexistent").status_code == 404
        unicode_spec = spec.model_dump() | {
            "idea": "星の海で、旅人は静かな灯台を見つける。",
            "idempotency_key": "unicode-example",
        }
        assert client.post("/api/projects", json=unicode_spec).status_code == 201


def test_concurrent_creates_and_enqueue(store, spec):
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: store.create(spec)[0], range(25)))
    assert len(set(results)) == 1
    with ThreadPoolExecutor(8) as pool:
        jobs = list(pool.map(lambda _: store.enqueue(results[0]), range(25)))
    assert len(set(jobs)) == 1
    with store.connect() as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_path_confinement(store):
    for path in ["../secret", "C:/Windows/System32/drivers/etc/hosts", str(store.root)]:
        with pytest.raises(ValueError):
            store.resolve(path)


def test_pause_cancel_terminal(store, spec):
    pid, _ = store.create(spec)
    store.enqueue(pid)
    store.control(pid, "pause")
    assert store.get(pid)["jobs"][0]["state"] == "PAUSED"
    store.control(pid, "resume")
    assert store.get(pid)["jobs"][0]["state"] == "QUEUED"
    store.control(pid, "cancel")
    with pytest.raises(ValueError, match="terminal"):
        store.control(pid, "resume")


def test_limits():
    with pytest.raises(ValueError):
        ProjectInput(idea="Idea with a null\x00 character", idempotency_key="unique-key")
