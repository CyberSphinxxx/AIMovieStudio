"""Configuration contract fixtures, never native inference or memory-fit proof."""

import json

import pytest

from studio.vendor_config import session_config


@pytest.mark.parametrize("option", [True, False])
def test_scoped_override_preserves_source_and_omits_secrets(tmp_path, option):
    root, output = tmp_path / "engine", tmp_path / "output"
    root.mkdir()
    source = root / "wgp_config.json"
    source.write_text(
        json.dumps(
            {
                "checkpoints_paths": ["ckpts", "."],
                "text_encoder_quantization": "int8",
                "deepy_api_key": "fixture-secret",
                "deepy_providers": {"token": "fixture-secret"},
                "smart_memory_pinning": True,
            }
        )
    )
    original = source.read_bytes()
    path, record = session_config(root, output, option)
    assert path.name == "wgp_config.json" and path.is_relative_to(output)
    data = json.loads(path.read_text())
    assert data["smart_memory_pinning"] is option
    assert data["text_encoder_quantization"] == "int8" and data["checkpoints_paths"] == ["ckpts", "."]
    assert "fixture-secret" not in path.read_text()
    assert data["deepy_enabled"] == 0 and data["enhancer_enabled"] == 0
    assert source.read_bytes() == original
    assert record["override"] and record["smart_memory_pinning"] is option
    assert len(record["config_input_sha256"]) == 64


def test_legacy_request_preserves_vendor_defaults_without_writing(tmp_path):
    root = tmp_path / "engine"
    root.mkdir()
    source = root / "wgp_config.json"
    source.write_text('{"smart_memory_pinning":false}')
    before = source.read_bytes()
    path, record = session_config(root, tmp_path / "output", None)
    assert path is None and record["smart_memory_pinning"] is False and not record["override"]
    assert source.read_bytes() == before and not (tmp_path / "output").exists()


@pytest.mark.parametrize("value", [[], {"smart_memory_pinning": "false"}])
def test_invalid_configuration_is_rejected_without_overwrite(tmp_path, value):
    source = tmp_path / "wgp_config.json"
    source.write_text(json.dumps(value))
    before = source.read_bytes()
    with pytest.raises(RuntimeError, match="INCOMPATIBLE"):
        session_config(tmp_path, tmp_path / "output", False)
    assert source.read_bytes() == before and not (tmp_path / "output").exists()


def test_large_configuration_is_rejected_before_json_read(tmp_path):
    (tmp_path / "wgp_config.json").write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(RuntimeError, match="too large"):
        session_config(tmp_path, tmp_path / "output", False)


def test_invalid_json_does_not_create_scoped_output(tmp_path):
    (tmp_path / "wgp_config.json").write_bytes(b"not-json")
    with pytest.raises(RuntimeError, match="INCOMPATIBLE.*invalid JSON"):
        session_config(tmp_path, tmp_path / "output", False)
    assert not (tmp_path / "output").exists()


def test_optional_transfer_choice_roundtrips_and_freezes_in_queued_job(tmp_path, spec):
    from fastapi.testclient import TestClient
    from studio.api import create_app
    from studio.providers import WanGPConfig

    assert WanGPConfig().smart_memory_pinning is None
    with TestClient(create_app(tmp_path / "app", run_worker=False)) as client:
        saved = client.patch("/api/settings", json={"wangp": {"smart_memory_pinning": False}})
        assert saved.status_code == 200 and saved.json()["wangp"]["smart_memory_pinning"] is False
        created = client.post("/api/projects", json=spec.model_dump()).json()
        assert json.loads(created["jobs"][0]["config"])["wangp"]["smart_memory_pinning"] is False
        client.patch("/api/settings", json={"wangp": {"smart_memory_pinning": None}})
        persisted = client.get(f"/api/projects/{created['id']}").json()
        assert json.loads(persisted["jobs"][0]["config"])["wangp"]["smart_memory_pinning"] is False
