"""Installer fixtures make no network requests or real model downloads."""

import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from scripts import setup_cpu_story as installer
from studio.storage import atomic_json


@pytest.fixture
def setup(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    atomic_json(ledger, {"received_bytes": 0, "completed": {}})
    monkeypatch.setattr(installer.shutil, "disk_usage", lambda _: SimpleNamespace(free=6_000_000_000))
    return tmp_path / "model.gguf", ledger


def respond(monkeypatch, content, status=200, offset=""):
    calls = []

    def request(req, **kwargs):
        calls.append(req)
        r = io.BytesIO(content)
        r.status = status
        r.headers = {"Content-Range": offset}
        return r

    monkeypatch.setattr(installer.urllib.request, "urlopen", request)
    return calls


def test_approval_required_before_network_or_file_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "TARGET", tmp_path / "absent")
    calls = respond(monkeypatch, b"unused")
    with pytest.raises(SystemExit) as error:
        installer.main([])
    assert error.value.code == 2
    assert not calls and not installer.TARGET.exists()


def test_resume_accounts_only_received_bytes_and_does_not_repeat(setup, monkeypatch):
    path, ledger = setup
    payload = b"0123456789"
    path.with_suffix(".gguf.partial").write_bytes(payload[:6])
    atomic_json(ledger, {"received_bytes": 96, "completed": {}})
    calls = respond(monkeypatch, payload[6:], 206, "bytes 6-9/10")
    sha = hashlib.sha256(payload).hexdigest()
    installer.fetch("https://fixture.invalid/model", path, 10, sha, ledger, 100)
    assert path.read_bytes() == payload
    assert json.loads(ledger.read_text())["received_bytes"] == 100
    installer.fetch("https://fixture.invalid/model", path, 10, sha, ledger, 100)
    assert len(calls) == 1


def test_budget_resume_and_checksum_rejections_preserve_work(setup, monkeypatch):
    path, ledger = setup
    sha = hashlib.sha256(b"0123456789").hexdigest()
    partial = path.with_suffix(".gguf.partial")
    partial.write_bytes(b"012345")
    atomic_json(ledger, {"received_bytes": 96, "completed": {}})
    respond(monkeypatch, b"0123456789")
    with pytest.raises(RuntimeError, match="refused resume"):
        installer.fetch("https://fixture.invalid/model", path, 10, sha, ledger, 100)
    assert partial.read_bytes() == b"012345"
    respond(monkeypatch, b"6789", 206, "bytes 0-3/10")
    with pytest.raises(RuntimeError, match="incorrect CPU resume"):
        installer.fetch("https://fixture.invalid/model", path, 10, sha, ledger, 100)
    partial.unlink()
    atomic_json(ledger, {"received_bytes": 0, "completed": {}})
    respond(monkeypatch, b"xxxxxxxxxx")
    with pytest.raises(RuntimeError, match="SHA256"):
        installer.fetch("https://fixture.invalid/model", path, 10, sha, ledger, 100)
    assert not path.exists() and json.loads(ledger.read_text())["received_bytes"] == 10


def test_disk_budget_and_existing_file_guards(setup, monkeypatch):
    path, ledger = setup
    calls = respond(monkeypatch, b"safe")
    sha = hashlib.sha256(b"safe").hexdigest()
    with pytest.raises(RuntimeError, match="budget"):
        installer.fetch("https://fixture.invalid/model", path, 4, sha, ledger, 3)
    monkeypatch.setattr(installer.shutil, "disk_usage", lambda _: SimpleNamespace(free=100))
    with pytest.raises(RuntimeError, match="disk reserve"):
        installer.fetch("https://fixture.invalid/model", path, 4, sha, ledger, 10)
    path.write_bytes(b"original")
    with pytest.raises(RuntimeError, match="Existing"):
        installer.fetch("https://fixture.invalid/model", path, 4, sha, ledger, 10)
    with pytest.raises(ValueError, match="SHA256"):
        installer.fetch("https://fixture.invalid/model", path, 4, "", ledger, 10)
    assert path.read_bytes() == b"original" and not calls


def test_finished_partial_publishes_without_an_http_range_past_eof(setup, monkeypatch):
    path, ledger = setup
    payload = b"finished"
    path.with_suffix(".gguf.partial").write_bytes(payload)
    atomic_json(ledger, {"received_bytes": 100, "completed": {}})
    calls = respond(monkeypatch, b"must-not-download")
    installer.fetch(
        "https://fixture.invalid/model", path, len(payload), hashlib.sha256(payload).hexdigest(), ledger, 100
    )
    assert path.read_bytes() == payload and not calls
    assert json.loads(ledger.read_text())["received_bytes"] == 100
