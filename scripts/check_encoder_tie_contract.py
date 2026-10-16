"""Run pinned mapping/tie source against tiny objects, never import AI runtimes."""

import ast
import hashlib
import json
import os
from types import SimpleNamespace
from uuid import uuid4

from scripts.encoder_experiment import ROOT
from studio.storage import atomic_json
from studio.vendor_qwen_compat import EMBEDDING, HEAD, scoped_tied_head


def main():
    root = ROOT / "tools/wan-gp"
    path = root / "models/flux/modules/text_encoder_qwen3.py"
    mapping_path = root / "shared/utils/gguf_mapping.py"
    namespace = {"os": os, "_HF_TOKEN_EMBEDDING_KEY": EMBEDDING}
    # These inspected helpers have no imports or runtime initialization.
    mapping_tree = ast.parse(mapping_path.read_text(encoding="utf-8"))
    nodes = [node for node in mapping_tree.body if isinstance(node, (ast.FunctionDef, ast.Assign))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(mapping_path), "exec"), namespace)
    qwen_tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in qwen_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_qwen3_gguf_mapping_needed", "_build_qwen3_state_dict_preprocessor"}
    ]
    if len(nodes) != 2:
        raise RuntimeError("Pinned Qwen preprocessing functions missing")
    namespace["_qwen3_gguf_name_map"] = lambda _path: {
        "token_embd.weight": EMBEDDING,
        "blk.0.attn_q.weight": "model.layers.0.self_attn.q_proj.weight",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    module = SimpleNamespace(
        __file__=str(path),
        _build_qwen3_state_dict_preprocessor=namespace["_build_qwen3_state_dict_preprocessor"],
    )
    original = module._build_qwen3_state_dict_preprocessor
    packed = SimpleNamespace(tensor_shape=(151936, 2560))
    tiny = {"token_embd.weight": packed, "blk.0.attn_q.weight": object()}
    config = root / "ckpts/Qwen3/config.json"
    baseline = original(str(config))(tiny)
    if EMBEDDING not in baseline[0] or HEAD in baseline[0] or baseline[2] is not None:
        raise RuntimeError("Pinned source no longer reproduces the missing tied-head condition")
    offload_path = root / "mmgp/offload.py"
    offload_tree = ast.parse(offload_path.read_text(encoding="utf-8"))
    loops = [
        node
        for node in ast.walk(offload_tree)
        if isinstance(node, ast.For)
        and ast.unparse(node.target) == "(name, tied_weights_list)"
        and ast.unparse(node.iter) == "tied_weights_map.items()"
    ]
    if len(loops) != 1:
        raise RuntimeError("Pinned MMGP tied-weight loop changed")
    with scoped_tied_head(root, module) as compatibility:
        state, quant, tied = module._build_qwen3_state_dict_preprocessor(str(config))(tiny)
        loader_namespace = {"state_dict": state, "tied_weights_map": tied}
        exec(compile(ast.Module(body=loops, type_ignores=[]), str(offload_path), "exec"), loader_namespace)
        if state[HEAD] is not packed or state[EMBEDDING] is not packed or quant is not None:
            raise RuntimeError("Pinned loader did not retain the exact same packed-object alias")
    if module._build_qwen3_state_dict_preprocessor is not original or HEAD in tiny:
        raise RuntimeError("Scoped compatibility failed to preserve original inputs/factory")
    report = {
        "status": "PINNED_MAPPING_TIE_CONTRACT_PASS_NOT_NATIVE_LOADING",
        "scope": "Actual pinned preprocessing, mapping and MMGP alias loop; tiny Python objects; HF name-map dependency substituted. No torch/quantized runtime/model payload/inference.",
        "baseline_missing_head_reproduced": True,
        "same_object_alias": True,
        "original_factory_restored": True,
        "compatibility": compatibility,
        "mapping_source_sha256": hashlib.sha256(mapping_path.read_bytes()).hexdigest(),
    }
    output = ROOT / f"ops/evidence/encoder-tie-source-contract-{uuid4().hex}.json"
    atomic_json(output, report)
    print(json.dumps(report | {"report": str(output)}))


if __name__ == "__main__":
    main()
