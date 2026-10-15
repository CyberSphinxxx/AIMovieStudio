from __future__ import annotations

from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from studio.screenplay_text import validate_shot_headings


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
    review_story: bool = False
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
    initial_knowledge: list[Annotated[str, Field(min_length=3, max_length=500)]] = Field(
        default_factory=list, max_length=24
    )


class Location(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=8, max_length=1200)


class Prop(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=8, max_length=1200)
    owner_id: str = ""


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
    props: list[Prop] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def identities(self):
        ids = [c.id for c in self.characters] + [p.id for p in self.locations] + [p.id for p in self.props]
        if len(ids) != len(set(ids)):
            raise ValueError("Character, location and prop IDs must be unique.")
        if any(p.owner_id and p.owner_id not in {c.id for c in self.characters} for p in self.props):
            raise ValueError("Unknown initial prop owner")
        if [e.number for e in self.episodes] != list(range(1, len(self.episodes) + 1)):
            raise ValueError("Episode numbers must be contiguous and ordered.")
        return self


class KnowledgeUse(StrictModel):
    character_id: str
    fact: str = Field(min_length=3, max_length=500)


class PropUse(StrictModel):
    prop_id: str
    character_id: str


class CanonChange(StrictModel):
    after_shot: int = Field(ge=0, le=120)
    entity_id: str
    field: Literal["alive", "location", "prop_owner", "knowledge"]
    before_value: str = Field(max_length=500)
    value: str = Field(max_length=500)
    reason: str = Field(min_length=8, max_length=500)


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
    required_props: list[PropUse] = Field(default_factory=list, max_length=8)
    required_knowledge: list[KnowledgeUse] = Field(default_factory=list, max_length=8)
    flashback_episode: int | None = Field(default=None, ge=1, le=24)
    continuity_note: str = Field(default="", max_length=500)

    @field_validator("character_ids")
    @classmethod
    def unique_cast_references(cls, value):
        return list(dict.fromkeys(value))


def shot_participants(shot: Shot) -> set[str]:
    """A silent shot's mandatory speaker slot is an ID, not an actor presence."""
    return set(shot.character_ids) | ({shot.speaker_id} if shot.narration.strip() else set())


class EpisodeScript(StrictModel):
    number: int = Field(ge=1, le=24)
    screenplay: str = Field(min_length=20, max_length=50000)
    shots: list[Shot] = Field(min_length=1, max_length=120)
    proposed_changes: list[CanonChange] = Field(default_factory=list, max_length=48)


class CanonEvent(StrictModel):
    entity_id: str
    episode: int = Field(ge=1)
    field: Literal["alive", "location", "prop_owner", "knowledge", "outcome"]
    value: str
    reason: str = Field(min_length=3)


def validate_script(
    script: EpisodeScript, plan: SeasonPlan, seconds: int, *, screenplay_numbers=None
) -> None:
    if len(script.screenplay.strip()) < max(80, len(script.shots) * 80):
        raise ValueError("Incomplete screenplay: provide scene action and spoken lines, not just a title")
    validate_shot_headings(
        script.screenplay,
        screenplay_numbers if screenplay_numbers is not None else [s.number for s in script.shots],
    )
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
        if not {p.prop_id for p in shot.required_props} <= {p.id for p in plan.props}:
            raise ValueError("Unknown required prop")
        if any(p.character_id not in shot.character_ids for p in shot.required_props):
            raise ValueError("Prop user must be present in the shot")
        if any(k.character_id not in shot_participants(shot) for k in shot.required_knowledge):
            raise ValueError("Knowledge assertion references a character outside the shot")
        if shot.flashback_episode is not None:
            if shot.flashback_episode >= script.number or len(shot.continuity_note.strip()) < 8:
                raise ValueError("Flashbacks need an earlier episode and explicit continuity explanation")
    for change in script.proposed_changes:
        if change.after_shot > len(script.shots):
            raise ValueError("Canon change references a missing shot")
        if change.after_shot and script.shots[change.after_shot - 1].flashback_episode is not None:
            raise ValueError("Flashback changes cannot alter present canon")
        validate_canon_value(plan, change.entity_id, change.field, change.value)
        if change.field == "alive" and change.before_value not in {"true", "false"}:
            raise ValueError("Alive before-state must be true or false")
        if change.field == "prop_owner" and change.before_value and change.before_value not in characters:
            raise ValueError("Unknown previous prop owner")
        if change.field == "location" and change.before_value and change.before_value not in places:
            raise ValueError("Unknown previous location")
        if change.field == "knowledge" and change.before_value not in {"unknown", "known"}:
            raise ValueError("Knowledge before-state must be unknown or known")


def validate_canon_value(plan: SeasonPlan, entity_id: str, field: str, value: str) -> None:
    characters, places, props = (
        {c.id for c in plan.characters},
        {p.id for p in plan.locations},
        {p.id for p in plan.props},
    )
    if field == "prop_owner":
        if entity_id not in props or (value and value not in characters):
            raise ValueError("Unknown prop or prop owner")
    elif field in {"alive", "location", "knowledge"}:
        if entity_id not in characters:
            raise ValueError("Unknown canon character")
        if field == "alive" and value not in {"true", "false"}:
            raise ValueError("Alive state must be true or false")
        if field == "location" and value not in places:
            raise ValueError("Unknown canon location")
        if field == "knowledge" and not 3 <= len(value) <= 500:
            raise ValueError("Knowledge fact must contain 3–500 characters")


def continuity_errors(script: EpisodeScript, events: list[dict], plan: SeasonPlan | None = None) -> list[str]:
    from studio.continuity import check_continuity

    return check_continuity(script, events, plan)
