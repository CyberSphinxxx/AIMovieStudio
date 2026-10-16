"""Experimental tied-head preprocessor; dormant until explicitly installed.

No model imports or vendor edits. This supplies MMGP's existing tied-weight map
after its Qwen GGUF name mapping; it never permits arbitrary missing weights.
Native loading, quantized alias behavior and memory fit remain unverified.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

EMBEDDING = "model.embed_tokens.weight"
HEAD = "lm_head.weight"
ENGINE_REVISION = "6479db36bdc2619a904a852bba9c2d78e1a83f82"
SOURCE_HASHES = {
    "shared/utils/gguf_mapping.py": "5f60507c6c9bd1108d844e64870aa4d436fdfde92491fd6f4d983dbdb9c3709d",
    "models/flux/modules/text_encoder_qwen3.py": "c9a9d9e3d29956410662cdae88670f69d7f78ab60f2697d85db6f30fd14c3cdb",
    "mmgp/offload.py": "0935bcb628a35635eee7d747b756a2c93a6df4916d7c8ce01831b61a852e3288",
    "shared/qtypes/gguf.py": "87afd75652d0dd104bbaec1dadd8a268b78dd377c8fe7ce6292dffd62b117b0f",
    "ckpts/Qwen3/config.json": "8ba006f74fecfaaeb392872a60f4a480e7ec9860153d2e1b769ec81f9a147f8a",
}


def tied_head_preprocessor(original, config: dict, applied: list):
    if (
        config.get("model_type") != "qwen3"
        or config.get("tie_word_embeddings") is not True
        or (config.get("vocab_size"), config.get("hidden_size")) != (151936, 2560)
    ):
        raise RuntimeError("INCOMPATIBLE: Tied-head experiment requires the inspected Qwen3 configuration")

    def preprocess(state_dict, quantization_map=None, tied_weights_map=None):
        mapped, quantization, tied = original(state_dict, quantization_map, tied_weights_map)
        if HEAD in mapped:
            # An explicitly stored output projection must never be replaced.
            return mapped, quantization, tied
        embedding = mapped.get(EMBEDDING)
        if embedding is None or tuple(getattr(embedding, "tensor_shape", ())) != (151936, 2560):
            raise RuntimeError(
                "INCOMPATIBLE: Expected packed Qwen3 token embedding is missing or has another shape"
            )
        aliases = {} if tied is None else {key: list(values) for key, values in tied.items()}
        if any(HEAD in values for key, values in aliases.items() if key != EMBEDDING):
            raise RuntimeError("INCOMPATIBLE: Output head already has a conflicting tied-weight source")
        names = aliases.setdefault(EMBEDDING, [])
        if HEAD not in names:
            names.append(HEAD)
        applied.append(
            {
                "source": EMBEDDING,
                "alias": HEAD,
                "scope": "Existing packed tensor; no copy or missing-key bypass",
            }
        )
        return mapped, quantization, aliases

    return preprocess


@contextmanager
def scoped_tied_head(root: Path, module):
    """Only an explicit future experiment may install this in its owned child.

    The caller supplies the already imported, inspected encoder module. Default
    Studio generation does not call this function. Always restore its factory.
    """
    root = root.resolve()
    if (root / ".studio-revision").read_text() != ENGINE_REVISION:
        raise RuntimeError("INCOMPATIBLE: Tied-head experiment requires the pinned engine")
    for relative, expected in SOURCE_HASHES.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path.stat().st_size > 1_048_576:
            raise RuntimeError("INCOMPATIBLE: Compatibility source escaped its bounded engine folder")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("INCOMPATIBLE: Compatibility source or configuration changed")
    source = (root / "models/flux/modules/text_encoder_qwen3.py").resolve()
    if Path(module.__file__).resolve() != source:
        raise RuntimeError("INCOMPATIBLE: Loaded encoder module differs from the inspected source")
    config_path = (root / "ckpts/Qwen3/config.json").resolve()
    config = json.loads(config_path.read_bytes())
    original = module._build_qwen3_state_dict_preprocessor
    applied = []

    def factory(path):
        if Path(path).resolve() != config_path:
            raise RuntimeError("INCOMPATIBLE: Unexpected encoder configuration in scoped experiment")
        return tied_head_preprocessor(original(path), config, applied)

    module._build_qwen3_state_dict_preprocessor = factory
    try:
        yield {
            "compatibility": "qwen3_tied_head_v1",
            "source_hashes": dict(SOURCE_HASHES),
            "applied": applied,
        }
    finally:
        module._build_qwen3_state_dict_preprocessor = original
