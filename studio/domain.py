from __future__ import annotations

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def stable(project: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"movie-studio:{project}:{key}"))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(StrictModel):
    idea: str = Field(min_length=8, max_length=8000)
    kind: Literal["clip", "drama", "film", "series"] = "clip"
    orientation: Literal["portrait", "landscape", "square"] = "portrait"
    target_seconds: int = Field(default=30, ge=5, le=600)
    episodes: int = Field(default=6, ge=1, le=24)
    language: Literal["English"] = "English"
    style: str = Field(default="Cinematic realism", max_length=100)
    backend: Literal["demo", "local"] = "demo"
    prewrite_season: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100)

    @field_validator("idea")
    @classmethod
    def clean_idea(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 8 or "\x00" in value:
            raise ValueError("Describe your movie in at least eight characters.")
        return value

    @model_validator(mode="after")
    def mode_limit(self):
        if self.kind == "clip" and self.target_seconds > 30:
            raise ValueError("Clips are 5–30 seconds. Choose drama or film for a longer story.")
        if self.kind != "series":
            self.episodes = 1
        return self


class Character(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    appearance: str = Field(min_length=8, max_length=1200)
    goal: str = Field(min_length=3, max_length=500)
    voice: str = "default"


class Location(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=8, max_length=1200)


class EpisodeOutline(StrictModel):
    number: int = Field(ge=1, le=24)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=10, max_length=1500)
    outcome: str = Field(min_length=5, max_length=1000)


class SeasonPlan(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    logline: str = Field(min_length=10, max_length=1500)
    ending: str = Field(min_length=10, max_length=1500)
    world_rules: list[str] = Field(min_length=1, max_length=20)
    characters: list[Character] = Field(min_length=1, max_length=8)
    locations: list[Location] = Field(min_length=1, max_length=8)
    episodes: list[EpisodeOutline] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def identities(self):
        ids = [c.id for c in self.characters] + [p.id for p in self.locations]
        if len(ids) != len(set(ids)):
            raise ValueError("Character and location IDs must be unique.")
        if [e.number for e in self.episodes] != list(range(1, len(self.episodes) + 1)):
            raise ValueError("Episode numbers must be contiguous and ordered.")
        return self


class Shot(StrictModel):
    id: str
    number: int = Field(ge=1)
    duration: float = Field(ge=1, le=15)
    location_id: str
    character_ids: list[str] = Field(min_length=1, max_length=8)
    action: str = Field(min_length=5, max_length=1500)
    camera: str = Field(min_length=3, max_length=400)
    narration: str = Field(max_length=600)
    speaker_id: str
    transition: Literal["cut", "fade"] = "cut"


class EpisodeScript(StrictModel):
    number: int = Field(ge=1, le=24)
    screenplay: str = Field(min_length=20, max_length=50000)
    shots: list[Shot] = Field(min_length=1, max_length=120)


class CanonEvent(StrictModel):
    entity_id: str
    episode: int = Field(ge=1)
    field: Literal["alive", "location", "prop_owner", "knowledge", "outcome"]
    value: str
    reason: str = Field(min_length=3)


def validate_script(script: EpisodeScript, plan: SeasonPlan, seconds: int) -> None:
    characters = {c.id for c in plan.characters}
    places = {loc.id for loc in plan.locations}
    if len({s.id for s in script.shots}) != len(script.shots):
        raise ValueError("Duplicate shot IDs")
    if [s.number for s in script.shots] != list(range(1, len(script.shots) + 1)):
        raise ValueError("Shot numbers must be ordered")
    if abs(sum(s.duration for s in script.shots) - seconds) > 0.1:
        raise ValueError("Shot durations must match the requested runtime")
    for shot in script.shots:
        if not set(shot.character_ids) <= characters or shot.speaker_id not in characters:
            raise ValueError("Unknown character or speaker")
        if shot.location_id not in places:
            raise ValueError("Unknown location")


def continuity_errors(script: EpisodeScript, events: list[dict]) -> list[str]:
    alive: dict[str, str] = {}
    for event in sorted(events, key=lambda e: e["episode"]):
        if event["episode"] < script.number and event["field"] == "alive":
            alive[event["entity_id"]] = event["value"]
    return [
        f"Shot {s.number}: {c} is dead; add an explicit revision/flashback before production."
        for s in script.shots
        for c in s.character_ids
        if alive.get(c) == "false"
    ]
