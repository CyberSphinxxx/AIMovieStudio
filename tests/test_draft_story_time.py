"""Sparse story-time edits use an explicitly labeled demo library, no models."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.checkpoint_browser_smoke import fixture
from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.storage import Store


@pytest.fixture
def saved_time(tmp_path):
    sample = fixture(tmp_path / "story-time-library")
    store = Store(Path(sample["root"]))
    with TestClient(create_app(store.root, run_worker=False)) as client:
        yield store, sample["id"], client


def patch(client, project, **fields):
    return client.patch(
        f"/api/projects/{project['id']}/episodes/2/draft",
        json={
            "revision": project["revision"],
            "edits": [{"shot_id": project["episodes"][1]["script"]["shots"][2]["id"], **fields}],
        },
    )


@pytest.mark.parametrize("position", [None, 0, 2, 3])
def test_edit_story_moment_retains_identity_history_and_original_episode(saved_time, position):
    store, pid, client = saved_time
    before = store.get(pid)
    result = patch(
        client,
        before,
        flashback_after_shot=position,
        continuity_note="Remembering a different moment in the first episode.",
    )
    assert result.status_code == 200, result.text
    after = result.json()
    old = before["episodes"][1]["script"]
    new = after["episodes"][1]["script"]
    assert after["episodes"][0] == before["episodes"][0]
    assert after["assets"] == before["assets"] and not after["jobs"] and not after["canon"]
    assert new["shots"][2]["flashback_after_shot"] == position
    assert new["shots"][2]["flashback_episode"] == 1
    for source, edited in zip(old["shots"], new["shots"], strict=True):
        assert source["id"] == edited["id"] and source["duration"] == edited["duration"]
    assert after["revision"] == before["revision"] + 1
    with store.connect() as db:
        event = json.loads(db.execute("SELECT data FROM events WHERE kind='draft_revision'").fetchone()[0])
    assert event["original_script"] == old
    assert "flashback_after_shot" in event["edits"][0]
    assert event["edits"][0]["flashback_after_shot"] == position
    assert Store(store.root).get(pid)["episodes"][1]["script"] == new


def test_explicit_null_can_return_to_current_story_but_omission_preserves_moment(saved_time, tmp_path):
    store, pid, client = saved_time
    before = store.get(pid)
    first = patch(client, before, narration="I remember the door opening.")
    assert first.status_code == 200, first.text
    kept = first.json()
    assert kept["episodes"][1]["script"]["shots"][2]["flashback_after_shot"] == 1
    result = patch(client, kept, flashback_episode=None, flashback_after_shot=None, continuity_note="")
    assert result.status_code == 200, result.text
    current = result.json()["episodes"][1]["script"]["shots"][2]
    assert current["flashback_episode"] is None and current["flashback_after_shot"] is None
    assert current["continuity_note"] == ""
    backup = create_backup(store, tmp_path / "story-time.zip")
    restored = restore_backup(backup, tmp_path / "restored")
    reopened = restored.get(pid)
    assert reopened["episodes"][1]["script"]["shots"][2] == current


@pytest.mark.parametrize(
    "fields",
    [
        {"flashback_after_shot": -1},
        {"flashback_after_shot": 4},
        {"flashback_after_shot": 1.5},
        {"flashback_after_shot": "1"},
        {"flashback_after_shot": True},
        {"flashback_episode": True},
        {"flashback_episode": 2},
        {"flashback_episode": 3},
        {"flashback_episode": None},
        {"continuity_note": "tiny"},
    ],
)
def test_invalid_time_edit_rolls_back_without_history_or_queue(saved_time, fields):
    store, pid, client = saved_time
    before = store.get(pid)
    result = patch(client, before, **fields)
    assert result.status_code in {409, 422}, result.text
    assert store.get(pid) == before
    with store.connect() as db:
        assert not db.execute("SELECT 1 FROM events WHERE kind='draft_revision'").fetchone()


def test_exact_time_cannot_reference_an_unreviewed_earlier_script(saved_time):
    store, pid, client = saved_time
    with store.connect() as db:
        db.execute("UPDATE episodes SET status='REVIEW_REQUIRED' WHERE project_id=? AND number=1", (pid,))
    before = store.get(pid)
    result = patch(client, before, flashback_after_shot=0)
    assert result.status_code == 409 and "checkpoint" in result.text.lower()
    assert store.get(pid) == before
