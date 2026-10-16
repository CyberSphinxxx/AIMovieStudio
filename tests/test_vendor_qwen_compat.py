"""Tiny object/configuration contracts, never native model loading."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from studio import vendor_qwen_compat as compat
from studio.vendor_bridge import encoder_compatibility_context, run_session
from studio.providers import WanGPConfig, WanGPProvider

CONFIG = {"model_type": "qwen3", "tie_word_embeddings": True, "vocab_size": 151936, "hidden_size": 2560}


def identity(state, quant, tied):
    return state, quant, tied


def test_missing_head_uses_same_packed_object_through_loader_tie_map():
    embedding = SimpleNamespace(tensor_shape=(151936, 2560))
    state = {compat.EMBEDDING: embedding, "unrelated.weight": object()}
    quant = {"model.embed_tokens": {"weights": "gguf", "activations": "none"}}
    tied = {compat.EMBEDDING: ["other_alias"]}
    applied = []
    mapped, returned_quant, returned_tied = compat.tied_head_preprocessor(identity, CONFIG, applied)(
        state, quant, tied
    )
    assert mapped is state and returned_quant is quant
    assert tied == {compat.EMBEDDING: ["other_alias"]}
    assert compat.HEAD not in state  # Loader, rather than helper, applies aliases.
    for key, aliases in returned_tied.items():
        for alias in aliases:
            mapped[alias] = mapped[key]
    assert mapped[compat.HEAD] is embedding and mapped["other_alias"] is embedding
    assert len(applied) == 1
    assert "unrelated.weight" in mapped


def test_explicit_output_head_is_preserved_without_guessing_or_tying():
    state = {compat.EMBEDDING: object(), compat.HEAD: object()}
    applied = []
    result = compat.tied_head_preprocessor(identity, CONFIG, applied)(state)
    assert result == (state, None, None) and not applied
    assert state[compat.HEAD] is not state[compat.EMBEDDING]


@pytest.mark.parametrize(
    "changes",
    [
        {"tie_word_embeddings": False},
        {"tie_word_embeddings": 1},
        {"model_type": "llama"},
        {"hidden_size": 1024},
        {"vocab_size": 42},
    ],
)
def test_untied_or_wrong_configuration_rejected(changes):
    with pytest.raises(RuntimeError, match="INCOMPATIBLE"):
        compat.tied_head_preprocessor(identity, CONFIG | changes, [])


@pytest.mark.parametrize("embedding", [None, object(), SimpleNamespace(tensor_shape=(42, 2560))])
def test_missing_or_wrong_embedding_does_not_hide_missing_weights(embedding):
    state = {} if embedding is None else {compat.EMBEDDING: embedding}
    with pytest.raises(RuntimeError, match="missing or has another shape"):
        compat.tied_head_preprocessor(identity, CONFIG, [])(state)
    assert compat.HEAD not in state


def test_conflicting_tie_source_rejected_and_original_callback_errors_propagate():
    state = {compat.EMBEDDING: SimpleNamespace(tensor_shape=(151936, 2560))}
    with pytest.raises(RuntimeError, match="conflicting"):
        compat.tied_head_preprocessor(identity, CONFIG, [])(state, None, {"wrong": [compat.HEAD]})

    def broken(*_args):
        raise ValueError("Duplicate weight after GGUF mapping")

    with pytest.raises(ValueError, match="Duplicate"):
        compat.tied_head_preprocessor(broken, CONFIG, [])(state)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    (tmp_path / ".studio-revision").write_text(compat.ENGINE_REVISION)
    hashes = {}
    for relative in compat.SOURCE_HASHES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(CONFIG) if relative.endswith("config.json") else "tiny contract source")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(compat, "SOURCE_HASHES", hashes)
    module = SimpleNamespace(
        __file__=str(tmp_path / "models/flux/modules/text_encoder_qwen3.py"),
        _build_qwen3_state_dict_preprocessor=lambda _path: identity,
    )
    return tmp_path, module


def test_scoped_factory_restored_on_failure_and_inputs_unchanged(engine):
    root, module = engine
    before = {relative: (root / relative).read_bytes() for relative in compat.SOURCE_HASHES}
    original = module._build_qwen3_state_dict_preprocessor
    with pytest.raises(RuntimeError, match="test failure"):
        with compat.scoped_tied_head(root, module) as report:
            callback = module._build_qwen3_state_dict_preprocessor(root / "ckpts/Qwen3/config.json")
            result = callback({compat.EMBEDDING: SimpleNamespace(tensor_shape=(151936, 2560))})
            assert result[2] == {compat.EMBEDDING: [compat.HEAD]}
            assert len(report["applied"]) == 1
            raise RuntimeError("test failure")
    assert module._build_qwen3_state_dict_preprocessor is original
    assert before == {relative: (root / relative).read_bytes() for relative in compat.SOURCE_HASHES}


@pytest.mark.parametrize("changed", ["revision", "source", "module", "config"])
def test_unknown_revision_source_module_or_configuration_refused(engine, changed):
    root, module = engine
    original = module._build_qwen3_state_dict_preprocessor
    if changed == "revision":
        (root / ".studio-revision").write_text("another revision")
    elif changed == "source":
        (root / "mmgp/offload.py").write_text("changed")
    elif changed == "module":
        module.__file__ = str(root / "wrong.py")
    else:
        (root / "ckpts/Qwen3/config.json").write_text("{}")
    with pytest.raises(RuntimeError, match="INCOMPATIBLE"):
        with compat.scoped_tied_head(root, module):
            pytest.fail("Changed engine must not be patched")
    assert module._build_qwen3_state_dict_preprocessor is original


def test_scoped_factory_refuses_other_encoder_config_and_restores(engine):
    root, module = engine
    original = module._build_qwen3_state_dict_preprocessor
    with compat.scoped_tied_head(root, module):
        with pytest.raises(RuntimeError, match="Unexpected encoder configuration"):
            module._build_qwen3_state_dict_preprocessor(root / "other/config.json")
    assert module._build_qwen3_state_dict_preprocessor is original


def test_normal_bridge_never_imports_or_applies_experimental_compatibility(tmp_path):
    with encoder_compatibility_context({"kind": "image", "model": "flux2_klein_4b"}, tmp_path) as record:
        assert record is None
    provider = WanGPProvider(WanGPConfig(), tmp_path)
    assert provider.encoder_compatibility is None


@pytest.mark.parametrize(
    "fields",
    [
        {"encoder_compatibility": "unknown"},
        {"encoder_compatibility": "qwen3_tied_head_v1", "kind": "video"},
        {"encoder_compatibility": "qwen3_tied_head_v1", "kind": "image", "model": "another"},
    ],
)
def test_bridge_rejects_unsupported_scope_before_importing_model(tmp_path, fields):
    with pytest.raises(RuntimeError, match="restricted"):
        encoder_compatibility_context(fields, tmp_path)


def test_provider_only_allows_known_compatibility_for_separate_profile(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        WanGPProvider(WanGPConfig(image_model="other"), tmp_path, encoder_compatibility="qwen3_tied_head_v1")
    with pytest.raises(ValueError, match="Unsupported"):
        WanGPProvider(
            WanGPConfig(image_model="flux2_klein_4b_studio_q4"), tmp_path, encoder_compatibility="unknown"
        )


@pytest.mark.parametrize("success", [True, False])
def test_actual_bridge_scopes_factory_and_records_used_alias(engine, monkeypatch, success):
    import sys

    from tests.test_providers import Session

    root, module = engine
    original = module._build_qwen3_state_dict_preprocessor
    output = root / "output"
    output.mkdir()
    image = output / "tiny-contract-output.png"
    image.write_bytes(b"explicit contract fixture, not an image or inference")

    class ContractSession(Session):
        def submit_task(self, _parameters):
            assert module._build_qwen3_state_dict_preprocessor is not original
            callback = module._build_qwen3_state_dict_preprocessor(root / "ckpts/Qwen3/config.json")
            callback({compat.EMBEDDING: SimpleNamespace(tensor_shape=(151936, 2560))})
            result = SimpleNamespace(
                success=success,
                generated_files=[str(image)],
                errors=[SimpleNamespace(message="contract failure")],
            )
            return SimpleNamespace(done=True, result=lambda: result)

    monkeypatch.setitem(sys.modules, "shared.api", SimpleNamespace(init=lambda **_kwargs: ContractSession()))
    monkeypatch.setitem(sys.modules, "models.flux.modules", SimpleNamespace(text_encoder_qwen3=module))
    request = {
        "kind": "image",
        "model": "flux2_klein_4b_studio_q4",
        "encoder_compatibility": "qwen3_tied_head_v1",
        "prompt": "contract only",
        "resolution": "512x512",
        "seed": 42,
        "steps": 4,
        "timeout": 1,
    }
    response = root / "response.json"
    sampler = SimpleNamespace(mark_phase=lambda _phase: None)
    if success:
        run_session(request, root, output, response, sampler)
        result = json.loads(response.read_bytes())
        assert len(result["runtime_options"]["encoder_compatibility"]["applied"]) == 1
    else:
        with pytest.raises(RuntimeError, match="contract failure"):
            run_session(request, root, output, response, sampler)
        assert not response.exists()
    assert module._build_qwen3_state_dict_preprocessor is original
