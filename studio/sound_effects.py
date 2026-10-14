"""Original procedural sound library. No recordings, downloads or AI inference."""

from __future__ import annotations

import hashlib
import math
import os
import re
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol

from pydantic import Field
from studio.domain import StrictModel

VERSION = "procedural-effects-v1"
RIGHTS = "Original procedural synthesis in AI Movie Studio; no imported recording."
RATE = 16000


@dataclass(frozen=True)
class Effect:
    name: str
    duration: float
    pattern: str


LIBRARY = {
    "signal": Effect("Electronic signal", 0.6, r"\b(?:beeps?|beeping|alarm rings|radio crackles)\b"),
    "door": Effect(
        "Door movement", 0.45, r"\b(?:door (?:opens|closes|slams)|(?:opens|closes|slams) (?:the |a )?door)\b"
    ),
    "footsteps": Effect("Footsteps", 0.8, r"\b(?:footsteps|walks|walking|runs|running)\b"),
}


class SoundCue(StrictModel):
    shot_id: str = Field(min_length=1, max_length=100)
    shot_number: int = Field(ge=1, le=120)
    effect: Literal["signal", "door", "footsteps"]
    start: float = Field(ge=0, le=600)
    duration: float = Field(gt=0, le=1)
    seed: int = Field(ge=0, le=2**32 - 1)
    gain: float = Field(default=0.55, gt=0, le=0.8)


class SoundProvider(Protocol):
    def cues(self, shots: list[dict]) -> list[SoundCue]: ...
    def render(
        self, cues: list[SoundCue], duration: float, path: Path, check: Callable[[], None]
    ) -> None: ...


class ProceduralSound:
    def cues(self, shots):
        cues, start = [], 0.0
        for shot in shots:
            text = shot["action"].lower()
            # Conservative suppression; ambiguous or deliberately silent action gets no cue.
            quiet = re.search(
                r"\b(?:silently|silent|no sound|without (?:a |any )?sound|does not|doesn't|never|not)\b", text
            )
            for effect, entry in LIBRARY.items():
                if not quiet and re.search(entry.pattern, text):
                    offset = min(0.25, shot["duration"] * 0.15)
                    seed = int(
                        hashlib.sha256(f"{VERSION}:{shot['id']}:{effect}".encode()).hexdigest()[:8], 16
                    )
                    cues.append(
                        SoundCue(
                            shot_id=shot["id"],
                            shot_number=shot["number"],
                            effect=effect,
                            start=start + offset,
                            duration=min(entry.duration, shot["duration"] - offset),
                            seed=seed,
                        )
                    )
                    break
            start += shot["duration"]
        if len(cues) > 120:
            raise ValueError("Too many sound cues")
        return cues

    def render(self, cues, duration, path, check):
        if not math.isfinite(duration) or not 0 < duration <= 600:
            raise ValueError("Sound effect track must be at most 600 seconds")
        if len(cues) > 120 or len({c.shot_id for c in cues}) != len(cues):
            raise ValueError("Duplicate or excessive sound cues")
        if any(
            c.start + c.duration > duration + 1e-6 or c.duration > LIBRARY[c.effect].duration for c in cues
        ):
            raise ValueError("Sound cue extends outside its track or library effect")
        frames = round(duration * RATE)
        temporary = path.with_suffix(".partial.wav")
        with wave.open(str(temporary), "wb") as wav:
            wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            for first in range(0, frames, RATE):
                check()
                count = min(RATE, frames - first)
                values = [0.0] * count
                for cue in cues:
                    begin, end = round(cue.start * RATE), round((cue.start + cue.duration) * RATE)
                    for index in range(max(first, begin), min(first + count, end)):
                        t = (index - begin) / RATE
                        values[index - first] += cue.gain * self._sample(cue, t)
                wav.writeframes(b"".join(struct.pack("<h", round(max(-1, min(1, v)) * 8000)) for v in values))
        check()
        os.replace(temporary, path)

    @staticmethod
    def _sample(cue, t):
        envelope = math.sin(math.pi * t / cue.duration) ** 2
        if cue.effect == "signal":
            return envelope * (0.6 * math.sin(2 * math.pi * 660 * t) + 0.3 * math.sin(2 * math.pi * 880 * t))
        # Stateless deterministic noise; no full-track buffer or random external recording.
        value = (int(t * RATE) + cue.seed) & 0xFFFFFFFF
        value ^= value >> 16
        value = (value * 0x7FEB352D) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 0x846CA68B) & 0xFFFFFFFF
        value ^= value >> 16
        noise = value / 2**31 - 1
        if cue.effect == "door":
            return (
                envelope
                * math.exp(-t * 7)
                * (0.7 * math.sin(2 * math.pi * (85 * t + 40 * t * t)) + 0.3 * noise)
            )
        local = t - 0.05 if t < 0.4 else t - 0.45
        if not 0 <= local < 0.2:
            return 0
        return (
            envelope
            * math.sin(math.pi * local / 0.2) ** 2
            * (0.7 * math.sin(2 * math.pi * 75 * local) + 0.3 * noise)
        )
