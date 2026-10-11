import json

import httpx
import pytest

from studio.domain import EpisodeScript, continuity_errors, validate_script
from studio.story import DemoStory, OllamaStory


def test_ten_episode_ending_and_pinned_ids(store, spec):
    spec.kind, spec.episodes = "series", 10
    pid, _ = store.create(spec)
    project = store.get(pid)
    provider = DemoStory()
    plan = provider.plan(project)
    assert len(plan.episodes) == 10
    assert "resolved" in plan.episodes[-1].outcome
    project["plan"] = plan.model_dump()
    script1 = provider.script(project, 1)
    project["canon"] = [{"episode": 1, "field": "outcome", "value": "Mara received the compass."}]
    script2 = provider.script(project, 2)
    assert "Mara received the compass" in script2.screenplay
    assert script1.shots[0].character_ids == script2.shots[0].character_ids
    validate_script(script1, plan, spec.target_seconds)
    events = [{"episode": 1, "field": "alive", "entity_id": plan.characters[0].id, "value": "false"}]
    assert continuity_errors(script2, events)
    assert not continuity_errors(script1, events)


def test_broken_references_and_duration(store, spec):
    pid, _ = store.create(spec)
    project = store.get(pid)
    provider = DemoStory()
    plan = provider.plan(project)
    project["plan"] = plan.model_dump()
    script = provider.script(project, 1)
    script.shots[0].speaker_id = "unknown"
    with pytest.raises(ValueError, match="Unknown character"):
        validate_script(script, plan, spec.target_seconds)
    with pytest.raises(ValueError, match="runtime"):
        validate_script(script, plan, 30)


def test_ollama_official_contract_and_repair(store, spec):
    pid, _ = store.create(spec)
    project = store.get(pid)
    plan = DemoStory().plan(project)
    calls = []

    def handler(request):
        data = json.loads(request.content)
        calls.append(data)
        content = "{}" if len(calls) == 1 else plan.model_dump_json()
        return httpx.Response(200, json={"message": {"content": content}})

    provider = OllamaStory("installed-model", transport=httpx.MockTransport(handler))
    actual = provider.plan(project)
    assert actual.ending == plan.ending
    assert len(calls) == 2
    assert calls[0]["format"]["type"] == "object"
    assert calls[0]["keep_alive"] == 0 and not calls[0]["stream"]
    assert "Repair" in calls[1]["messages"][-1]["content"]


def test_ollama_invalid_json_bounded():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"message": {"content": "not json"}})

    provider = OllamaStory("installed-model", transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="three attempts"):
        provider.generate(EpisodeScript, "test")
    assert len(calls) == 3
