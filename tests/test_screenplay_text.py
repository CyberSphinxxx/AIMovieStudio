import json

import httpx
import pytest

from studio.domain import validate_script
from studio.screenplay_text import validate_shot_headings
from studio.script_batches import validate_section
from studio.story import DemoStory, OllamaStory


@pytest.mark.parametrize(
    "text",
    [
        "[Shot 1: 5s]\n[Shot 9: 5s]",
        "# SHOT 9 — Extra scene",
        "**Shot 9**: Extra scene",
        "shot 9\n",
        "[9] [actor-id] A scene.",
        "[9]\n",
    ],
)
def test_outside_headings_are_rejected(text):
    with pytest.raises(ValueError, match="outside the requested shot range"):
        validate_shot_headings(text, range(1, 5))


@pytest.mark.parametrize(
    "text,error", [("[Shot 1]\n[Shot 1]", "repeats"), ("[Shot 2]\n[Shot 1]", "out of order")]
)
def test_duplicate_or_backwards_headings_are_rejected(text, error):
    with pytest.raises(ValueError, match=error):
        validate_shot_headings(text, (1, 2))


def test_global_section_numbers_and_normal_scene_headings_remain_valid():
    for text in [
        "[Shot 5:5s]\n[Shot 8:5s]",
        "SCENE 1 — INT. THE KEEP\nMara recalls shot 1 from a film.",
        "A single unnumbered scene unfolds.",
    ]:
        assert validate_shot_headings(text, range(5, 9)) == text


def test_provider_repair_catches_numbered_prose_before_checkpoint(store, spec):
    spec.target_seconds = 20
    pid, _ = store.create(spec)
    project = store.get(pid)
    plan = DemoStory().plan(project)
    project["plan"] = plan.model_dump()
    valid = DemoStory().script_batch(project, 1, 0, 4, [])
    for shot in valid.shots:
        shot.camera = "Close-up"
    valid.screenplay = "[Shot 1:5s]\n" + valid.screenplay
    bad = valid.model_copy(
        update={"screenplay": valid.screenplay + "\n[Shot 9:5s]\nInvented future material."}
    )
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        content = bad.model_dump_json() if len(calls) == 1 else valid.model_dump_json()
        return httpx.Response(200, json={"message": {"content": content}})

    provider = OllamaStory("TEST-CONTRACT-ONLY", transport=httpx.MockTransport(handler))
    actual = provider.script_batch(project, 1, 0, 4, [])
    assert len(calls) == 2
    assert "outside the requested shot range" in calls[1]["messages"][-1]["content"]
    validate_section(actual, plan, 0, 4, 5)


def test_second_section_keeps_global_numbers_and_cached_bad_whole_script_is_rejected(store, spec):
    spec.target_seconds = 40
    pid, _ = store.create(spec)
    project = store.get(pid)
    plan = DemoStory().plan(project)
    project["plan"] = plan.model_dump()
    section = DemoStory().script_batch(project, 1, 4, 4, [])
    section.screenplay = "[Shot 5:5s]\n" + section.screenplay + "\n[Shot 8:5s]\n"
    validate_section(section, plan, 4, 4, 5)
    script = DemoStory().script(project, 1)
    script.screenplay += "\n[Shot 14:5s]\nA hallucinated additional shot."
    with pytest.raises(ValueError, match="outside the requested shot range"):
        validate_script(script, plan, 40)
