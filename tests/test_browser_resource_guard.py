"""The demo UI harness must refuse a large suite before allocating children."""

import pytest

from scripts import checkpoint_browser_smoke as smoke


@pytest.mark.parametrize(
    "args,free,minimum",
    [
        (["--all"], 2.12, "3"),
        ([], 0.7, "0.75"),
        (["--movie-review"], 1.0, "1.25"),
        (["--story-branch"], 1.0, "1.25"),
    ],
)
def test_browser_scope_requires_headroom_before_creating_a_fixture(
    tmp_path, monkeypatch, args, free, minimum
):
    monkeypatch.setattr("sys.argv", ["browser-smoke", *args])
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(
        smoke,
        "memory_status",
        lambda: {"available": True, "total_gb": 15.19, "free_gb": free, "load_percent": 90},
    )
    monkeypatch.setattr(
        smoke, "fixture", lambda *a, **k: pytest.fail("Allocated fixture below its startup guard")
    )
    with pytest.raises(RuntimeError, match=f"Need {minimum} GiB"):
        smoke.main()
    assert not list(tmp_path.iterdir())


def test_unknown_memory_is_refused_before_ui_startup(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["browser-smoke", "--all"])
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "memory_status", lambda: {"available": False})
    with pytest.raises(RuntimeError, match="UI_TEST_RESOURCE_BUSY"):
        smoke.main()
    assert not list(tmp_path.iterdir())


def test_full_suite_and_single_timing_mode_cannot_be_mixed(monkeypatch):
    monkeypatch.setattr("sys.argv", ["browser-smoke", "--all", "--canon-timing"])
    monkeypatch.setattr(
        smoke, "memory_status", lambda: pytest.fail("Conflicting modes reached resource checks")
    )
    with pytest.raises(SystemExit) as error:
        smoke.main()
    assert error.value.code == 2
