"""Optional subprocess-local resource sampling using its installed runtime libraries."""

from __future__ import annotations

import json
import os
import threading
import time


class Sampler:
    def __init__(self, path):
        self.path = path
        self.stop = threading.Event()
        self.started = time.monotonic()
        self.samples = []
        self.errors = []
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def start(self):
        self.thread.start()

    def sample(self):
        try:
            import psutil
            import pynvml

            process = psutil.Process(os.getpid())
            pynvml.nvmlInit()
            gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
            while not self.stop.is_set():
                memory = pynvml.nvmlDeviceGetMemoryInfo(gpu)
                self.samples.append(
                    {
                        "seconds": round(time.monotonic() - self.started, 2),
                        "rss_bytes": process.memory_info().rss,
                        "available_ram_bytes": psutil.virtual_memory().available,
                        "global_vram_bytes": memory.used,
                        "temperature_c": pynvml.nvmlDeviceGetTemperature(gpu, pynvml.NVML_TEMPERATURE_GPU),
                    }
                )
                self.stop.wait(1)
            pynvml.nvmlShutdown()
        except Exception as error:
            self.errors.append(str(error)[:500])

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        data = {
            "sample_interval_seconds": 1,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "samples": self.samples,
            "sampling_errors": self.errors,
            "peak_rss_bytes_sampled": max((s["rss_bytes"] for s in self.samples), default=None),
            "peak_global_vram_bytes_sampled": max(
                (s["global_vram_bytes"] for s in self.samples), default=None
            ),
            "peak_temperature_c_sampled": max((s["temperature_c"] for s in self.samples), default=None),
            "note": "Sampled maxima, not guaranteed absolute peaks. VRAM is whole-device usage.",
        }
        temporary = self.path.with_suffix(".partial")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return data
