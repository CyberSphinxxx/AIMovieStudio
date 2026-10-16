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


def test_inventory_covers_the_actual_private_app_runtime_without_imports(tmp_path):
    site = tmp_path / "tools/app-runtime/Lib/site-packages"
    dist = site / "private_dependency-1.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: private-dependency\nVersion: 1.0\nLicense-Expression: MIT\n"
    )
    (dist / "LICENSE").write_text("A private runtime dependency notice.")
    (dist / "RECORD").write_text("private_dependency-1.0.dist-info/LICENSE,,\n")
    (site / "private_dependency.py").write_text("raise RuntimeError('DO NOT IMPORT RUNTIME')")
    python_notice = tmp_path / "tools/app-runtime/LICENSE.txt"
    python_notice.write_text("Private Python runtime notice.")
    report = inventory(tmp_path)
    assert report["counts"]["app-runtime-python"] == 1
    assert any(
        c["name"] == "private-dependency" and c["scope"] == "app-runtime-python" for c in report["components"]
    )
    assert any(item["path"] == "tools/app-runtime/LICENSE.txt" for item in report["standalone_notices"])
    assert report["status"] == "INVENTORY_ONLY_NOT_CLEARED" and not report["native_dependencies_imported"]


def test_installed_experimental_encoder_notices_are_hash_checked_against_lock(tmp_path, monkeypatch):
    import hashlib

    directory = tmp_path / "tools/wan-gp/ckpts/Qwen3/studio-q4-notices"
    directory.mkdir(parents=True)
    license_file = directory / "LICENSE"
    license_file.write_text("Pinned experimental model license.")
    card = directory / "README.md"
    card.write_text("Pinned experimental model card.")
    lock = tmp_path / "ops/evidence/encoder-experiment-lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "notices": [
                    {"file": item.name, "sha256": hashlib.sha256(item.read_bytes()).hexdigest()}
                    for item in [license_file, card]
                ]
            }
        )
    )
    monkeypatch.setattr(
        "scripts.license_inventory.ENCODER_NOTICE_LOCK_SHA", hashlib.sha256(lock.read_bytes()).hexdigest()
    )
    report = inventory(tmp_path)
    captured = [item for item in report["standalone_notices"] if "studio-q4-notices" in item["path"]]
    assert len(captured) == 2
    assert not any("experimental encoder" in f for f in report["findings"])
    license_file.write_text("Changed bytes must not silently count as pinned rights evidence.")
    failed = inventory(tmp_path)
    assert len([item for item in failed["standalone_notices"] if "studio-q4-notices" in item["path"]]) == 1
    assert any("experimental encoder" in f and "changed" in f for f in failed["findings"])


def test_installed_private_runtime_missing_python_notice_is_reported(tmp_path):
    (tmp_path / "tools/app-runtime/Lib/site-packages").mkdir(parents=True)
    report = inventory(tmp_path)
    assert any(
        "tools/app-runtime/LICENSE.txt" in item and "unavailable" in item for item in report["findings"]
    )


def test_uninstalled_experimental_encoder_adds_no_false_missing_notice_finding(tmp_path):
    assert not any("experimental encoder" in item for item in inventory(tmp_path)["findings"])


@pytest.mark.parametrize("contents", [None, "not JSON", '{"notices":[]}'])
def test_present_encoder_without_valid_pinned_notice_lock_cannot_clear_findings(tmp_path, contents):
    directory = tmp_path / "tools/wan-gp/ckpts/Qwen3"
    directory.mkdir(parents=True)
    (directory / "Qwen3-4B-Q4_K_M.gguf").write_bytes(b"size-only fixture, never model loading")
    if contents is not None:
        lock = tmp_path / "ops/evidence/encoder-experiment-lock.json"
        lock.parent.mkdir(parents=True)
        lock.write_text(contents)
    report = inventory(tmp_path)
    assert any("experimental encoder" in item and "lock" in item for item in report["findings"])
    assert not any("studio-q4-notices" in item["path"] for item in report["standalone_notices"])


def test_license_cli_keeps_each_report_and_does_not_replace_historical_evidence(tmp_path, monkeypatch):
    from scripts import license_inventory

    output = tmp_path / "ops/evidence"
    output.mkdir(parents=True)
    historical = output / "installed-license-inventory.json"
    historical.write_bytes(b"preserve historical exact evidence")
    monkeypatch.setattr(license_inventory, "ROOT", tmp_path)
    license_inventory.main()
    license_inventory.main()
    assert historical.read_bytes() == b"preserve historical exact evidence"
    assert len(list(output.glob("installed-license-inventory-*.json"))) == 2


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
