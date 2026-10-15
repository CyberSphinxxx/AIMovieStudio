import json

import pytest
from PIL import Image, ImageDraw

from studio import media
from studio.storage import digest
from studio.worker import Worker
from tests.test_pipeline import produce_until, set_silent


@pytest.mark.parametrize("size", [(360, 640), (640, 360), (480, 480), (512, 512)])
@pytest.mark.parametrize("style", ["paragraph", "unbroken", "natural"])
def test_drawn_letters_fit_visible_zoom_area_for_long_titles_and_captions(tmp_path, size, style):
    title = (
        "W" * 500
        if style == "unbroken"
        else "A very long camera description with a distant lighthouse and harbor " * 12
    )
    caption = (
        "M" * 3000
        if style == "unbroken"
        else "A keeper follows the signal through a quiet harbor beside the old station. " * 40
    )
    if style == "natural":
        title = "Wide establishing shot across the quiet harbor beside an old lighthouse"
        caption = (
            "Cinematic realism. The keeper studies a signal at the station while the distant ship turns toward the shore. Preserve the warm light and quiet harbor. "
            * 2
        )
    output = tmp_path / "demo.png"
    media.demo_image(output, size, title, caption, 42)
    with Image.open(output) as image:
        pixels = image.load()
        lettering = [
            (x, y)
            for y in range(round(size[1] * 0.71), size[1])
            for x in range(size[0])
            if all(channel >= minimum for channel, minimum in zip(pixels[x, y], (200, 200, 190)))
        ]
        caption_pixels = [
            (x, y)
            for y in range(size[1])
            for x in range(size[0])
            if pixels[x, y][0] >= 180 and 1 <= pixels[x, y][0] - pixels[x, y][1] <= 5
        ]
    assert lettering
    # Measure rendered pixels, independent of line-wrapping implementation.
    assert max(x for x, _ in lettering) < int(size[0] / 1.06) - 12
    assert max(y for _, y in lettering) < int(size[1] / 1.06) - 12
    assert caption_pixels, "Caption was omitted"


def test_preview_shortening_is_explicit_and_original_text_is_untouched():
    original = "W" * 3000
    draw = ImageDraw.Draw(Image.new("RGB", (640, 360)))
    preview = media.preview_text(draw, original, media.font(12), 400, 2)
    assert preview.endswith("…") and len(preview.splitlines()) == 2
    assert original == "W" * 3000


def test_new_layout_records_provenance_without_rewriting_saved_assets_or_story(store, spec):
    # Explicit long-preview fixture; the full style stays in saved prompt metadata.
    spec.style = "Cinematic realism " + "warm light " * 7 + "dusk"
    pid, _ = store.create(spec)
    set_silent(store)
    store.enqueue(pid)
    worker = Worker(store)
    partial = produce_until(store, worker, pid, "REFERENCE", 1)
    reference = next(a for a in partial["assets"] if a["role"] == "reference")
    sha = reference["sha256"]
    assert reference["metadata"]["demo_layout_version"] == "zoom-safe-v2"
    # An already published legacy asset keeps its original metadata/hash.
    legacy = dict(reference["metadata"])
    legacy.pop("demo_layout_version")
    with store.connect() as db:
        db.execute("UPDATE assets SET metadata=? WHERE id=?", (json.dumps(legacy), reference["id"]))
    final = produce_until(store, worker, pid)
    old = next(a for a in final["assets"] if a["id"] == reference["id"])
    assert old["sha256"] == sha == digest(store.asset_path(old["id"])[0])
    assert "demo_layout_version" not in old["metadata"]
    frame = next(a for a in final["assets"] if a["role"] == "keyframe")
    assert frame["metadata"]["demo_layout_version"] == "zoom-safe-v2"
    assert len(frame["metadata"]["prompt"]) > 160
    assert (
        final["plan"] == partial["plan"]
        and final["episodes"][0]["script"] == partial["episodes"][0]["script"]
    )
    assert final["status"] == "COMPLETED" and len(final["canon"]) == 1
