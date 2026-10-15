"""Passive scheduling checks. Actual providers always repeat their safety guards."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from studio.domain import StrictModel
from studio.diagnostics import memory_status, runtime_memory_known, gpu_reading_known
from studio.inference_lock import inference_busy

RECHECK_SECONDS = 15
WAIT_SECONDS = 24 * 60 * 60
WAIT_STATE = "WAITING_RESOURCES"
STORY_STAGES = {"PLAN", "SCRIPT", "DRAFT", "SCRIPT_BATCH", "DRAFT_BATCH"}
GPU_STAGES = {"REFERENCE", "FRAME", "CLIP", "REFERENCE_VARIANT", "RETAKE_FRAME", "RETAKE_CLIP"}


class ResourceReason(StrictModel):
    code: Literal["MEMORY_BUSY", "GRAPHICS_BUSY", "GPU_HOT", "COUNTERS_UNKNOWN", "INFERENCE_BUSY"]
    message: str = Field(min_length=1, max_length=400)


class ResourceWait(ResourceReason):
    step_id: str = Field(min_length=1, max_length=100)
    stage: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z_]+$")
    since: float = Field(ge=0, allow_inf_nan=False)
    deadline: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_deadline(self):
        if not 0 < self.deadline - self.since <= WAIT_SECONDS + 0.01:
            raise ValueError("Resource wait deadline must be within 24 hours")
        return self


def load_wait(db, jid):
    row = db.execute(
        "SELECT data FROM events WHERE job_id=? AND kind='resource_wait' ORDER BY seq DESC LIMIT 1", (jid,)
    ).fetchone()
    return ResourceWait.model_validate_json(row["data"]) if row else None


def probe(step: dict, settings: dict, spec: dict, gpu_reader) -> ResourceReason | None:
    if spec.get("backend") != "local":
        return None
    minimum, needs_gpu = None, False
    if step["stage"] in STORY_STAGES and settings.get("story_engine") in {"small_cpu", "cpu_1_5b", "cpu_4b"}:
        from studio.local_story import ROOT, CPU_PROFILES

        profile = settings["story_engine"]
        _, filename, size, _ = CPU_PROFILES[profile]
        folder = ROOT / "tools/story"
        try:
            installed = (folder / "llama-server.exe").is_file() and (folder / filename).stat().st_size == size
        except OSError:
            installed = False
        if not installed:
            return None  # The provider reports missing/changed setup instead of waiting for RAM.
        minimum = 7 if profile == "cpu_4b" else 5 if profile == "cpu_1_5b" else 2
    elif step["stage"] in STORY_STAGES and settings.get("story_model"):
        if inference_busy():
            return busy_reason()
        return None  # External Ollama's memory configuration is not inferred here.
    elif step["stage"] in GPU_STAGES:
        from studio.providers import WanGPConfig, WanGPProvider
        from studio.media import ROOT

        provider = WanGPProvider(WanGPConfig(**settings.get("wangp", {})), ROOT)
        if not provider.configured():
            return None
        minimum, needs_gpu = 5, True
    if minimum is None:
        return None
    if inference_busy():
        return busy_reason()
    try:
        memory = memory_status()
    except OSError:
        memory = {}
    if not runtime_memory_known(memory):
        return ResourceReason(
            code="COUNTERS_UNKNOWN",
            message="Waiting for reliable memory readings. Review Settings if this continues.",
        )
    if memory["free_gb"] < minimum:
        return ResourceReason(
            code="MEMORY_BUSY", message=f"Waiting for at least {minimum} GB of free memory."
        )
    if needs_gpu:
        try:
            gpu = gpu_reader()
        except (OSError, RuntimeError):
            gpu = {}
        if not gpu_reading_known(gpu):
            return ResourceReason(
                code="COUNTERS_UNKNOWN",
                message="Waiting for reliable graphics readings. Review Settings if this continues.",
            )
        if gpu["temperature_c"] >= 85:
            return ResourceReason(code="GPU_HOT", message="Waiting for the graphics card to cool below 85°C.")
        if gpu["total_mb"] - gpu["used_mb"] < 4096:
            return ResourceReason(
                code="GRAPHICS_BUSY", message="Waiting for at least 4 GB of free graphics memory."
            )
    return None


def busy_reason() -> ResourceReason:
    return ResourceReason(
        code="INFERENCE_BUSY",
        message="Waiting for another Studio process to finish using the local AI engine.",
    )
