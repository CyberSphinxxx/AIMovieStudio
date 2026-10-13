import ctypes
import os
import subprocess
import sys

import pytest

from studio.processes import owned_process


@pytest.mark.skipif(os.name != "nt", reason="Windows process ownership API")
def test_finished_leaf_does_not_fail_assignment_race_and_generic_process_stays_strict():
    process = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.wait(timeout=10) == 0
    with owned_process(process, completed_leaf=True):
        assert process.poll() == 0
    with pytest.raises(RuntimeError, match="PROCESS_CONTAINMENT_FAILED"):
        with owned_process(process):
            pytest.fail("Accepted an arbitrary process after failed containment")


@pytest.mark.skipif(os.name != "nt", reason="Windows process ownership API")
def test_live_leaf_assignment_denial_terminates_child(monkeypatch):
    original = ctypes.WinDLL

    class Function:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    class Kernel:
        def __init__(self):
            self.CreateJobObjectW = Function(lambda *_args: 1)
            self.SetInformationJobObject = Function(lambda *_args: 1)
            self.CloseHandle = Function(lambda *_args: 1)

            def denied(*_args):
                ctypes.set_last_error(5)
                return 0

            self.AssignProcessToJobObject = Function(denied)

    process = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW
    )
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name, **kwargs: Kernel() if name == "kernel32" else original(name, **kwargs)
    )
    try:
        with pytest.raises(RuntimeError, match="PROCESS_CONTAINMENT_FAILED"):
            with owned_process(process, completed_leaf=True):
                pytest.fail("Ran a live child without containment")
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
