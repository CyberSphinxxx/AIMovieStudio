import json

import pytest

from scripts import package_private as package
from scripts.prepare_app_runtime import digest
from tests.test_app_runtime import fixture_manifest


def prepared_fixture(root):
    source, data, _ = fixture_manifest(root)
    for relative in package.FILES:
        path = root / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"development package fixture")
    for relative in package.TREES:
        (root / relative).mkdir(parents=True, exist_ok=True)
    runtime = root / "tools/app-runtime"
    for row in data["base_files"]:
        (runtime / row["path"]).write_bytes((source / row["path"]).read_bytes())
    (runtime / "studio-runtime.json").write_text(
        json.dumps(
            {"status": "READY", "manifest_sha256": digest(root / "contracts/app-runtime-windows.json")}
        )
    )
    (root / "studio/code.py").write_text("# development fixture")
    (root / "client/dist/index.html").write_text("<html>Development fixture</html>")
    return runtime


def test_private_copy_verifies_inputs_and_excludes_models_data_and_development_runtime(tmp_path):
    prepared_fixture(tmp_path)
    for name in (
        "data/personal.txt",
        "tools/wan-gp/private.txt",
        "tools/story/model.gguf",
        ".venv/secret.txt",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"must remain only at source")
    original = {p.relative_to(tmp_path).as_posix(): digest(p) for p in tmp_path.rglob("*") if p.is_file()}
    target = package.build(tmp_path)
    receipt = json.loads((target / "private-build.json").read_text())
    assert receipt["private_only"] and not receipt["models_included"] and not receipt["user_data_included"]
    assert not receipt["distribution_cleared"] and not receipt["native_generation_verified"]
    for row in receipt["files"]:
        assert digest(target / row["path"]) == row["sha256"] == original[row["path"]]
    for name in ("data", "tools/wan-gp", "tools/story", ".venv"):
        assert not (target / name).exists()
    assert "PRIVATE DEVELOPMENT BUILD" in (target / "PRIVATE_BUILD.txt").read_text()
    for relative, sha in original.items():
        assert digest(tmp_path / relative) == sha
    assert package.build(tmp_path) != target


def test_changed_runtime_or_missing_media_never_publishes(tmp_path):
    runtime = prepared_fixture(tmp_path)
    original = (runtime / "python.exe").read_bytes()
    (runtime / "python.exe").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="executable changed"):
        package.build(tmp_path)
    assert not (tmp_path / "tools/private-builds").exists()
    (runtime / "python.exe").write_bytes(original)
    (tmp_path / "tools/ffmpeg/LICENSE").unlink()  # Only our tiny test fixture.
    with pytest.raises(FileNotFoundError):
        package.build(tmp_path)
    assert not (tmp_path / "tools/private-builds").exists()


def test_disk_reserve_failure_leaves_source_untouched(tmp_path, monkeypatch):
    prepared_fixture(tmp_path)
    from collections import namedtuple

    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(package.shutil, "disk_usage", lambda *_: usage(100, 100, 0))
    with pytest.raises(RuntimeError, match="disk reserve"):
        package.build(tmp_path)
    assert list((tmp_path / "tools/private-builds").iterdir()) == []
    assert (tmp_path / "studio/code.py").read_text() == "# development fixture"


def test_failed_copy_retains_diagnostics_and_no_finished_build(tmp_path, monkeypatch):
    prepared_fixture(tmp_path)

    def full_disk(*_):
        raise OSError("Development disk-full fixture")

    monkeypatch.setattr(package.shutil, "copyfile", full_disk)
    with pytest.raises(OSError, match="disk-full"):
        package.build(tmp_path)
    contents = list((tmp_path / "tools/private-builds").iterdir())
    assert len(contents) == 1 and contents[0].name.startswith(".building-")
