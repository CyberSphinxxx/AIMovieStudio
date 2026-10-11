from types import SimpleNamespace

import pytest

from studio.vendor_bridge import build_settings, require_success
from studio.providers import WanGPConfig, WanGPProvider


class Session:
    def get_model_availability(self, model):
        return {"available": True, "status": "available"}

    def get_model_schema(self, model):
        return {
            "main_output": ["image", "video"],
            "media_inputs": {"image": {"reference": True}},
            "capabilities": {"image_to_video": True},
        }

    def get_default_settings(self, model):
        return {"model_type": model, "guidance_scale": 4}


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
    session.get_model_schema = lambda _: {"main_output": ["image"], "capabilities": {}}
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
