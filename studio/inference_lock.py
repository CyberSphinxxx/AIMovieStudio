"""Cooperative per-user ownership of Studio's native model workloads.

The OS releases the byte lock on descriptor/process exit. The file stays present
so another copy cannot accidentally lock a different replacement file object.
Independently launched third-party model programs do not participate.
"""

from __future__ import annotations

import errno
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

_current_lease = ContextVar("studio_native_lease", default=None)


class _Lease:
    def __init__(self, handle):
        self.handle = handle
        self.users = 1
        self.mutex = threading.Lock()

    def retain(self):
        with self.mutex:
            if self.users == 0:
                raise RuntimeError("Native ownership has already ended")
            self.users += 1

    def release(self):
        with self.mutex:
            self.users -= 1
            if self.users:
                return
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()


def retain_current_inference():
    """Keep ownership until a background HTTP call actually exits after cancellation."""
    lease = _current_lease.get()
    if lease is not None:
        lease.retain()
    return lease


class InferenceBusy(RuntimeError):
    """Only raised when ownership fails before the protected inference begins."""

    def __init__(self):
        super().__init__("INFERENCE_BUSY: Another Studio process is using the local AI engine.")


def lock_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    else:
        base = Path.home() / ".local/state"
    return base / "AIMovieStudio/runtime/native-inference.lock"


@contextmanager
def native_inference(path: Path | None = None):
    """Fail fast on contention; an injectable path is for internal tests only."""
    target = path if path is not None else lock_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("a+b", buffering=0)
    except OSError as error:
        raise RuntimeError("INFERENCE_LOCK_UNAVAILABLE: Cannot open local AI ownership storage.") from error
    try:
        os.set_inheritable(handle.fileno(), False)
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise InferenceBusy() from error
            raise RuntimeError("INFERENCE_LOCK_UNAVAILABLE: Cannot acquire local AI ownership.") from error
    except BaseException:
        handle.close()
        raise
    lease = _Lease(handle)
    token = _current_lease.set(lease)
    try:
        yield
    finally:
        _current_lease.reset(token)
        lease.release()


def inference_busy() -> bool:
    try:
        with native_inference():
            return False
    except InferenceBusy:
        return True


def serialized_inference(function):
    @wraps(function)
    def protected(*args, **kwargs):
        with native_inference():
            return function(*args, **kwargs)

    return protected
