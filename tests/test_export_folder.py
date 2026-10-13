import os

import pytest
from fastapi.testclient import TestClient

from studio import export_folder
from studio.api import create_app
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


@pytest.mark.skipif(os.name != "nt", reason="Windows Explorer launch contract")
def test_folder_api_validates_immutable_export_and_scoped_path(store, spec, monkeypatch):
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    project = produce_until(store, Worker(store), pid)
    movie = next(a for a in project["assets"] if a["role"] == "export")
    reference = next(a for a in project["assets"] if a["role"] == "reference")
    calls = []
    monkeypatch.setattr(export_folder, "open_selected_file", lambda path: calls.append(path))
    with TestClient(create_app(store.root, run_worker=False)) as client:
        endpoint = f"/api/assets/{movie['id']}/show-in-folder"
        assert client.post(endpoint, json={}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.post(endpoint, json={"path": "C:/Windows"}).status_code == 422
        assert client.post("/api/assets/not-an-asset/show-in-folder", json={}).status_code == 404
        assert client.post(f"/api/assets/{reference['id']}/show-in-folder", json={}).status_code == 409
        assert calls == []
        response = client.post(endpoint, json={})
        assert response.json() == {"asset_id": movie["id"], "launch_requested": True}
        assert calls.pop() == store.asset_path(movie["id"])[0]
        assert store.get(pid) == project
        store.asset_path(movie["id"])[0].write_bytes(b"damaged original sample")
        assert client.post(endpoint, json={}).status_code == 409 and calls == []


@pytest.mark.skipif(os.name != "nt", reason="Windows Explorer launch contract")
def test_folder_launch_failure_and_redirected_assets_are_actionable(store, spec, tmp_path, monkeypatch):
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    project = produce_until(store, Worker(store), pid)
    movie = next(a for a in project["assets"] if a["role"] == "export")

    def fail(*args, **kwargs):
        raise OSError("fixture launch refusal")

    monkeypatch.setattr(export_folder, "open_selected_file", fail)
    with TestClient(create_app(store.root, run_worker=False)) as client:
        endpoint = f"/api/assets/{movie['id']}/show-in-folder"
        response = client.post(endpoint, json={})
        assert response.status_code == 503 and "download the MP4" in response.json()["message"]
        with store.connect() as db:
            db.execute("UPDATE assets SET path=? WHERE id=?", (str(tmp_path / "outside.mp4"), movie["id"]))
        assert client.post(endpoint, json={}).status_code == 409
