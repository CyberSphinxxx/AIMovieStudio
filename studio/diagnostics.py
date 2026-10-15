from __future__ import annotations

import ctypes
import math
import os
import shutil
import sys
import time
from ctypes import wintypes

from studio.media import run

_cached: tuple[float, dict] = (0, {})


def runtime_memory_known(memory: dict) -> bool:
    value = memory.get("free_gb")
    return (
        memory.get("available") is True
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def gpu_reading_known(gpu: dict) -> bool:
    values = [gpu.get(key) for key in ("total_mb", "used_mb", "temperature_c")]
    return (
        gpu.get("available") is True
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
        and gpu["total_mb"] > 0
        and 0 <= gpu["used_mb"] <= gpu["total_mb"]
        and gpu["temperature_c"] >= 0
    )


def process_rss(pid: int) -> int | None:
    """Read-only Windows working-set counter; sampling is not an exact peak proof."""
    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in [
                "peak_rss",
                "rss",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
            ]
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        return None
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return counters.rss
        return None
    finally:
        kernel.CloseHandle(handle)


def memory_status() -> dict:
    if os.name != "nt":
        return {"available": False, "reason": "Windows memory counters unavailable"}

    class Memory(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
            (name, ctypes.c_uint64)
            for name in [
                "total_physical",
                "available_physical",
                "total_pagefile",
                "available_pagefile",
                "total_virtual",
                "available_virtual",
                "extended_virtual",
            ]
        ]

    status = Memory()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"available": False, "reason": "Windows memory query failed"}
    return {
        "available": True,
        "total_gb": round(status.total_physical / 1024**3, 2),
        "free_gb": round(status.available_physical / 1024**3, 2),
        "load_percent": status.load,
    }


def hardware(refresh=False) -> dict:
    global _cached
    if not refresh and time.monotonic() - _cached[0] < 30:
        return _cached[1] | {"memory": memory_status()}
    gpu = {"available": False, "message": "NVIDIA tools unavailable"}
    command = shutil.which("nvidia-smi")
    if command:
        try:
            output = (
                run(
                    [
                        command,
                        "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    timeout=5,
                )
                .decode()
                .strip()
                .splitlines()[0]
            )
            name, driver, total, used, temperature = [field.strip() for field in output.split(",")]
            gpu = {
                "available": True,
                "name": name,
                "driver": driver,
                "total_mb": int(total),
                "used_mb": int(used),
                "temperature_c": int(temperature),
            }
        except (RuntimeError, ValueError, IndexError):
            gpu = {
                "available": False,
                "message": "GPU diagnostic query failed; inference support remains unverified",
            }
    report = {
        "gpu": gpu,
        "python": sys.version.split()[0],
        "memory": memory_status(),
        "measured_at": time.time(),
    }
    _cached = (time.monotonic(), report)
    return report
