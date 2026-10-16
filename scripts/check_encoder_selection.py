"""Developer-only pinned source contract; reads local engine, never imports CUDA.

Requires the optional inspected vendor tree. Save results rather than vendor
source in Studio: the optional engine retains its separate license and notices.
"""

import ast
import json
import os
from uuid import uuid4

from scripts.encoder_experiment import PROFILE, ROOT, definition, locked_inputs
from studio.storage import atomic_json, digest


def main():
    engine, _ = locked_inputs(ROOT)
    path = engine / "wgp.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"get_model_recursive_prop", "get_model_filename"}
    ]
    if len(functions) != 2:
        raise RuntimeError("Pinned selection contract functions are missing")
    base = json.loads((engine / "defaults/flux2_klein_4b.json").read_bytes())["model"]
    model = definition(engine)["model"]
    namespace = {
        "os": os,
        # Dtype selection itself is outside this narrow configuration contract.
        "get_transformer_dtype": lambda *args: "bf16",
        "models_def": {"flux2_klein_4b": base, PROFILE: model},
        "model_types": ["flux2_klein_4b", PROFILE],
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    inherited = namespace["get_model_recursive_prop"](PROFILE)
    selected = namespace["get_model_filename"](PROFILE, quantization="int8", URLs=model["text_encoder_URLs"])
    if inherited != base["URLs"] or selected != model["text_encoder_URLs"][0]:
        raise RuntimeError("Pinned source did not select the intended existing base and local encoder")
    report = {
        "scope": "Actual pinned selection functions only, dtype dependency substituted; no runtime init or inference",
        "status": "CONFIGURATION_SELECTION_PASS_NOT_INFERENCE",
        "source_sha256": digest(path),
        "profile": PROFILE,
        "inherited_base_urls": inherited,
        "selected_encoder": selected,
    }
    output = ROOT / f"ops/evidence/encoder-selection-contract-{uuid4().hex}.json"
    atomic_json(output, report)
    print(json.dumps(report | {"report": str(output)}))


if __name__ == "__main__":
    main()
