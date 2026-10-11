"""Development-only network fixtures; no model or runtime is downloaded here."""

import hashlib
import io
from types import SimpleNamespace

import pytest

from scripts import setup_gpu as installer


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    target = tmp_path / "tools/gpu"
    target.mkdir(parents=True)
    monkeypatch.setattr(installer, "ROOT", tmp_path)
    monkeypatch.setattr(installer, "TARGET", target)
    monkeypatch.setattr(installer, "LIMIT", 100)
    monkeypatch.setattr(installer, "RESERVE", 10)
    monkeypatch.setattr(installer, "MIN_FREE", 10)
    monkeypatch.setattr(installer.shutil, "disk_usage", lambda _: SimpleNamespace(free=1000))
    return target


def response(monkeypatch, content, status=200, content_range=""):
    requests = []

    def open_url(request, **kwargs):
        requests.append(request)
        stream = io.BytesIO(content)
        stream.status = status
        stream.headers = {"Content-Range": content_range}
        return stream

    monkeypatch.setattr(installer.urllib.request, "urlopen", open_url)
    return requests


def test_resumed_download_charges_only_received_bytes_and_verifies_hash(downloads, monkeypatch):
    data = b"0123456789"
    path = downloads / "model.bin"
    path.with_suffix(".bin.partial").write_bytes(data[:6])
    state = installer.ledger()
    state["received_bytes"] = 96
    installer.save(state)
    requests = response(monkeypatch, data[6:], 206, "bytes 6-9/10")
    installer.fetch("https://fixture.invalid/model", path, 10, hashlib.sha256(data).hexdigest())
    assert path.read_bytes() == data
    assert requests[0].headers["Range"] == "bytes=6-"
    assert installer.ledger()["received_bytes"] == 100
    installer.fetch("https://fixture.invalid/model", path, 10, hashlib.sha256(data).hexdigest())
    assert len(requests) == 1  # Already verified file makes no network request.


def test_resume_refusal_or_wrong_offset_preserves_partial(downloads, monkeypatch):
    data = b"0123456789"
    path = downloads / "model.bin"
    partial = path.with_suffix(".bin.partial")
    partial.write_bytes(data[:6])
    state = installer.ledger()
    state["received_bytes"] = 96
    installer.save(state)
    response(monkeypatch, data)
    with pytest.raises(RuntimeError, match="refused resume"):
        installer.fetch("https://fixture.invalid/model", path, 10, hashlib.sha256(data).hexdigest())
    assert partial.read_bytes() == data[:6] and not path.exists()
    response(monkeypatch, data[6:], 206, "bytes 0-3/10")
    with pytest.raises(RuntimeError, match="resume offset"):
        installer.fetch("https://fixture.invalid/model", path, 10, hashlib.sha256(data).hexdigest())
    assert partial.read_bytes() == data[:6]


def test_budget_disk_and_checksum_failures_never_publish(downloads, monkeypatch):
    path = downloads / "model.bin"
    sha = hashlib.sha256(b"safe").hexdigest()
    requests = response(monkeypatch, b"evil")
    installer.reserve("runtime", 99)
    with pytest.raises(RuntimeError, match="budget"):
        installer.fetch("https://fixture.invalid/model", path, 4, sha)
    assert not requests
    with pytest.raises(RuntimeError, match="checksum"):
        installer.fetch("https://fixture.invalid/model", path, 4, sha, reservation="runtime")
    assert not path.exists()
    assert installer.ledger()["received_bytes"] == 4
    assert installer.ledger()["reservations"]["runtime"] == 95
    monkeypatch.setattr(installer.shutil, "disk_usage", lambda _: SimpleNamespace(free=9))
    with pytest.raises(RuntimeError, match="disk reserve"):
        installer.fetch(
            "https://fixture.invalid/another", downloads / "another.bin", 4, sha, reservation="runtime"
        )


def test_existing_file_is_never_overwritten_and_missing_checksum_rejected(downloads, monkeypatch):
    path = downloads / "model.bin"
    path.write_bytes(b"original")
    requests = response(monkeypatch, b"new")
    with pytest.raises(RuntimeError, match="different checksum"):
        installer.fetch("https://fixture.invalid/model", path, 3, hashlib.sha256(b"new").hexdigest())
    with pytest.raises(ValueError, match="SHA256"):
        installer.fetch("https://fixture.invalid/model", path, 3, "")
    assert path.read_bytes() == b"original" and not requests


def test_finished_partial_publishes_without_network_or_extra_budget(downloads, monkeypatch):
    path = downloads / "finished.bin"
    payload = b"finished"
    path.with_suffix(".bin.partial").write_bytes(payload)
    state = installer.ledger()
    state["received_bytes"] = 100
    installer.save(state)
    requests = response(monkeypatch, b"must-not-download")
    installer.fetch("https://fixture.invalid/model", path, len(payload), hashlib.sha256(payload).hexdigest())
    assert path.read_bytes() == payload and not requests
    assert installer.ledger()["received_bytes"] == 100
