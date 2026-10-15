"""Real PCM/FFmpeg measurements; fixture visuals do not certify AI generation."""

import json
import math
import struct
import wave

import pytest

from studio import media
from studio.loudness import balance, measure, parse_measurement
from studio.storage import atomic_json, digest, Store
from studio.worker import Worker
from studio.backup import create_backup, restore_backup
from tests.test_pipeline import produce_until, set_silent


def tone(path, amplitude, seconds=5, impulse=False):
    rate = 48000
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        for second in range(seconds):
            values = []
            for i in range(rate):
                value = round(amplitude * math.sin(2 * math.pi * 400 * i / rate))
                if impulse and second == 2 and i == 100:
                    value = 32760
                values.append(struct.pack("<h", value))
            wav.writeframes(b"".join(values))


@pytest.mark.parametrize("amplitude", [2500, 20000])
def test_measured_spoken_target_preserves_original_timing_and_peaks(tmp_path, amplitude):
    source, output = tmp_path / "original with spaces.wav", tmp_path / "balanced.wav"
    tone(source, amplitude)
    original = digest(source)
    report = balance(source, output, True, lambda: None)
    measured = measure(output)
    assert report["status"] == "target_reached"
    assert measured["integrated_lufs"] == pytest.approx(-16, abs=0.3)
    assert measured["true_peak_dbtp"] <= -1.9
    assert digest(source) == original
    with wave.open(str(output)) as wav:
        assert wav.getnframes() == 5 * 48000 and wav.getframerate() == 48000
    json.dumps(report, allow_nan=False)


def test_quiet_atmosphere_is_gain_limited_and_silence_is_bit_identical(tmp_path):
    quiet, silent = tmp_path / "quiet.wav", tmp_path / "silent.wav"
    tone(quiet, 50)
    tone(silent, 0)
    report = balance(quiet, tmp_path / "quiet-balanced.wav", False, lambda: None)
    assert report["applied_gain_db"] <= 6
    assert report["status"] == "gain_limited"
    assert report["output"]["integrated_lufs"] < -26
    unchanged = tmp_path / "silence-copy.wav"
    report = balance(silent, unchanged, True, lambda: None)
    assert report["status"] == "below_measurement_gate"
    assert report["output"]["integrated_lufs"] is None
    assert digest(silent) == digest(unchanged)
    json.dumps(report, allow_nan=False)


def test_isolated_loud_peak_limits_gain_instead_of_forcing_target(tmp_path):
    source, output = tmp_path / "peaky.wav", tmp_path / "balanced.wav"
    tone(source, 600, impulse=True)
    report = balance(source, output, True, lambda: None)
    assert report["status"] == "peak_limited"
    assert report["applied_gain_db"] < 0
    assert report["output"]["true_peak_dbtp"] <= -1.9
    assert report["output"]["integrated_lufs"] < -16


@pytest.mark.parametrize(
    "raw",
    [
        b"no JSON",
        b"[]",
        b'{"input_i":"NaN","input_tp":"-3","input_lra":"0"}',
        b'{"input_i":"-20","input_tp":"inf","input_lra":"0"}',
        b'{"input_i":"-20;payload","input_tp":"-3","input_lra":"0"}',
    ],
)
def test_invalid_measurement_is_not_passed_to_filter(raw):
    with pytest.raises(RuntimeError, match="BAD_AUDIO"):
        parse_measurement(raw)


def test_cancel_during_processing_keeps_both_original_and_previous_output(tmp_path):
    source, output = tmp_path / "source.wav", tmp_path / "out.wav"
    tone(source, 2500)
    output.write_bytes(b"previous original")
    old_hash = digest(source)

    def stop():
        raise media.Interrupted("fixture cancellation")

    with pytest.raises(media.Interrupted):
        balance(source, output, True, stop)
    assert output.read_bytes() == b"previous original" and digest(source) == old_hash


@pytest.mark.parametrize("enabled,legacy", [(True, False), (False, False), (True, True)])
def test_frozen_balancing_receipt_backup_and_source_mix(store, spec, tmp_path, enabled, legacy):
    pid, _ = store.create(spec)
    set_silent(store)
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('balanced_audio',?)", (json.dumps(enabled),))
    jid = store.enqueue(pid)
    with store.connect() as db:
        if legacy:
            config = json.loads(db.execute("SELECT config FROM jobs WHERE id=?", (jid,)).fetchone()["config"])
            config.pop("balanced_audio")
            db.execute("UPDATE jobs SET config=? WHERE id=?", (json.dumps(config), jid))
        db.execute("INSERT OR REPLACE INTO settings VALUES('balanced_audio',?)", (json.dumps(not enabled),))
    worker = Worker(store)
    produce_until(store, worker, pid, "SCRIPT", 1)
    step = worker.claim()
    output = worker.execute(step)
    atomic_json(worker.directory(step) / "receipt.json", output)
    Worker(Store(store.root)).recover()
    project = store.get(pid)
    soundtrack = next(a for a in project["assets"] if a["role"] == "soundtrack")
    premixes = [a for a in project["assets"] if a["role"] == "unbalanced-mix"]
    assert bool(premixes) == (enabled and not legacy)
    assert bool(soundtrack["metadata"]["loudness"]) == bool(premixes)
    if premixes:
        assert premixes[0]["id"] in soundtrack["metadata"]["parent_asset_ids"]
        archive = create_backup(store, tmp_path / "balanced.zip")
        restored = restore_backup(archive, tmp_path / "restored")
        assert digest(restored.asset_path(premixes[0]["id"])[0]) == premixes[0]["sha256"]
    assert not project["canon"]


def test_normalized_aac_export_is_playable_and_carries_actual_pcm_measurements(store, spec):
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    project = produce_until(store, Worker(store), pid)
    movie = next(a for a in project["assets"] if a["role"] == "export")
    path = store.asset_path(movie["id"])[0]
    media.validate_video(path, (360, 640), 5, audio=True)
    encoded = measure(path)
    assert encoded["true_peak_dbtp"] < 0
    assert movie["metadata"]["loudness"]["scope"].startswith("PCM soundtrack")
    assert movie["metadata"]["is_mock"]  # Explicit development visuals.
