import json
from pathlib import Path

import pytest

from scripts.license_inventory import inventory, node_inventory, notice_record, python_inventory


def test_metadata_only_python_inventory_and_notice_checksums(tmp_path):
    site = tmp_path / "env"
    dist = site / "example-1.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: example\nVersion: 1.0\nLicense-Expression: MIT\n"
    )
    (dist / "LICENSE").write_text("A test license notice.")
    (dist / "RECORD").write_text("example-1.0.dist-info/LICENSE,,\n")
    # If package code is ever imported, this test fails; metadata inspection must not run it.
    (site / "example.py").write_text("raise RuntimeError('DO NOT IMPORT')")
    items, findings = python_inventory(tmp_path, "env", "test")
    assert findings == []
    assert items[0]["declaration"] == "MIT"
    assert len(items[0]["notices"][0]["sha256"]) == 64
    assert items[0]["notices"][0]["path"] == "env/example-1.0.dist-info/LICENSE"


def test_node_inventory_missing_optional_license_and_lock_mismatch(tmp_path):
    directory = tmp_path / "client/node_modules/test-package"
    directory.mkdir(parents=True)
    (directory / "package.json").write_text(json.dumps({"name": "test-package", "version": "2.0"}))
    (tmp_path / "client/package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {},
                    "node_modules/test-package": {"version": "1.0"},
                    "node_modules/absent": {"version": "1.0", "optional": True},
                    "../outside": {"version": "1.0"},
                }
            }
        )
    )
    items, findings = node_inventory(tmp_path)
    assert len(items) == 1 and items[0]["declaration"] is None
    assert any("version differs" in f for f in findings)
    assert any("optional=True" in f for f in findings)
    assert any("external package" in f for f in findings)
    assert any("no installed notice" in f for f in findings)


def test_notice_path_confinement_size_and_missing_file(tmp_path):
    boundary = tmp_path / "package"
    boundary.mkdir()
    outside = tmp_path / "LICENSE"
    outside.write_text("An outside notice")
    with pytest.raises(ValueError, match="escapes"):
        notice_record(outside, boundary, tmp_path)
    with pytest.raises(ValueError, match="missing"):
        notice_record(boundary / "MISSING", boundary, tmp_path)
    huge = boundary / "LICENSE"
    huge.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="limit"):
        notice_record(huge, boundary, tmp_path)


def test_empty_environment_is_not_a_rights_clearance(tmp_path):
    report = inventory(tmp_path)
    assert report["status"] == "INVENTORY_ONLY_NOT_CLEARED"
    assert report["components"] == [] and report["standalone_notices"] == []
    assert report["native_dependencies_imported"] is False and report["no_network"] is True
    assert any("environment not installed" in f for f in report["findings"])


def test_untrusted_record_does_not_hash_an_external_notice(tmp_path):
    site = tmp_path / "env"
    dist = site / "bad-1.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: bad\nVersion: 1\n")
    (dist / "RECORD").write_text("../LICENSE,,\n")
    (tmp_path / "LICENSE").write_text("Outside the environment")
    items, findings = python_inventory(tmp_path, "env", "test")
    assert items[0]["notices"] == []
    assert any("redirected notice" in f for f in findings)
    assert not any(str(Path(tmp_path)) in f for f in findings)


def test_capture_download_ceiling_retains_failure_receipt(tmp_path, monkeypatch):
    from scripts.capture_license_sources import LIMIT, capture

    (tmp_path / "ops/evidence").mkdir(parents=True)
    (tmp_path / "ops/evidence/gpu-download-proposal.json").write_text(
        json.dumps({"revisions": {"DeepBeepMeep/Flux2": "abc"}})
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self, count):
            return b"x" * count

    monkeypatch.setattr(
        "scripts.capture_license_sources.urllib.request.urlopen", lambda *_args, **_kwargs: Response()
    )
    with pytest.raises(RuntimeError, match="ceiling"):
        capture(tmp_path)
    receipt = json.loads((tmp_path / "ops/evidence/model-license-sources.json").read_text())
    assert receipt["status"] == "PARTIAL_SOURCE_CAPTURE"
    assert receipt["received_bytes"] == LIMIT and receipt["sources"] == []


def test_captured_notice_checksum_cannot_silently_change(tmp_path):
    from studio.storage import digest

    path = tmp_path / "tools/licenses/test-LICENSE"
    path.parent.mkdir(parents=True)
    path.write_text("Pinned notice.")
    index = tmp_path / "ops/evidence/model-license-sources.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps({"sources": [{"path": path.relative_to(tmp_path).as_posix(), "sha256": digest(path)}]})
    )
    assert len(inventory(tmp_path)["standalone_notices"]) == 1
    path.write_text("Changed notice.")
    report = inventory(tmp_path)
    assert len(report["standalone_notices"]) == 0
    assert any("changed" in f for f in report["findings"])


def test_external_python_environment_is_not_scanned(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "external").mkdir()
    items, findings = python_inventory(root, "../external", "test")
    assert items == [] and findings == ["test: environment redirected outside workspace"]


def test_small_source_capture_preserves_original_at_pinned_revision(tmp_path, monkeypatch):
    from scripts.capture_license_sources import capture

    (tmp_path / "ops/evidence").mkdir(parents=True)
    proposal = {
        "revisions": {"DeepBeepMeep/Flux2": "c" * 40},
        "files": [{"file": "flux2_vae.safetensors", "sha256": "d" * 64}],
    }
    (tmp_path / "ops/evidence/gpu-download-proposal.json").write_text(json.dumps(proposal))
    changed = False

    class Response:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self, count):
            if "/api/models/" in self.url:
                return json.dumps(
                    {
                        "sha": "a" * 40,
                        "cardData": {"license": "apache-2.0"},
                        "siblings": [
                            {"rfilename": "README.md"},
                            {"rfilename": "LICENSE.md"},
                            {
                                "rfilename": "vae/diffusion_pytorch_model.safetensors",
                                "lfs": {"sha256": "d" * 64},
                            },
                        ],
                    }
                ).encode()
            return (b"Changed notice" if changed else b"TEST LICENSE SOURCE")[:count]

    monkeypatch.setattr(
        "scripts.capture_license_sources.urllib.request.urlopen", lambda url, **_kwargs: Response(url)
    )
    capture(tmp_path)
    original = json.loads((tmp_path / "ops/evidence/model-license-sources.json").read_text())
    assert len(original["sources"]) == 9
    assert original["models"][0]["vae_hash_matches_upstream"]
    assert original["models"][0]["upstream_notice_found"]
    saved = tmp_path / original["sources"][0]["path"]
    changed = True
    with pytest.raises(RuntimeError, match="original retained"):
        capture(tmp_path)
    assert saved.read_bytes() == b"TEST LICENSE SOURCE"


def test_capture_refuses_cumulative_budget_before_any_network_call(tmp_path, monkeypatch):
    from scripts.capture_license_sources import capture

    path = tmp_path / "tools/gpu/download-ledger.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"received_bytes": 32_000_000_000, "reservations": {}}))

    def unexpected(*_args, **_kwargs):
        raise AssertionError("Network must not be reached")

    monkeypatch.setattr("scripts.capture_license_sources.urllib.request.urlopen", unexpected)
    with pytest.raises(RuntimeError, match="cumulative"):
        capture(tmp_path)
    assert not (tmp_path / "tools/licenses").exists()
