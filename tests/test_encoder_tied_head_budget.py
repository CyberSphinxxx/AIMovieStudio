"""New test scope cannot refund or overwrite the original failed attempt."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.encoder_experiment import ROOT, claim_tied_head_test


@pytest.fixture
def original(tmp_path):
    directory = tmp_path / "tools/gpu"
    directory.mkdir(parents=True)
    path = directory / "encoder-image-test-reservation.json"
    path.write_bytes(b'{"run_id":"original-spent-attempt","max_seconds":300}')
    return tmp_path, path


def test_missing_new_approval_never_claims(original):
    root, path = original
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="APPROVAL_REQUIRED"):
        claim_tied_head_test(root, "new", 300)
    assert path.read_bytes() == before
    assert not (path.parent / "encoder-tied-head-test-reservation.json").exists()


@pytest.mark.parametrize("seconds", [0, 301, True, 1.0])
def test_new_scope_time_ceiling_is_strict(original, seconds):
    root, path = original
    with pytest.raises(ValueError):
        claim_tied_head_test(root, "new", seconds, approved=True)
    assert not (path.parent / "encoder-tied-head-test-reservation.json").exists()


def test_new_reservation_survives_reopen_and_original_is_never_refunded(original):
    root, path = original
    before = path.read_bytes()
    claim_tied_head_test(root, "new", 300, approved=True)
    new = path.parent / "encoder-tied-head-test-reservation.json"
    saved = new.read_bytes()
    assert json.loads(saved)["compatibility"] == "qwen3_tied_head_v1"
    assert path.read_bytes() == before
    with pytest.raises(RuntimeError, match="EXPERIMENT_SPENT"):
        claim_tied_head_test(root, "retry", 300, approved=True)
    assert new.read_bytes() == saved and path.read_bytes() == before


def test_new_attempt_cannot_precede_original_result(tmp_path):
    with pytest.raises(RuntimeError, match="original image attempt"):
        claim_tied_head_test(tmp_path, "new", 300, approved=True)


def test_concurrent_claims_spend_only_one_new_attempt(original):
    root, path = original

    def claim(index):
        try:
            claim_tied_head_test(root, str(index), 300, approved=True)
            return "claimed"
        except RuntimeError as error:
            assert "EXPERIMENT_SPENT" in str(error)
            return "spent"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == ["claimed", "spent"]
    assert path.exists()


def test_cli_without_new_approval_refuses_before_setup_or_model_import():
    result = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "scripts.gpu_smoke",
            "image",
            "--encoder-experiment",
            "--tied-head-retest",
            "--max-seconds",
            "300",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2 and "explicit new approval" in result.stderr


def prepare_smoke(monkeypatch, root):
    from scripts import gpu_smoke

    monkeypatch.setattr(gpu_smoke, "ROOT", root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gpu_smoke",
            "image",
            "--encoder-experiment",
            "--tied-head-retest",
            "--approved-tied-head-retest",
            "--max-seconds",
            "300",
        ],
    )
    return gpu_smoke


def test_busy_real_owner_does_not_spend_new_attempt_or_check_models(original, monkeypatch):
    from studio import inference_lock
    from tests.test_inference_lock import owner_process

    root, path = original
    common = root / "shared-native.lock"
    monkeypatch.setattr(inference_lock, "lock_path", lambda: common)
    smoke = prepare_smoke(monkeypatch, root)
    monkeypatch.setattr(
        smoke, "require_resources", lambda: pytest.fail("Busy owner reached resource/model checks")
    )
    with owner_process(root, common):
        with pytest.raises(inference_lock.InferenceBusy):
            smoke.main()
    assert not (path.parent / "encoder-tied-head-test-reservation.json").exists()


def test_low_resources_do_not_spend_new_attempt(original, monkeypatch):
    root, path = original
    smoke = prepare_smoke(monkeypatch, root)

    def blocked():
        raise RuntimeError("RESOURCE_BUSY: explicit counter fixture")

    monkeypatch.setattr(smoke, "require_resources", blocked)
    monkeypatch.setattr(
        smoke, "verify_installed", lambda *_: pytest.fail("Unsafe resources reached model checks")
    )
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY"):
        smoke.main()
    assert not (path.parent / "encoder-tied-head-test-reservation.json").exists()


def test_retest_harness_keeps_original_reports_and_spends_only_new_scope(original, monkeypatch):
    from studio.storage import atomic_json

    root, path = original
    before = path.read_bytes()
    old_status = path.parent / "encoder-image-status.json"
    atomic_json(old_status, {"code": "FAILED", "original": True})
    old_bytes = old_status.read_bytes()
    smoke = prepare_smoke(monkeypatch, root)
    monkeypatch.setattr(smoke, "require_resources", lambda: {"explicit_counter_fixture": True})
    monkeypatch.setattr(smoke, "verify_installed", lambda *_: {"explicit_file_fixture": True})
    seen = []

    def stop(provider, *_args, **_kwargs):
        seen.append(provider.encoder_compatibility)
        raise RuntimeError("explicit no-inference fixture failure")

    monkeypatch.setattr(smoke.WanGPProvider, "image", stop)
    with pytest.raises(RuntimeError, match="fixture failure"):
        smoke.main()
    assert seen == ["qwen3_tied_head_v1"]
    assert path.read_bytes() == before and old_status.read_bytes() == old_bytes
    report = next((root / "ops/evidence").glob("encoder-tied-head-image-*.json"))
    assert json.loads(report.read_bytes())["status"] == "FAILED"
    assert json.loads((path.parent / "encoder-tied-head-status.json").read_bytes())["code"] == "FAILED"
    with pytest.raises(RuntimeError, match="EXPERIMENT_SPENT"):
        smoke.main()
    assert seen == ["qwen3_tied_head_v1"] and path.read_bytes() == before
