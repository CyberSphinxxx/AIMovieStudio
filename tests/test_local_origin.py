"""Local browser-origin regression; no model or external server is started."""

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_browser_can_fetch_its_own_local_assets_on_an_isolated_port(tmp_path, host):
    origin = f"http://{host}:60300"
    with TestClient(create_app(tmp_path / "library", run_worker=False), base_url=origin) as client:
        result = client.get("/api/health", headers={"Origin": origin})
    assert result.status_code == 200
    assert result.headers["Content-Security-Policy"].startswith("default-src 'self'")


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "http://127.0.0.1:60301",
        "http://localhost.evil.example:60300",
        "null",
        "http://127.0.0.1:60300@evil.example",
    ],
)
def test_foreign_origin_is_still_rejected_on_a_local_test_port(tmp_path, origin):
    with TestClient(
        create_app(tmp_path / "library", run_worker=False), base_url="http://127.0.0.1:60300"
    ) as client:
        result = client.get("/api/health", headers={"Origin": origin})
    assert result.status_code == 403 and result.json()["code"] == "INVALID_ORIGIN"


def test_testserver_host_does_not_create_a_new_browser_origin_exception(tmp_path):
    with TestClient(create_app(tmp_path / "library", run_worker=False)) as client:
        result = client.get("/api/health", headers={"Origin": "http://testserver"})
    assert result.status_code == 403
