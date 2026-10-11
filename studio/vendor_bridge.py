"""Standalone, stdlib-only bridge executed by the user's separate WanGP Python.

No vendor code is bundled. Calls match inspected official b/main API contracts.
External network is refused; absent local weights never trigger downloads.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path


def build_settings(session, request):
    model = request["model"]
    availability = session.get_model_availability(model)
    if availability.get("status") != "available" or not availability.get("available"):
        raise RuntimeError(
            "MISSING_MODEL: WanGP reports missing or partially installed weights. Downloads are disabled."
        )
    schema = session.get_model_schema(model)
    if not schema:
        raise RuntimeError("INCOMPATIBLE: Unknown WanGP model")
    kinds = schema.get("main_output", [])
    if isinstance(kinds, str):
        kinds = [kinds]
    if request["kind"] not in kinds:
        raise RuntimeError("INCOMPATIBLE: Selected model does not produce this media type")
    parameters = session.get_default_settings(model)
    parameters.update(
        {
            "model_type": model,
            "prompt": request["prompt"],
            "resolution": request["resolution"],
            "seed": request["seed"],
            "num_inference_steps": request["steps"],
        }
    )
    if request["kind"] == "image":
        parameters["image_mode"] = 1
        if request.get("references"):
            if not schema.get("media_inputs", {}).get("image", {}).get("reference"):
                raise RuntimeError(
                    "INCOMPATIBLE: This image model does not support identity reference conditioning."
                )
            parameters["image_refs"] = request["references"]
    else:
        if not schema.get("capabilities", {}).get("image_to_video"):
            raise RuntimeError("INCOMPATIBLE: This video model does not support image-to-video.")
        parameters.update(
            {"image_start": request["start_image"], "video_length": f"{request['seconds']}s", "force_fps": 24}
        )
    return parameters, schema


def require_success(result, directory: Path):
    if not result.success:
        messages = "; ".join(str(getattr(e, "message", e)) for e in result.errors)
        code = (
            "OUT_OF_MEMORY"
            if any(word in messages.lower() for word in ["out of memory", "cuda oom"])
            else "PROVIDER_FAILED"
        )
        raise RuntimeError(f"{code}: {messages or 'WanGP returned no successful task'}")
    files = [Path(p).resolve() for p in result.generated_files]
    files = [p for p in files if p.is_relative_to(directory.resolve()) and p.is_file()]
    if not files:
        raise RuntimeError("BAD_OUTPUT: WanGP did not return files inside its scoped output folder")
    return files


def offline_network():
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
    connect = socket.socket.connect

    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError(
                "DOWNLOAD_BLOCKED: Provider network downloads are disabled; install approved weights separately."
            )
        return connect(sock, address)

    socket.socket.connect = local_connect


def main():
    request_path, response_path = map(Path, sys.argv[1:3])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    directory = Path(request["output_dir"]).resolve()
    data_root = Path(request["data_root"]).resolve()
    if not directory.is_relative_to(data_root):
        raise RuntimeError("Unsafe output directory")
    for path in request.get("references", []) + (
        [request["start_image"]] if request.get("start_image") else []
    ):
        if not Path(path).resolve().is_relative_to(data_root):
            raise RuntimeError("Unsafe input media path")
    root = Path(request["installation"]).resolve()
    if not (root / "wgp.py").is_file() or not (root / "shared" / "api.py").is_file():
        raise RuntimeError("MISSING_PROVIDER: WanGP installation has no official shared/api.py")
    directory.mkdir(parents=True, exist_ok=True)
    offline_network()
    # This module lives alongside the standalone bridge, independent of Studio's venv.
    from vendor_telemetry import Sampler

    telemetry = Sampler(directory / "provider-telemetry.json")
    telemetry.start()
    try:
        run_session(request, root, directory, response_path)
    finally:
        telemetry.close()


def run_session(request, root, directory, response_path):
    sys.path.insert(0, str(root))
    from shared.api import init

    session = init(
        root=root,
        output_dir=directory,
        cli_args=["--attention", "sdpa", "--profile", "4"],
        console_output=False,
    )
    if request["kind"] == "discover":
        result = {
            "models": session.list_model_metadata(
                include_availability=True, main_output=["image", "video"], limit=100
            )
        }
    else:
        parameters, schema = build_settings(session, request)
        job = session.submit_task(parameters)
        deadline = time.monotonic() + request["timeout"]
        while not job.done:
            if (directory / "cancel.request").exists() or time.monotonic() > deadline:
                job.cancel()
                raise RuntimeError("CANCELLED_OR_TIMEOUT: WanGP generation stopped.")
            time.sleep(0.2)
        generated = require_success(job.result(), directory)
        result = {
            "files": [str(p) for p in generated],
            "schema": schema,
            "model": request["model"],
            "parameters": parameters,
            "is_mock": False,
        }
    temporary = response_path.with_suffix(".partial")
    temporary.write_text(json.dumps(result, default=str), encoding="utf-8")
    temporary.replace(response_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
