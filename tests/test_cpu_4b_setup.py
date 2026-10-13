import json

import pytest

from scripts import setup_cpu_4b_story as setup


def test_four_b_download_requires_new_approval_before_filesystem_or_network(monkeypatch):
    monkeypatch.setattr(setup, "fetch", lambda *_args: pytest.fail("Downloaded before approval"))
    with pytest.raises(SystemExit) as error:
        setup.main([])
    assert error.value.code == 2


@pytest.mark.parametrize("fault", ["missing_runtime", "bad_path", "network_cap", "disk_cap"])
def test_reviewed_4b_scope_rejects_invalid_runtime_paths_and_budgets(tmp_path, monkeypatch, fault):
    target = tmp_path / "tools/story"
    target.mkdir(parents=True)
    if fault != "missing_runtime":
        (target / "llama-server.exe").write_bytes(b"not-an-executable-test-fixture")
    path = tmp_path / "ops/evidence/cpu-4b-story-download-proposal.json"
    path.parent.mkdir(parents=True)
    value = {
        "files": [
            {"target": "model.gguf", "bytes": 100, "sha256": "0" * 64, "url": "https://example.invalid"}
        ],
        "preapproval_metadata_received_bytes": 1,
        "network_cap_bytes": 200,
        "disk_cap_bytes": 200,
    }
    if fault == "bad_path":
        value["files"][0]["target"] = "../outside"
    if fault == "network_cap":
        value["network_cap_bytes"] = 99
    if fault == "disk_cap":
        value["disk_cap_bytes"] = 99
    path.write_text(json.dumps(value))
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup, "fetch", lambda *_args: pytest.fail("Downloaded invalid proposal"))
    with pytest.raises((ValueError, RuntimeError)):
        setup.main(["--approved"])
