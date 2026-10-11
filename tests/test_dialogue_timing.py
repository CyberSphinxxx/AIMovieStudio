import time
import wave

import pytest

from studio import media
from studio.worker import Worker
from studio.story import DemoStory
from studio.backup import create_backup, restore_backup
from tests.test_pipeline import produce_until


def test_real_windows_overflow_stops_before_visual_generation(store, spec, monkeypatch):
    original = DemoStory.script

    def long_line(self, project, number):
        script = original(self, project, number)
        script.shots[0].narration = (
            "The keeper carefully follows the distant signal through the abandoned station, "
            "remembering every traveler who once trusted this light, while the guide waits "
            "beside the locked chamber and wonders whether the compass can reveal the truth "
            "before the final ship disappears beyond the dark and silent sea."
        )
        return script

    monkeypatch.setattr(DemoStory, "script", long_line)
    pid, _ = store.create(spec)
    store.enqueue(pid)
    worker = Worker(store)
    worker.start()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            project = store.get(pid)
            if project["jobs"][0]["state"] == "FAILED":
                break
            time.sleep(0.1)
        else:
            pytest.fail("Overflowing real Windows speech did not fail within 20 seconds")
        assert "DIALOGUE_TOO_LONG" in project["jobs"][0]["error"]
        audio = next(s for s in project["jobs"][0]["steps"] if s["stage"] == "AUDIO")
        assert audio["state"] == "FAILED"
        assert all(
            s["state"] == "READY"
            for s in project["jobs"][0]["steps"]
            if s["stage"] in {"REFERENCE", "FRAME", "CLIP", "EXPORT"}
        )
        assert project["assets"] == [] and project["canon"] == []
        directory = worker.directory({**audio, "project_id": pid, "job_id": project["jobs"][0]["id"]})
        with wave.open(str(directory / "voice-1.wav")) as voice:
            assert voice.getnframes() / voice.getframerate() > spec.target_seconds
        assert not (directory / "segment-1.wav").exists()
        assert not (directory / "soundtrack.wav").exists()
    finally:
        worker.close()


def test_small_tempo_adjustment_records_measured_voice_and_keeps_all_samples(tmp_path, monkeypatch):
    # Explicit development fixture with known-duration audio; actual Windows overflow is above.
    def measured_voice(text, voice, output, check):
        media.ambience(output, 4.9)
        return 4.9

    monkeypatch.setattr(media, "speech", measured_voice)
    script = {"shots": [{"number": 1, "duration": 5, "narration": "Short line.", "speaker_id": "keeper"}]}
    plan = {"characters": [{"id": "keeper", "voice": "default"}]}
    output = tmp_path / "soundtrack.wav"
    timeline = media.soundtrack(script, plan, output, tmp_path, True, lambda: None)
    assert timeline[0]["raw_duration"] == 4.9
    assert 1 < timeline[0]["tempo"] <= 1.15
    assert timeline[0]["end"] == 4.75
    with wave.open(str(output)) as soundtrack:
        assert soundtrack.getnframes() / soundtrack.getframerate() == pytest.approx(5, abs=0.02)
    with wave.open(str(tmp_path / "voice-1.wav")) as original:
        assert original.getnframes() / original.getframerate() == pytest.approx(4.9)


@pytest.mark.parametrize("skip_first", [False, True])
def test_real_voice_and_ambience_stems_survive_portable_backup(
    store, spec, tmp_path, monkeypatch, skip_first
):
    voice_role = "voice-1"
    if skip_first:
        spec.target_seconds = 10
        voice_role = "voice-2"
        original = DemoStory.script

        def silent_first(self, project, number):
            script = original(self, project, number)
            script.shots[0].narration = ""
            return script

        monkeypatch.setattr(DemoStory, "script", silent_first)
    pid, _ = store.create(spec)
    store.enqueue(pid)
    project = produce_until(store, Worker(store), pid)
    stems = [a for a in project["assets"] if a["role"] in {voice_role, "dialogue", "ambience"}]
    assert {a["role"] for a in stems} == {voice_role, "dialogue", "ambience"}
    voice = next(a for a in stems if a["role"] == voice_role)
    assert voice["metadata"]["text"] == (
        "The light showed us a way." if skip_first else "Every journey begins with a question."
    )
    assert voice["metadata"]["shot_number"] == (2 if skip_first else 1)
    assert 1 <= voice["metadata"]["tempo"] <= 1.15
    soundtrack = next(a for a in project["assets"] if a["role"] == "soundtrack")
    assert set(soundtrack["metadata"]["parent_asset_ids"]) == {a["id"] for a in stems}
    archive = create_backup(store, tmp_path / "voices.zip")
    restored = restore_backup(archive, tmp_path / "restored")
    for stem in stems:
        path, asset = restored.asset_path(stem["id"])
        assert asset["sha256"] == stem["sha256"]
        with wave.open(str(path)) as wav:
            assert wav.getnframes() > 0
