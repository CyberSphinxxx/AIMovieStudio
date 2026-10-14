"""Original synthesis/media checks; movie visuals here are labeled demo fixtures."""

import array
import json
import wave

import pytest
from fastapi.testclient import TestClient

from studio import media
from studio.api import create_app
from studio.backup import create_backup, restore_backup
from studio.sound_effects import ProceduralSound, SoundCue, VERSION, RATE
from studio.storage import Store, atomic_json, digest
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


def shots(actions):
    return [
        {"id": f"shot-{i}", "number": i + 1, "duration": 1, "action": action}
        for i, action in enumerate(actions)
    ]


def pcm(path):
    with wave.open(str(path)) as wav:
        return wav.getframerate(), array.array("h", wav.readframes(wav.getnframes()))


def test_cues_match_explicit_actions_not_ambiguous_or_negative_mentions():
    provider = ProceduralSound()
    cues = provider.cues(
        shots(
            [
                "The radio beeps.",
                "She opens the door.",
                "He walks home.",
                "A silent door opens.",
                "The door does not open.",
                "A letter contains a signal.",
                "She never runs.",
            ]
        )
    )
    assert [c.effect for c in cues] == ["signal", "door", "footsteps"]
    assert [c.shot_number for c in cues] == [1, 2, 3]
    assert cues == provider.cues(shots(["The radio beeps.", "She opens the door.", "He walks home."]))
    assert all(c.start + c.duration <= c.shot_number for c in cues)


def test_pcm_has_exact_timing_silent_gaps_bounded_levels_and_reproducible_seed(tmp_path):
    provider = ProceduralSound()
    cues = provider.cues(
        shots(["The radio beeps.", "She opens the door.", "He walks home.", "She studies the map."])
    )
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    provider.render(cues, 4, first, lambda: None)
    provider.render(cues, 4, second, lambda: None)
    rate, values = pcm(first)
    assert rate == RATE and len(values) == RATE * 4
    assert digest(first) == digest(second)
    assert max(map(abs, values)) < 8000 and max(map(abs, values)) > 1000
    assert not any(values[: round(RATE * cues[0].start)])
    assert not any(values[3 * RATE :])
    probe = media.probe(first)
    assert probe["streams"][0]["codec_name"] == "pcm_s16le"
    assert float(probe["format"]["duration"]) == pytest.approx(4)


@pytest.mark.parametrize("fault", ["duplicate", "outside", "too_long"])
def test_invalid_cues_rejected_before_writing(tmp_path, fault):
    cue = SoundCue(shot_id="shot", shot_number=1, effect="signal", start=0, duration=0.6, seed=1)
    cues, duration = [cue], 1
    if fault == "duplicate":
        cues.append(cue)
    elif fault == "outside":
        cue.start = 0.5
    else:
        duration = 601
    with pytest.raises(ValueError):
        ProceduralSound().render(cues, duration, tmp_path / "effects.wav", lambda: None)
    assert list(tmp_path.iterdir()) == []


def test_interruption_does_not_replace_original_and_retry_is_deterministic(tmp_path):
    path = tmp_path / "effects.wav"
    path.write_bytes(b"original")
    checks = 0

    def interrupted():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise media.Interrupted("fixture pause")

    cues = ProceduralSound().cues(shots(["The alarm rings.", "She walks home."]))
    with pytest.raises(media.Interrupted):
        ProceduralSound().render(cues, 2, path, interrupted)
    assert path.read_bytes() == b"original"
    ProceduralSound().render(cues, 2, path, lambda: None)
    expected = tmp_path / "expected.wav"
    ProceduralSound().render(cues, 2, expected, lambda: None)
    assert digest(path) == digest(expected)


