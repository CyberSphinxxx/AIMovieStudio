"""Optional subprocess-local resource sampling using its installed runtime libraries."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque


class Sampler:
    def __init__(self, path):
        self.path = path
        self.stop = threading.Event()
        self.started = time.monotonic()
        self.samples = deque(maxlen=120)
        self.sample_count = 0
        self.peaks = {"rss_bytes": None, "global_vram_bytes": None, "temperature_c": None}
        self.minimum_ram = None
        self.phase = "starting"
        self.closed = False
        self.lock = threading.RLock()
        self.errors = []
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def start(self):
        self.persist()
        self.thread.start()

    def mark_phase(self, phase):
        with self.lock:
            if self.phase == phase[:80]:
                return
            self.phase = phase[:80]
            self.persist()

    def on_progress(self, update):
        # Documented WanGP callback; do not capture status text, prompts or stream output.
        phase = getattr(update, "phase", None)
        if phase in {
            "loading_model",
            "encoding_text",
            "inference",
            "inference_stage_1",
            "inference_stage_2",
            "inference_stage_3",
            "decoding",
            "downloading_output",
            "cancelled",
        }:
            self.mark_phase(phase)

    def record(self, sample):
        with self.lock:
            self.samples.append({**sample, "phase": self.phase})
            self.sample_count += 1
            for key in self.peaks:
                self.peaks[key] = max(self.peaks[key] or 0, sample[key])
            value = sample["available_ram_bytes"]
            self.minimum_ram = value if self.minimum_ram is None else min(self.minimum_ram, value)
            self.persist()

    def sample(self):
        try:
            import psutil
            import pynvml

            process = psutil.Process(os.getpid())
            pynvml.nvmlInit()
            gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
            while not self.stop.is_set():
                memory = pynvml.nvmlDeviceGetMemoryInfo(gpu)
                self.record(
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
            with self.lock:
                self.errors.append(str(error)[:500])
                self.persist()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        with self.lock:
            self.closed = not self.thread.is_alive()
            return self.persist()

    def persist(self):
        with self.lock:
            return self._persist()

    def _persist(self):
        data = {
            "sample_interval_seconds": 1,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "samples": list(self.samples),
            "sample_count": self.sample_count,
            "recent_sample_limit": self.samples.maxlen,
            "phase": self.phase,
            "sampler_closed": self.closed,
            "sampling_errors": self.errors[:8],
            "peak_rss_bytes_sampled": self.peaks["rss_bytes"],
            "peak_global_vram_bytes_sampled": self.peaks["global_vram_bytes"],
            "peak_temperature_c_sampled": self.peaks["temperature_c"],
            "min_available_ram_bytes_sampled": self.minimum_ram,
            "note": "Sampled lifetime extrema, not absolute peaks. Recent samples bounded; VRAM is whole-device usage. Sampler closure does not establish generation success.",
        }
        temporary = self.path.with_suffix(".partial")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError as error:
            # Diagnostics cannot turn a completed generation into failure. Keep the last atomic file.
            message = str(error)[:500]
            if message not in self.errors and len(self.errors) < 8:
                self.errors.append(message)
        return data
