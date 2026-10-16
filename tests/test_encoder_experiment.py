"""Tiny explicit setup fixtures and pinned-source contracts; no model inference."""

import hashlib
import json
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import encoder_experiment as experiment
from scripts import setup_gpu as gpu
from studio.inference_lock import InferenceBusy, native_inference
from studio.storage import atomic_json, digest

REAL_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    engine = tmp_path / "tools/wan-gp"
    engine.mkdir(parents=True)
    (engine / ".studio-revision").write_text(experiment.ENGINE_REVISION)
    config = engine / "ckpts/Qwen3/config.json"
    atomic_json(config, {"model_type": "qwen3", "hidden_size": 2560, "num_hidden_layers": 36})
    model = engine / "ckpts/flux.bin"
    model.write_bytes(b"EXPLICIT TEST FIXTURE, NOT MODEL WEIGHTS")
    source = engine / "wgp.py"
    source.write_bytes(b"# Pinned contract fixture, never imported")
    notice = tmp_path / "ops/evidence/encoder-candidate-notices/LICENSE"
    notice.parent.mkdir(parents=True)
    notice.write_bytes(b"Explicit development-only license fixture")

    def row(path, base):
        return {
            "file": path.relative_to(base).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }

    lock = {
        "source_files": [row(source, engine)],
        "reuse": [row(model, engine), row(config, engine)],
        "notices": [row(notice, notice.parent)],
    }
    lock_path = tmp_path / "ops/evidence/encoder-experiment-lock.json"
    atomic_json(lock_path, lock)
    monkeypatch.setattr(experiment, "LOCK_SHA", digest(lock_path))
    monkeypatch.setattr(experiment, "SIZE", 10)
    monkeypatch.setattr(experiment, "SHA", hashlib.sha256(b"0123456789").hexdigest())
    monkeypatch.setattr(experiment, "ALLOWANCE", 20)
    monkeypatch.setattr(experiment, "RESEARCH_BYTES", 2)
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    monkeypatch.setattr(gpu, "ROOT", tmp_path)
    monkeypatch.setattr(gpu, "TARGET", tmp_path / "tools/gpu")
    monkeypatch.setattr(gpu, "LIMIT", 100)
    monkeypatch.setattr(gpu, "MIN_FREE", 10)
    monkeypatch.setattr(gpu, "RESERVE", 10)
    monkeypatch.setattr(gpu.shutil, "disk_usage", lambda _: SimpleNamespace(free=2_000_000))
    monkeypatch.setattr(
        gpu.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Unexpected network request")
    )
    state = gpu.ledger()
    state["received_bytes"] = 2
    state["license_source_captures"] = {"encoder-candidate-research": {"received_bytes": 2}}
    gpu.save(state)
    return tmp_path, engine


def candidate(engine):
    return engine / f"ckpts/Qwen3/{experiment.FILENAME}"


def profile(engine):
    return engine / f"finetunes/{experiment.PROFILE}.json"


def fake_fetch(monkeypatch, action=None):
    calls = []

    def fetch(url, path, size, sha, reservation):
        calls.append((url, path, size, sha, reservation))
        state = gpu.ledger()
        state["received_bytes"] += 10
        state["reservations"][reservation] -= 10
        gpu.save(state)
        if action:
            action(path)
        else:
            path.write_bytes(b"0123456789")

    monkeypatch.setattr(gpu, "fetch", fetch)
    return calls


def test_offline_inspection_and_install_approval_have_no_setup_side_effects(prepared):
    root, engine = prepared
    state = gpu.ledger()
    report = experiment.inspect(root)
    assert report["status"] == "PREPARED_NOT_INSTALLED_NOT_INFERENCE"
    assert report["accounted_gpu_bytes_including_new_reservation"] == 20
    assert report["hardware_fit"] == "NOT_TESTED" and not report["settings_changed"]
    assert not candidate(engine).exists() and not profile(engine).exists()
    with pytest.raises(RuntimeError, match="APPROVAL_REQUIRED"):
        experiment.install(root)
    assert gpu.ledger() == state


