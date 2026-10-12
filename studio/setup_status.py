"""Discovery and previous smoke observations, without importing an AI runtime."""

import json
import math
from pathlib import Path


def read_runtime_status(root: Path):
    path = root / "tools/gpu/runtime-status.json"
    try:
        if path.stat().st_size > 65536:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("code") not in {"OS_POLICY_BLOCKED", "RUNTIME_DISCOVERED_NOT_INFERENCE", "FAILED"}:
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


def classify(providers, memory, last_runtime=None, selected_installation=""):
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
        if provider["id"] == "cpu-1-5b" and installed:
            free = memory.get("free_gb")
            if not memory.get("available") or free is None:
                provider.update(status="RAM not measured", attention=True)
                provider["message"] += " Memory counters must be available before loading."
            elif free < 5:
                provider.update(status="Needs free RAM", attention=True)
                provider["message"] += (
                    f" Currently {free} GiB free; minimum 5 GiB. Close heavy applications and refresh diagnostics."
                )
            else:
                provider["status"] = "Installed · untested"
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
    return providers
