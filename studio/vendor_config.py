"""Scoped WanGP configuration overrides, independent of Studio's runtime packages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Preserve generation-related settings only; never copy cloud/plugin credentials.
RUNTIME_KEYS = frozenset(
    {
        "checkpoints_paths",
        "loras_root",
        "attention_mode",
        "transformer_quantization",
        "text_encoder_quantization",
        "int8_kernels",
        "kernel_precision",
        "attention_head_split",
        "ram_allocator",
        "vram_allocator",
        "perc_reserved_mem_max",
        "vae_config",
        "compile",
        "read_ahead",
        "boost",
        "profile",
        "video_profile",
        "image_profile",
        "audio_profile",
        "video_preload_mode",
        "image_preload_mode",
        "audio_preload_mode",
        "prefetch_window",
        "video_preload_in_VRAM",
        "image_preload_in_VRAM",
        "audio_preload_in_VRAM",
    }
)


def session_config(root: Path, directory: Path, smart_pinning: bool | None):
    source = root / "wgp_config.json"
    data, source_sha = {}, None
    if source.exists():
        if not source.resolve().is_relative_to(root.resolve()) or source.stat().st_size > 1024 * 1024:
            raise RuntimeError("INCOMPATIBLE: Engine configuration is outside its folder or too large.")
        with source.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("INCOMPATIBLE: Engine configuration grew beyond its size limit.")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise RuntimeError("INCOMPATIBLE: Engine configuration contains invalid JSON.") from error
        source_sha = hashlib.sha256(raw).hexdigest()
        if not isinstance(data, dict):
            raise RuntimeError("INCOMPATIBLE: Expected an engine configuration object.")
    inherited = data.get("smart_memory_pinning", True)
    if not isinstance(inherited, bool) or (smart_pinning is not None and not isinstance(smart_pinning, bool)):
        raise RuntimeError("INCOMPATIBLE: Engine transfer-buffer option must be a boolean.")
    if smart_pinning is None:
        return None, {"smart_memory_pinning": inherited, "override": False, "config_input_sha256": source_sha}
    scoped = {key: value for key, value in data.items() if key in RUNTIME_KEYS}
    scoped.update(
        {
            "smart_memory_pinning": smart_pinning,
            "deepy_enabled": 0,
            "enhancer_enabled": 0,
            "notification_on_generation": False,
            "notification_on_queue_complete": False,
        }
    )
    path = directory / "provider-config" / "wgp_config.json"
    if not path.resolve().is_relative_to(directory.resolve()):
        raise RuntimeError("INCOMPATIBLE: Scoped engine configuration escaped its output folder.")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(scoped, sort_keys=True, indent=2).encode("utf-8")
    temporary = path.with_suffix(".partial")
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return path, {
        "smart_memory_pinning": smart_pinning,
        "override": True,
        "config_input_sha256": hashlib.sha256(raw).hexdigest(),
    }
