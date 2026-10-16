"""Explicit byte-sized installer fixtures; never download real model files."""

import hashlib
import json
import sys

import pytest

from scripts import setup_gpu as installer
from studio.storage import atomic_json, digest
from tests.test_gpu_downloads import downloads as _downloads_fixture, response

downloads = _downloads_fixture


def item(name, content=b"safe", *, sha=True):
    return {
        "repo": "DeepBeepMeep/Flux2",
        "file": name,
        "url": f"https://fixture.invalid/{name}",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest() if sha else None,
    }


def save_proposal(items):
    proposal = {"files": items}
    atomic_json(installer.ROOT / "ops/evidence/gpu-download-proposal.json", proposal)
    return proposal


def test_invalid_later_file_never_spends_an_earlier_download(downloads, monkeypatch):
    save_proposal([item("one.bin"), item("two.bin", sha=False)])
    requests = response(monkeypatch, b"safe")
    monkeypatch.setattr(sys, "argv", ["setup_gpu", "image", "--approved"])
    before = installer.ledger()
    with pytest.raises((ValueError, RuntimeError)):
        installer.main()
    assert not requests and installer.ledger() == before


def test_whole_phase_budget_failure_never_spends_an_earlier_download(downloads, monkeypatch):
    save_proposal([item("one.bin"), item("two.bin", b"second")])
    installer.reserve("existing-runtime", 95)
    requests = response(monkeypatch, b"safe")
    monkeypatch.setattr(sys, "argv", ["setup_gpu", "image", "--approved"])
    before = installer.ledger()
    with pytest.raises(RuntimeError, match="budget|BUDGET"):
        installer.main()
    assert not requests and installer.ledger() == before


def test_historical_small_file_hash_uses_only_a_matching_verified_receipt(downloads, monkeypatch):
    row = item("tokenizer.json", sha=False)
    path = installer.ROOT / "tools/wan-gp/ckpts/tokenizer.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"safe")
    state = installer.ledger()
    state["completed"][str(path.relative_to(installer.ROOT))] = {
        "bytes": 4,
        "url": row["url"],
        "sha256": digest(path),
    }
    installer.save(state)
    before = installer.ledger()
    plan = installer.phase_plan(save_proposal([row]), "image")
    assert plan["remaining_download_bytes"] == 0
    assert plan["files"][0]["sha256"] == digest(path)
    assert installer.ledger() == before
    # A changed receipt URL must never authorize a different source.
    state["completed"][str(path.relative_to(installer.ROOT))]["url"] = "https://fixture.invalid/other"
    installer.save(state)
    with pytest.raises(ValueError, match="MISSING_CHECKSUM"):
        installer.phase_plan({"files": [row]}, "image")


@pytest.mark.parametrize("filename", ["../../escape.bin", "C:/outside.bin", "folder\\outside.bin"])
def test_paths_are_checked_before_any_download(downloads, filename):
    with pytest.raises(ValueError, match="UNSAFE_PATH"):
        installer.phase_plan(save_proposal([item(filename)]), "image")


def test_completed_corrupt_partial_and_duplicate_destinations_are_rejected(downloads):
    row = item("safe.bin")
    destination = installer.ROOT / "tools/wan-gp/ckpts/safe.bin"
    destination.parent.mkdir(parents=True)
    partial = destination.with_name(destination.name + ".partial")
    partial.write_bytes(b"evil")
    with pytest.raises(RuntimeError, match="CHECKSUM_REQUIRED"):
        installer.phase_plan(save_proposal([row]), "image")
    partial.write_bytes(b"sa")
    with pytest.raises(ValueError, match="UNSAFE_PATH"):
        installer.phase_plan(save_proposal([row, row]), "image")


def test_inspection_needs_no_approval_and_does_not_fetch_or_mutate_ledger(downloads, monkeypatch, capsys):
    save_proposal([item("safe.bin")])
    requests = response(monkeypatch, b"safe")
    monkeypatch.setattr(sys, "argv", ["setup_gpu", "image", "--inspect"])
    before = installer.ledger()
    installer.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "OFFLINE_PHASE_PLAN_NOT_INFERENCE" and result["remaining_download_bytes"] == 4
    assert not requests and before == installer.ledger()
    assert not (installer.ROOT / "tools/wan-gp").exists()


def test_video_download_gate_stays_authoritative_even_with_valid_phase_plan(downloads, monkeypatch):
    row = item("video.bin") | {"repo": "DeepBeepMeep/Wan2.2"}
    save_proposal([row])
    requests = response(monkeypatch, b"safe")
    monkeypatch.setattr(sys, "argv", ["setup_gpu", "video", "--approved"])
    with pytest.raises(RuntimeError, match="passing image gate"):
        installer.main()
    assert not requests and installer.ledger()["received_bytes"] == 0
