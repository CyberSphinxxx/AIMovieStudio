"""Private installer failure tests; tiny fixtures are never executable Python/wheels."""

import copy
import hashlib
import io
import json
import subprocess
from pathlib import Path

import pytest

from scripts import prepare_app_runtime as runtime


def fixture_manifest(root):
    source = root / "reviewed base"
    source.mkdir()
    rows = []
    for name in ("python.exe", "python311.dll", "LICENSE.txt"):
        content = ("fixture " + name).encode()
        (source / name).write_bytes(content)
        rows.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    content = b"development wheel fixture"
    wheel = {
        "name": "fixture",
        "version": "1.0",
        "filename": "fixture-1.0-py3-none-any.whl",
        "url": "https://files.pythonhosted.org/packages/fixture.whl",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    (root / "contracts").mkdir()
    (root / "requirements.txt").write_bytes(b"fixture==1.0\n")
    data = {
        "schema": 1,
        "platform": "win_amd64",
        "python_version": "3.11.14",
        "base_files": rows,
        "artifacts": [wheel],
        "base_bytes": sum(r["bytes"] for r in rows),
        "wheel_bytes": len(content),
        "requirements_sha256": runtime.digest(root / "requirements.txt"),
    }
    path = root / "contracts/app-runtime-windows.json"
    path.write_text(json.dumps(data))
    return source, data, content


class Response(io.BytesIO):
    def __init__(self, content, size=None):
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content) if size is None else size)}


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def open(self, *_args, **_kwargs):
        self.calls += 1
        return self.response


def test_successful_download_is_checksummed_charged_and_reused(tmp_path):
    _, data, content = fixture_manifest(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    ledger = {"received_bytes": 0, "allocated_bytes": 0}
    opener = Opener(Response(content))
    row = data["artifacts"][0]
    result = runtime.fetch(row, cache, ledger, True, opener=opener)
    assert result.read_bytes() == content
    assert ledger == {"received_bytes": len(content), "allocated_bytes": len(content)}
    assert json.loads((cache / "download-ledger.json").read_text()) == ledger
    assert runtime.fetch(row, cache, ledger, False, opener=opener) == result
    assert opener.calls == 1


@pytest.mark.parametrize("failure", ["truncated", "checksum", "length", "network"])
def test_failed_download_retains_conservative_allocation_and_never_publishes(tmp_path, failure):
    _, data, content = fixture_manifest(tmp_path)
    row = data["artifacts"][0]
    cache = tmp_path / "cache"
    cache.mkdir()
    ledger = {"received_bytes": 0, "allocated_bytes": 0}
    response = Response(
        content[:3] if failure == "truncated" else b"x" * len(content) if failure == "checksum" else content,
        size=row["bytes"] + (1 if failure == "length" else 0),
    )
    opener = Opener(response)
    if failure == "network":

        def unreachable(*_args, **_kwargs):
            raise OSError("Development network failure")

        opener.open = unreachable
    with pytest.raises((OSError, RuntimeError)):
        runtime.fetch(row, cache, ledger, True, opener=opener)
    assert not (cache / row["filename"]).exists()
    saved = json.loads((cache / "download-ledger.json").read_text())
    assert saved["allocated_bytes"] == len(content)
    assert saved["received_bytes"] <= saved["allocated_bytes"]


def test_budget_offline_and_corrupt_cache_refuse_without_network(tmp_path, monkeypatch):
    _, data, content = fixture_manifest(tmp_path)
    row = data["artifacts"][0]
    cache = tmp_path / "cache"
    cache.mkdir()
    opener = Opener(Response(content))
    ledger = {"received_bytes": 0, "allocated_bytes": runtime.LIMIT}
    with pytest.raises(RuntimeError, match="budget"):
        runtime.fetch(row, cache, ledger, True, opener=opener)
    with pytest.raises(RuntimeError, match="Offline wheel missing"):
        runtime.fetch(row, cache, ledger, False, opener=opener)
    (cache / row["filename"]).write_bytes(b"corrupt original")
    with pytest.raises(RuntimeError, match="checksum"):
        runtime.fetch(row, cache, ledger, True, opener=opener)
    assert (cache / row["filename"]).read_bytes() == b"corrupt original"
    assert opener.calls == 0


@pytest.mark.parametrize("path", ["../escape", "C:/escape", "a\\b", "/escape", "a/./b", "a//b"])
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValueError, match="unsafe"):
        runtime.safe_relative(path)