@pytest.mark.parametrize("which", ["source", "tokenizer", "notice", "manifest", "revision"])
def test_changed_pinned_inputs_fail_before_download_or_reservation(prepared, monkeypatch, which):
    root, engine = prepared
    paths = {
        "source": engine / "wgp.py",
        "tokenizer": engine / "ckpts/Qwen3/config.json",
        "notice": root / "ops/evidence/encoder-candidate-notices/LICENSE",
        "manifest": root / "ops/evidence/encoder-experiment-lock.json",
        "revision": engine / ".studio-revision",
    }
    paths[which].write_bytes(b"Changed input")
    before = gpu.ledger()
    calls = fake_fetch(monkeypatch)
    with pytest.raises(RuntimeError, match="CHECKSUM_REQUIRED|INCOMPATIBLE"):
        experiment.install(root, approved=True)
    assert not calls and gpu.ledger() == before and not profile(engine).exists()


def test_missing_or_invalid_candidate_never_publishes_profile(prepared, monkeypatch):
    root, engine = prepared
    calls = fake_fetch(monkeypatch, lambda path: path.write_bytes(b"corruption"))
    with pytest.raises(RuntimeError, match="CHECKSUM_REQUIRED"):
        experiment.install(root, approved=True)
    assert len(calls) == 1 and not profile(engine).exists()
    assert candidate(engine).read_bytes() == b"corruption"  # Preserve failed original.
    with pytest.raises(RuntimeError, match="CHECKSUM_REQUIRED"):
        experiment.install(root, approved=True)
    assert len(calls) == 1


def test_complete_setup_is_immutable_idempotent_and_offline(prepared, monkeypatch):
    root, engine = prepared
    config = engine / "wgp_config.json"
    config.write_bytes(b'{"existing-setting":"keep"}')
    calls = fake_fetch(monkeypatch)
    result = experiment.install(root, approved=True)
    assert result["status"] == "INSTALLED_NOT_INFERENCE"
    assert len(calls) == 1 and calls[0][0] == experiment.URL
    assert calls[0][-1] == experiment.RESERVATION
    assert json.loads(profile(engine).read_text())["model"]["text_encoder_URLs"] == [
        str(candidate(engine).resolve())
    ]
    assert config.read_bytes() == b'{"existing-setting":"keep"}'
    assert not (engine / "defaults").exists()
    before = {p: p.read_bytes() for p in engine.rglob("*") if p.is_file()}
    state = gpu.ledger()
    assert experiment.verify_installed(root)["encoder"]["installed"]
    experiment.install(root, approved=True)
    assert len(calls) == 1 and gpu.ledger() == state
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize("which", ["profile", "receipt", "notice"])
def test_conflicting_published_file_is_preserved_before_fetch(prepared, monkeypatch, which):
    root, engine = prepared
    paths = {
        "profile": profile(engine),
        "receipt": root / "tools/gpu/encoder-experiment-receipt.json",
        "notice": engine / "ckpts/Qwen3/studio-q4-notices/LICENSE",
    }
    path = paths[which]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"Preserve this original")
    calls = fake_fetch(monkeypatch)
    before = gpu.ledger()
    with pytest.raises(RuntimeError, match="EXISTING_FILE"):
        experiment.install(root, approved=True)
    assert path.read_bytes() == b"Preserve this original" and not calls and gpu.ledger() == before


def test_interrupted_publication_resumes_verified_download_without_new_allowance(prepared, monkeypatch):
    root, engine = prepared
    calls = fake_fetch(monkeypatch)
    publish = experiment.publish

    def interrupted(path, content):
        if path == profile(engine):
            raise OSError("Explicit interruption fixture")
        publish(path, content)

    monkeypatch.setattr(experiment, "publish", interrupted)
    with pytest.raises(OSError, match="interruption"):
        experiment.install(root, approved=True)
    assert candidate(engine).is_file() and not profile(engine).exists()
    state = gpu.ledger()
    monkeypatch.setattr(experiment, "publish", publish)
    experiment.install(root, approved=True)
    assert len(calls) == 1 and gpu.ledger() == state
    assert experiment.verify_installed(root)["hardware_fit"] == "NOT_TESTED"


def test_native_owner_blocks_setup_before_any_download(prepared, monkeypatch):
    root, engine = prepared
    calls = fake_fetch(monkeypatch)
    before = gpu.ledger()
    with native_inference():
        with pytest.raises(InferenceBusy):
            experiment.install(root, approved=True)
    assert not calls and before == gpu.ledger() and not profile(engine).exists()


