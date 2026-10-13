"""Discovery and previous smoke observations, without importing an AI runtime."""

import json
import math
from pathlib import Path


def read_runtime_status(root: Path):
    return _read_gpu_status(
        root / "tools/gpu/runtime-status.json",
        {"OS_POLICY_BLOCKED", "RUNTIME_DISCOVERED_NOT_INFERENCE", "FAILED"},
    )


def read_image_status(root: Path):
    return _read_gpu_status(
        root / "tools/gpu/image-status.json",
        {"IMAGE_RAM_GUARD_STOP", "FAILED", "GENERATED_PENDING_VISUAL_REVIEW"},
    )


def _read_gpu_status(path, allowed):
    try:
        if path.stat().st_size > 65536:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("code") not in allowed:
            return None
        if not isinstance(record.get("checked_at"), (float, int)):
            return None
        if (
            not math.isfinite(record["checked_at"])
            or record["checked_at"] <= 0
            or not isinstance(record.get("installation"), str)
            or not record["installation"]
            or "\x00" in record["installation"]
        ):
            return None
        return record
    except (OSError, ValueError, AttributeError):
        return None


def read_cpu_status(root: Path, profile="cpu_1_5b"):
    model = {"cpu_1_5b": "Qwen2.5-1.5B-Instruct-Q4_K_M", "cpu_4b": "Qwen3-4B-Instruct-2507-Q4_K_M"}[profile]
    filename = "cpu-4b-writing-status.json" if profile == "cpu_4b" else "cpu-writing-status.json"
    path = root / "tools/story" / filename
    try:
        if path.stat().st_size > 65536:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if (
            record.get("code") not in {"STRUCTURE_PASS_QUALITY_FAILED", "WRITING_FAILED"}
            or record.get("model") != model
            or Path(record.get("installation", "")).resolve() != (root / "tools/story").resolve()
        ):
            return None
        for key in ("checked_at", "elapsed_seconds", "sampled_peak_server_rss_bytes"):
            if (
                not isinstance(record.get(key), (int, float))
                or not math.isfinite(record[key])
                or record[key] <= 0
            ):
                return None
        return record
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def classify(
    providers,
    memory,
    last_runtime=None,
    selected_installation="",
    last_cpu=None,
    last_cpu_4b=None,
    last_image=None,
    selected_image_model="",
):
    for provider in providers:
        installed = provider["available"]
        provider["status"] = (
            "Available"
            if installed and provider.get("is_mock")
            else "Installed"
            if installed
            else "Setup needed"
        )
        provider["attention"] = not installed
        if provider["id"] in {"cpu-1-5b", "cpu-4b"} and installed:
            minimum = 7 if provider["id"] == "cpu-4b" else 5
            observation = last_cpu_4b if provider["id"] == "cpu-4b" else last_cpu
            free = memory.get("free_gb")
            if not memory.get("available") or free is None:
                provider.update(status="RAM not measured", attention=True)
                provider["message"] += " Memory counters must be available before loading."
            elif free < minimum:
                provider.update(status="Needs free RAM", attention=True)
                provider["message"] += (
                    f" Currently {free} GiB free; minimum {minimum} GiB. Close heavy applications and refresh diagnostics."
                )
            else:
                provider["status"] = "Installed · untested"
            if observation:
                provider.update(last_check_at=observation["checked_at"], attention=True, verified=False)
                if provider["status"] == "Installed · untested":
                    provider["status"] = "Tested · writing needs work"
                detail = (
                    "its structure passed but manual writing quality failed"
                    if observation["code"] == "STRUCTURE_PASS_QUALITY_FAILED"
                    else "writing did not finish successfully"
                )
                provider["message"] += (
                    f" Last CPU writing test: {observation['elapsed_seconds']:.1f} seconds; {detail}. No image/video generation was tested."
                )
        if provider["id"] == "small-cpu" and installed:
            provider["status"] = "Feasibility only"
        if provider["id"] == "windows-speech" and installed:
            provider["status"] = "Available"
        if provider["id"] == "local-video" and last_runtime:
            # Do not associate a previous app-owned test with another selected installation.
            try:
                matching = (
                    not selected_installation
                    or Path(selected_installation).resolve()
                    == Path(last_runtime.get("installation", "")).resolve()
                )
            except (ValueError, OSError, TypeError):
                matching = False
            if matching:
                provider["last_check_at"] = last_runtime["checked_at"]
                if last_runtime["code"] == "OS_POLICY_BLOCKED":
                    provider.update(status="Last check blocked", attention=True)
                    provider["message"] = (
                        "The last installed-runtime test stopped before inference: Windows Application Control blocked a CUDA dependency. The studio does not change Windows security policy. No image/video or 6 GB fit is verified."
                    )
                elif last_runtime["code"] == "RUNTIME_DISCOVERED_NOT_INFERENCE":
                    provider["message"] += (
                        " Runtime discovery passed; image/video inference remains untested."
                    )
                elif last_runtime["code"] == "FAILED":
                    provider.update(status="Last runtime check failed", attention=True)
                    provider["message"] = (
                        "The last installed-runtime test stopped before inference. Review the saved runtime diagnostics; image/video generation and 6 GB fit remain unverified."
                    )
        if provider["id"] == "local-video" and last_image:
            try:
                matching_image = (
                    (
                        not selected_installation
                        or Path(selected_installation).resolve()
                        == Path(last_image.get("installation", "")).resolve()
                    )
                    and (not selected_image_model or selected_image_model == last_image.get("model"))
                    and not (
                        last_runtime
                        and last_runtime["code"] == "OS_POLICY_BLOCKED"
                        and last_runtime["checked_at"] > last_image["checked_at"]
                    )
                )
            except (ValueError, OSError, TypeError):
                matching_image = False
            if matching_image:
                provider.update(last_image_check_at=last_image["checked_at"], attention=True, verified=False)
                if last_image["code"] == "IMAGE_RAM_GUARD_STOP":
                    provider.update(
                        status="Image test needs RAM",
                        message="The last real image load stopped below 2 GiB free RAM. No image was produced. Image/video generation and 6 GB compatibility remain unverified.",
                    )
                elif last_image["code"] == "FAILED":
                    provider.update(
                        status="Last image test failed",
                        message="The last real image test failed. Review its saved diagnostics; no image/video quality or 6 GB fit is verified.",
                    )
                else:
                    provider.update(
                        status="Image awaits review",
                        message="An image was generated in a separate test and awaits visual review. This does not verify video generation or reliable 6 GB operation.",
                    )
    return providers
