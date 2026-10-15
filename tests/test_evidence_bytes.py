"""Git checkout integrity for immutable proof; isolated repositories, no remotes."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,content",
    [
        ("ops/evidence/nested/model receipt.json", b'{\r\n  "status": "FAILED"\r\n}\r\n'),
        ("ops/archive/handoff.md", b"# Saved history\n\nExact LF bytes must survive checkout.\n"),
        ("ops/evidence/failure.log", b"E  Captured failure spacing is evidence. \r\nE    \r\n"),
    ],
)
def test_proof_bytes_survive_index_and_windows_style_checkout(tmp_path, name, content):
    repository, export = tmp_path / "repository", tmp_path / "checkout"
    repository.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "core.autocrlf=true", *args], cwd=repository, stderr=subprocess.PIPE
        )

    git("init", "-q")
    attributes = ROOT / ".gitattributes"
    if attributes.exists():
        (repository / ".gitattributes").write_bytes(attributes.read_bytes())
    sample = repository / name
    sample.parent.mkdir(parents=True)
    sample.write_bytes(content)
    git("add", ".")
    git("diff", "--cached", "--check")
    assert git("show", ":" + name) == content, "Git normalization changed checksum-bearing proof bytes"
    export.mkdir()
    git("checkout-index", "--all", "--prefix=" + export.as_posix() + "/")
    assert (export / name).read_bytes() == content, "Checkout changed archived proof bytes"