@pytest.mark.parametrize("failure", ["ceiling", "allowance", "disk", "unknown", "unrecorded", "oversized"])
def test_resource_and_accounting_failures_block_without_mutation(prepared, monkeypatch, failure):
    root, engine = prepared
    state = gpu.ledger()
    if failure == "ceiling":
        state["reservations"]["keep-runtime-allocation"] = 90
    elif failure == "allowance":
        state["reservations"][experiment.RESERVATION] = 3
    elif failure == "disk":
        monkeypatch.setattr(experiment.shutil, "disk_usage", lambda _: SimpleNamespace(free=9))
    elif failure == "unknown":
        state["received_bytes"] = True
    elif failure == "unrecorded":
        state.pop("license_source_captures")
    elif failure == "oversized":
        candidate(engine).with_suffix(".gguf.partial").write_bytes(b"X" * 11)
    gpu.save(state)
    calls = fake_fetch(monkeypatch)
    with pytest.raises(RuntimeError, match="BUDGET_|DISK_|INVALID_LEDGER|BAD_PARTIAL"):
        experiment.install(root, approved=True)
    assert gpu.ledger() == state and not calls and not profile(engine).exists()


def test_unfinished_receipt_and_escaped_path_are_rejected(prepared):
    root, engine = prepared
    with pytest.raises(RuntimeError, match="MISSING_MODEL"):
        experiment.verify_installed(root)
    with pytest.raises(RuntimeError, match="UNSAFE_PATH"):
        experiment.scoped(engine, "../../outside")


def test_source_manifest_preserves_real_pinned_hashes_and_notices():
    # Read only: optional vendor tree absent on CI is not required for these contracts.
    lock_path = REAL_ROOT / "ops/evidence/encoder-experiment-lock.json"
    assert digest(lock_path) == experiment.LOCK_SHA
    lock = json.loads(lock_path.read_bytes())
    assert len(lock["reuse"]) == 11 and len(lock["source_files"]) == 8
    for item in lock["notices"]:
        experiment.verify(
            REAL_ROOT / "ops/evidence/encoder-candidate-notices" / item["file"], item["bytes"], item["sha256"]
        )


def test_definition_uses_local_encoder_only_and_reuses_original_base(tmp_path):
    definition = experiment.definition(tmp_path)["model"]
    assert definition["URLs"] == "flux2_klein_4b"
    assert definition["text_encoder_URLs"] == [
        str((tmp_path / f"ckpts/Qwen3/{experiment.FILENAME}").resolve())
    ]
    assert definition["architecture"] == "flux2_klein_4b"


def test_real_bounded_fetch_resumes_and_charges_failed_bytes_once(prepared, monkeypatch):
    root, engine = prepared
    requests = []

    def open_url(request, **kwargs):
        requests.append(request)
        resumed = len(requests) == 2
        stream = io.BytesIO(b"456789" if resumed else b"0123")
        stream.status = 206 if resumed else 200
        stream.headers = {"Content-Range": "bytes 4-9/10"} if resumed else {}
        return stream

    monkeypatch.setattr(gpu.urllib.request, "urlopen", open_url)
    with pytest.raises(RuntimeError, match="length differs"):
        experiment.install(root, approved=True)
    assert not profile(engine).exists()
    assert gpu.ledger()["received_bytes"] == 6
    assert gpu.ledger()["reservations"][experiment.RESERVATION] == 14
    experiment.install(root, approved=True)
    assert requests[1].headers["Range"] == "bytes=4-"
    assert all(request.full_url == experiment.URL for request in requests)
    assert gpu.ledger()["received_bytes"] == 12
    assert gpu.ledger()["reservations"][experiment.RESERVATION] == 8
    assert experiment.verify_installed(root)["encoder"]["installed"]


def test_competing_installer_cannot_mutate_or_spend_ledger(prepared, monkeypatch):
    root, engine = prepared
    before = gpu.ledger()
    with gpu.download_ownership():
        with pytest.raises(RuntimeError, match="SETUP_BUSY"):
            gpu.reserve("competing-allocation", 4)
        with pytest.raises(RuntimeError, match="SETUP_BUSY"):
            gpu.fetch(experiment.URL, candidate(engine), 10, experiment.SHA)
    assert before == gpu.ledger() and not candidate(engine).exists()


def test_publication_collision_never_deletes_an_existing_temporary(prepared, monkeypatch):
    root, engine = prepared
    monkeypatch.setattr(experiment, "uuid4", lambda: SimpleNamespace(hex="explicit-collision"))
    path = engine / "finetunes/example.json"
    temporary = path.with_name(f".{path.name}.explicit-collision.partial")
    temporary.parent.mkdir()
    temporary.write_bytes(b"Preserve an existing interrupted operation")
    with pytest.raises(FileExistsError):
        experiment.publish(path, b"complete replacement")
    assert not path.exists() and temporary.read_bytes() == b"Preserve an existing interrupted operation"