@pytest.mark.parametrize("change", ["http", "other-host", "oversize", "duplicate", "missing-license"])
def test_manifest_rejects_unreviewed_downloads(tmp_path, change):
    _, data, _ = fixture_manifest(tmp_path)
    if change in {"http", "other-host"}:
        data["artifacts"][0]["url"] = (
            "http://files.pythonhosted.org/x" if change == "http" else "https://example.com/x"
        )
    elif change == "oversize":
        data["artifacts"][0]["bytes"] = data["wheel_bytes"] = runtime.LIMIT + 1
    elif change == "duplicate":
        data["artifacts"].append(copy.deepcopy(data["artifacts"][0]))
    else:
        data["base_files"] = [r for r in data["base_files"] if r["path"] != "LICENSE.txt"]
        data["base_bytes"] = sum(r["bytes"] for r in data["base_files"])
    path = tmp_path / "contracts/app-runtime-windows.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        runtime.load_manifest(path)


def test_changed_source_and_existing_runtime_preserve_originals(tmp_path):
    source, _, _ = fixture_manifest(tmp_path)
    (source / "python.exe").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="differs from reviewed base"):
        runtime.prepare(tmp_path, source)
    assert (source / "python.exe").read_bytes() == b"changed"
    assert not (tmp_path / "tools/app-runtime").exists()
    assert not (tmp_path / "tools/app-runtime-cache/setup.lock").exists()
    target = tmp_path / "tools/app-runtime"
    target.mkdir()
    sentinel = target / "original.txt"
    sentinel.write_bytes(b"keep")
    with pytest.raises(RuntimeError, match="already exists"):
        runtime.prepare(tmp_path, source)
    assert sentinel.read_bytes() == b"keep"


def test_setup_lock_after_interruption_requires_review(tmp_path):
    source, _, _ = fixture_manifest(tmp_path)
    lock = tmp_path / "tools/app-runtime-cache/setup.lock"
    lock.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="already running or was interrupted"):
        runtime.prepare(tmp_path, source)
    assert lock.exists()


def test_offline_install_failure_never_publishes_or_changes_source(tmp_path, monkeypatch):
    source, data, content = fixture_manifest(tmp_path)
    (tmp_path / "requirements.txt").write_bytes(b"fixture==1.0\r\n")
    wheels = tmp_path / "tools/app-runtime-cache/wheels"
    wheels.mkdir(parents=True)
    (wheels / data["artifacts"][0]["filename"]).write_bytes(content)
    calls = []

    def failed_install(argv, **kwargs):
        calls.append((argv, kwargs))
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(runtime.subprocess, "run", failed_install)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.prepare(tmp_path, source)
    argv, options = calls[0]
    assert "--no-index" in argv and "--require-hashes" in argv
    assert Path(argv[argv.index("--target") + 1]).is_relative_to(tmp_path / "tools/app-runtime-cache")
    assert options["env"]["PIP_CONFIG_FILE"] == runtime.os.devnull
    assert not (tmp_path / "tools/app-runtime").exists()
    assert not (tmp_path / "tools/app-runtime-cache/setup.lock").exists()
    for row in data["base_files"]:
        assert runtime.digest(source / row["path"]) == row["sha256"]


def test_redirect_cannot_send_downloads_to_another_host():
    import urllib.request

    handler = runtime.OfficialRedirect()
    with pytest.raises(ValueError, match="redirected"):
        handler.redirect_request(
            urllib.request.Request("https://files.pythonhosted.org/a"),
            None,
            302,
            "redirect",
            {},
            "https://example.com/secret",
        )


def test_windows_transient_ledger_lock_has_bounded_retry(tmp_path, monkeypatch):
    if runtime.os.name != "nt":
        pytest.skip("Observed Windows file-sharing race")
    original = runtime.os.replace
    calls = []

    def busy_twice(source, target):
        calls.append(True)
        if len(calls) < 3:
            error = PermissionError("Development sharing violation")
            error.winerror = 5
            raise error
        original(source, target)

    monkeypatch.setattr(runtime.os, "replace", busy_twice)
    monkeypatch.setattr(runtime.time, "sleep", lambda _: None)
    path = tmp_path / "ledger.json"
    runtime.atomic_json(path, {"received_bytes": 10})
    assert len(calls) == 3
    assert json.loads(path.read_text()) == {"received_bytes": 10}

    def busy_forever(*_):
        error = PermissionError("Development persistent sharing violation")
        error.winerror = 5
        raise error

    monkeypatch.setattr(runtime.os, "replace", busy_forever)
    with pytest.raises(PermissionError):
        runtime.atomic_json(path, {"received_bytes": 99})
    assert json.loads(path.read_text()) == {"received_bytes": 10}