@pytest.mark.parametrize("enabled,legacy", [(True, False), (False, False), (True, True)])
def test_frozen_sound_settings_audio_receipt_and_portable_stem(store, spec, tmp_path, enabled, legacy):
    spec.kind, spec.target_seconds = "drama", 20  # Demo fourth shot explicitly opens a door.
    pid, _ = store.create(spec)
    set_silent(store)
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('sound_effects',?)", (json.dumps(enabled),))
    jid = store.enqueue(pid)
    with store.connect() as db:
        if legacy:
            row = db.execute("SELECT config FROM jobs WHERE id=?", (jid,)).fetchone()
            config = json.loads(row["config"])
            config.pop("sound_effects")
            db.execute("UPDATE jobs SET config=? WHERE id=?", (json.dumps(config), jid))
        db.execute("INSERT OR REPLACE INTO settings VALUES('sound_effects',?)", (json.dumps(not enabled),))
    worker = Worker(store)
    produce_until(store, worker, pid, "SCRIPT", 1)
    step = worker.claim()
    assert step["stage"] == "AUDIO"
    output = worker.execute(step)
    atomic_json(worker.directory(step) / "receipt.json", output)
    Worker(Store(store.root)).recover()
    result = store.get(pid)
    effects = [a for a in result["assets"] if a["role"] == "sound-effects"]
    assert bool(effects) == (enabled and not legacy)
    soundtrack = next(a for a in result["assets"] if a["role"] == "soundtrack")
    assert not result["canon"] and not result["assets"][-1]["metadata"]["is_mock"]
    assert float(media.probe(store.asset_path(soundtrack["id"])[0])["format"]["duration"]) == pytest.approx(
        20, abs=0.02
    )
    if effects:
        effect = effects[0]
        assert effect["metadata"]["provider"] == VERSION
        assert "no imported recording" in effect["metadata"]["license"]
        assert effect["metadata"]["cues"][0]["shot_number"] == 4
        assert effect["id"] in soundtrack["metadata"]["parent_asset_ids"]
        archive = create_backup(store, tmp_path / "effects.zip")
        restored = restore_backup(archive, tmp_path / "effects-restored")
        assert digest(restored.asset_path(effect["id"])[0]) == effect["sha256"]
        worker.verify(output)
        store.asset_path(effect["id"])[0].write_bytes(b"corrupted")
        with pytest.raises(RuntimeError, match="checksum"):
            worker.verify(output)


def test_settings_api_defaults_freeze_new_job_option(tmp_path, spec):
    with TestClient(create_app(tmp_path, run_worker=False)) as client:
        assert client.get("/api/settings").json()["sound_effects"] is True
        assert client.patch("/api/settings", json={"sound_effects": False}).status_code == 200
        project = client.post("/api/projects", json=spec.model_dump()).json()
        assert json.loads(project["jobs"][0]["config"])["sound_effects"] is False


def test_retake_keeps_effects_and_audio_when_new_movie_defaults_change(store, spec):
    from studio.shot_revisions import enqueue_retake, latest_movie
    from tests.test_shot_revisions import request_for, shot_id

    spec.kind, spec.target_seconds = "drama", 20
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    original = produce_until(store, Worker(store), pid)
    effect = next(a for a in original["assets"] if a["role"] == "sound-effects")
    audio = next(a for a in original["assets"] if a["role"] == "soundtrack")
    assert latest_movie(original, 1)["metadata"]["sound_effects_present"]
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('sound_effects','false')")
    enqueue_retake(store, pid, 1, shot_id(original), request_for(original))
    result = produce_until(store, Worker(store), pid)
    movie = latest_movie(result, 1)
    assert movie["metadata"]["sound_effects_present"]
    assert audio["id"] in movie["metadata"]["parent_asset_ids"]
    assert [a for a in result["assets"] if a["role"] == "sound-effects"] == [effect]
    assert digest(store.asset_path(effect["id"])[0]) == effect["sha256"]
    assert digest(store.asset_path(audio["id"])[0]) == audio["sha256"]
    assert result["canon"] == original["canon"]
    media.validate_video(store.asset_path(movie["id"])[0], (360, 640), 20, audio=True)


def test_effects_are_ducked_under_measured_dialogue(tmp_path, monkeypatch):
    # Known waveform voice fixture isolates mixing; actual Windows speech tested elsewhere.
    import math
    import struct

    def speech(text, voice, path, check):
        with wave.open(str(path), "wb") as wav:
            wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            wav.writeframes(
                b"".join(
                    struct.pack("<h", round(12000 * math.sin(2 * math.pi * 200 * i / RATE)))
                    for i in range(RATE * 2)
                )
            )
        return 2

    monkeypatch.setattr(media, "speech", speech)
    cue = SoundCue(shot_id="shot", shot_number=1, effect="signal", start=0.5, duration=0.6, seed=1)
    effect = tmp_path / "effect.wav"
    ProceduralSound().render([cue], 5, effect, lambda: None)
    script = {"shots": [{"number": 1, "duration": 5, "narration": "Short line.", "speaker_id": "keeper"}]}
    plan = {"characters": [{"id": "keeper", "voice": "default"}]}
    base, mixed = tmp_path / "base.wav", tmp_path / "mixed.wav"
    media.soundtrack(script, plan, base, tmp_path, True, lambda: None)
    timeline = media.soundtrack(script, plan, mixed, tmp_path, True, lambda: None, effects=effect)
    rate, before = pcm(base)
    _, after = pcm(mixed)
    assert len(before) == len(after) == rate * 5
    assert timeline[0]["end"] == 2
    difference = [after[i] - before[i] for i in range(int(0.6 * rate), int(1 * rate))]
    assert max(map(abs, after)) < 32767
    assert 0 < max(map(abs, difference)) < 1500
