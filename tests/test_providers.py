from types import SimpleNamespace

import pytest

from studio.vendor_bridge import build_settings, require_success, run_session
from studio.providers import WanGPConfig, WanGPProvider


class Session:
    def get_model_availability(self, model):
        return {"available": True, "status": "available"}

    def get_model_schema(self, model):
        return {
            "metadata": {
                "main_output": ["image", "video"],
                "media_inputs": {"image": {"reference": True}},
                "capabilities": {"image_to_video": True},
            },
        }

    def get_default_settings(self, model):
        return {"model_type": model, "guidance_scale": 4}


def test_bridge_subscribes_to_documented_callbacks_and_saves_actual_phases(tmp_path, monkeypatch):
    import json
    import sys

    from studio.vendor_telemetry import Sampler

    # Explicit contract fixture: no vendor runtime or native generation executed.
    sampler = Sampler(tmp_path / "telemetry.json")
    received = []

    def init(**kwargs):
        received.append(kwargs)
        kwargs["callbacks"].on_progress(SimpleNamespace(phase="loading_model"))
        return SimpleNamespace(list_model_metadata=lambda **kw: [{"model_type": "fixture"}])

    monkeypatch.setitem(sys.modules, "shared", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "shared.api", SimpleNamespace(init=init))
    response = tmp_path / "result.json"
    run_session({"kind": "discover", "memory_profile": 5}, tmp_path, tmp_path, response, sampler)
    assert received[0]["callbacks"] is sampler and received[0]["console_output"] is False
    assert "--no-prevent-power-throttling" in received[0]["cli_args"]
    result = json.loads(response.read_text())
    assert result["models"] == [{"model_type": "fixture"}]
    assert result["runtime_options"]["smart_memory_pinning"] is True
    assert json.loads(sampler.path.read_text())["phase"] == "response_saved"


def test_explicit_transfer_override_is_passed_to_documented_session_config(tmp_path, monkeypatch):
    import json
    import sys

    from studio.vendor_telemetry import Sampler

    root, output = tmp_path / "engine", tmp_path / "output"
    root.mkdir()
    output.mkdir()
    source = root / "wgp_config.json"
    source.write_text('{"text_encoder_quantization":"int8","deepy_key":"fixture-secret"}')
    original = source.read_bytes()
    received = []

    def init(**kwargs):
        received.append(kwargs)
        return SimpleNamespace(list_model_metadata=lambda **kw: [])

    monkeypatch.setitem(sys.modules, "shared", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "shared.api", SimpleNamespace(init=init))
    run_session(
        {"kind": "discover", "smart_memory_pinning": False},
        root,
        output,
        output / "result.json",
        Sampler(output / "telemetry.json"),
    )
    config = received[0]["config_path"]
    assert config.name == "wgp_config.json" and config.is_relative_to(output)
    assert json.loads(config.read_text())["smart_memory_pinning"] is False
    assert "fixture-secret" not in config.read_text() and source.read_bytes() == original
    record = json.loads((output / "result.json").read_text())["runtime_options"]
    assert record["override"] and record["smart_memory_pinning"] is False


def test_documented_wangp_settings_preserve_defaults_and_references():
    request = {
        "model": "installed-model",
        "prompt": "A cinematic shot",
        "resolution": "480x832",
        "seed": 42,
        "steps": 12,
        "kind": "image",
        "references": ["scoped.png"],
    }
    settings, schema = build_settings(Session(), request)
    assert settings["image_refs"] == ["scoped.png"] and settings["image_mode"] == 1
    assert settings["guidance_scale"] == 4
    request.update(kind="video", start_image="frame.png", seconds=5)
    settings, _ = build_settings(Session(), request)
    assert (
        settings["image_start"] == "frame.png"
        and settings["video_length"] == "5s"
        and settings["force_fps"] == 24
    )


def test_missing_weights_never_submit():
    session = Session()
    session.get_model_availability = lambda _: {"status": "partial", "available": False}
    with pytest.raises(RuntimeError, match="MISSING_MODEL"):
        build_settings(session, {"model": "missing"})


def test_unsupported_reference_conditioning_blocks():
    session = Session()
    session.get_model_schema = lambda _: {"metadata": {"main_output": ["image"], "capabilities": {}}}
    with pytest.raises(RuntimeError, match="identity reference"):
        build_settings(
            session,
            {
                "model": "x",
                "kind": "image",
                "prompt": "x",
                "resolution": "480x832",
                "seed": 1,
                "steps": 12,
                "references": ["ref.png"],
            },
        )


def test_vendor_failure_not_mistaken_for_success(tmp_path):
    with pytest.raises(RuntimeError, match="OUT_OF_MEMORY"):
        require_success(
            SimpleNamespace(success=False, errors=[SimpleNamespace(message="CUDA out of memory")]), tmp_path
        )
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"not media")
    with pytest.raises(RuntimeError, match="scoped"):
        require_success(SimpleNamespace(success=True, generated_files=[str(outside)]), tmp_path)


def test_flat_mock_schema_cannot_mask_pinned_native_metadata_contract():
    session = Session()
    session.get_model_schema = lambda _: {"main_output": ["image"]}
    with pytest.raises(RuntimeError, match="no metadata object"):
        build_settings(session, {"model": "x", "kind": "image"})


def test_windows_policy_block_has_actionable_error_without_retry_or_fallback(tmp_path, monkeypatch):
    calls = []
    provider = WanGPProvider(WanGPConfig(license_reviewed=True), tmp_path)
    monkeypatch.setattr(provider, "configured", lambda: True)

    def blocked(*args, **kwargs):
        calls.append(args)
        raise RuntimeError(
            "MEDIA_FAILED: [WinError 4551] An Application Control policy has blocked this file."
        )

    monkeypatch.setattr("studio.providers.media.run", blocked)
    with pytest.raises(RuntimeError, match="OS_POLICY_BLOCKED") as caught:
        provider.request("discover", "", tmp_path, lambda: None)
    assert len(calls) == 1
    assert "4551" in str(caught.value.__cause__)
    assert not (tmp_path / "provider-result.json").exists()


@pytest.mark.parametrize("value", [1, 3, 6, "unsafe"])
def test_memory_profile_only_admits_documented_low_vram_options(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WanGPConfig(memory_profile=value)


def test_existing_provider_configuration_keeps_profile_four_unless_explicitly_changed():
    assert WanGPConfig().memory_profile == 4
    assert WanGPConfig(memory_profile=5).memory_profile == 5


def test_real_generation_ram_guard_keeps_checkpoint_and_never_falls_back(tmp_path, monkeypatch):
    calls = []
    provider = WanGPProvider(WanGPConfig(license_reviewed=True, memory_profile=5), tmp_path)
    monkeypatch.setattr(provider, "configured", lambda: True)
    monkeypatch.setattr("studio.providers.require_resources", lambda: None)
    monkeypatch.setattr("studio.diagnostics.memory_status", lambda: {"available": True, "free_gb": 1.99})
    monkeypatch.setattr("studio.providers.media.run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="RESOURCE_BUSY.*Saved checkpoints"):
        provider.request("image", "sample", tmp_path, lambda: None)
    assert not calls and (tmp_path / "provider-request.json").exists()
    assert not (tmp_path / "provider-result.json").exists()
