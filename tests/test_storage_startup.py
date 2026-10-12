import sqlite3
from types import SimpleNamespace
from contextlib import contextmanager

import pytest

from studio.storage import Store
from studio import storage


def sqlite_error(code, name):
    error = sqlite3.OperationalError("injected development I/O failure")
    error.sqlite_errorcode, error.sqlite_errorname = code, name
    return error


def test_windows_truncate_retry_is_finite_and_preserves_existing_database(store, monkeypatch):
    original = Store.migrate
    calls = []

    def temporarily_locked(self):
        calls.append(1)
        if len(calls) < 3:
            raise sqlite_error(sqlite3.SQLITE_IOERR_TRUNCATE, "SQLITE_IOERR_TRUNCATE")
        return original(self)

    monkeypatch.setattr(Store, "migrate", temporarily_locked)
    reopened = Store(store.root)
    assert reopened.initialization_retries == 2 and len(calls) == 3
    with reopened.connect() as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize(
    "code,name,attempts",
    [
        (sqlite3.SQLITE_IOERR_TRUNCATE, "SQLITE_IOERR_TRUNCATE", 3),
        (sqlite3.SQLITE_IOERR_WRITE, "SQLITE_IOERR_WRITE", 1),
        (sqlite3.SQLITE_CORRUPT, "SQLITE_CORRUPT", 1),
    ],
)
def test_persistent_or_other_io_errors_propagate_without_data_cleanup(
    store, monkeypatch, code, name, attempts
):
    calls = []
    before = store.database.read_bytes()

    def broken(self):
        calls.append(1)
        raise sqlite_error(code, name)

    monkeypatch.setattr(Store, "migrate", broken)
    with pytest.raises(sqlite3.OperationalError) as caught:
        Store(store.root)
    assert len(calls) == attempts
    assert store.database.read_bytes() == before
    assert caught.value.sqlite_errorname == name


@pytest.mark.parametrize("phase", ["connect", "setup", "operation", "commit"])
def test_connection_diagnostics_cover_original_failure_and_cleanup(store, monkeypatch, phase):
    original = sqlite_error(sqlite3.SQLITE_IOERR_FSTAT, "SQLITE_IOERR_FSTAT")
    closed = []

    def fail():
        raise original

    def rollback():
        raise sqlite_error(sqlite3.SQLITE_IOERR_TRUNCATE, "SQLITE_IOERR_TRUNCATE")

    def close():
        closed.append(True)
        raise RuntimeError("injected close failure")

    db = SimpleNamespace(
        execute=lambda _: fail() if phase == "setup" else None,
        commit=lambda: fail() if phase == "commit" else None,
        rollback=rollback,
        close=close,
    )
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: fail() if phase == "connect" else db)
    with pytest.raises(sqlite3.OperationalError) as caught:
        with store.connect():
            if phase == "operation":
                fail()
    assert caught.value is original
    assert original.sqlite_errorcode == sqlite3.SQLITE_IOERR_FSTAT
    assert "SQLite connection: SQLITE_IOERR_FSTAT (1802)" in original.__notes__
    if phase != "connect":
        assert closed == [True]
        assert any("rollback also failed" in note for note in original.__notes__)
        assert any("close also failed" in note for note in original.__notes__)


def test_unknown_sqlite_code_still_preserves_original_exception(store):
    original = sqlite3.OperationalError("manually raised without a native result code")
    with pytest.raises(sqlite3.OperationalError) as caught:
        with store.connect():
            raise original
    assert caught.value is original
    assert "SQLite connection: UNKNOWN (UNKNOWN)" in original.__notes__


def test_read_truncate_retry_uses_a_fresh_bounded_snapshot(store, spec, monkeypatch):
    pid, _ = store.create(spec)
    read = store._project_snapshot
    calls = []

    def fail_then_read(identity):
        calls.append(identity)
        if len(calls) < 3:
            raise sqlite_error(sqlite3.SQLITE_IOERR_TRUNCATE, "SQLITE_IOERR_TRUNCATE")
        return read(identity)

    monkeypatch.setattr(store, "_project_snapshot", fail_then_read)
    assert store.get(pid)["id"] == pid
    assert store.read_retries == 2 and calls == [pid] * 3
    assert store.initialization_retries == 0


@pytest.mark.parametrize(
    "code,name,calls_expected",
    [
        (sqlite3.SQLITE_IOERR_TRUNCATE, "SQLITE_IOERR_TRUNCATE", 3),
        (sqlite3.SQLITE_IOERR_FSTAT, "SQLITE_IOERR_FSTAT", 1),
        (sqlite3.SQLITE_IOERR_WRITE, "SQLITE_IOERR_WRITE", 1),
        (sqlite3.SQLITE_CORRUPT, "SQLITE_CORRUPT", 1),
    ],
)
def test_snapshot_failures_remain_finite_and_non_truncate_is_not_retried(
    store, monkeypatch, code, name, calls_expected
):
    calls = []
    original = sqlite_error(code, name)

    def broken(_):
        calls.append(True)
        raise original

    monkeypatch.setattr(store, "_project_snapshot", broken)
    with pytest.raises(sqlite3.OperationalError) as caught:
        store.get("sample")
    assert caught.value is original and len(calls) == calls_expected


def test_project_reads_are_one_snapshot_across_concurrent_writer(store, spec, monkeypatch):
    pid, _ = store.create(spec)
    jid = store.enqueue(pid)
    connect, should_write = store.connect, [True]

    class ProjectCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            row = self.cursor.fetchone()
            if should_write[0]:
                should_write[0] = False
                with connect() as writer:
                    writer.execute("UPDATE projects SET revision=2,status='CANCELLED' WHERE id=?", (pid,))
                    writer.execute("UPDATE jobs SET state='CANCELLED' WHERE id=?", (jid,))
            return row

    class ReadConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, *args):
            cursor = self.db.execute(sql, *args)
            return ProjectCursor(cursor) if sql.startswith("SELECT * FROM projects") else cursor

    @contextmanager
    def intercept():
        with connect() as db:
            yield ReadConnection(db)

    monkeypatch.setattr(store, "connect", intercept)
    snapshot = store.get(pid)
    assert snapshot["revision"] == 1 and snapshot["status"] == "QUEUED"
    assert snapshot["jobs"][0]["state"] == "QUEUED"
    following = store.get(pid)
    assert following["revision"] == 2 and following["status"] == "CANCELLED"
    assert following["jobs"][0]["state"] == "CANCELLED"


def test_non_windows_snapshot_does_not_retry_truncate(store, monkeypatch):
    calls = []
    monkeypatch.setattr(storage, "os", SimpleNamespace(name="posix"))

    def broken(_):
        calls.append(True)
        raise sqlite_error(sqlite3.SQLITE_IOERR_TRUNCATE, "SQLITE_IOERR_TRUNCATE")

    monkeypatch.setattr(store, "_project_snapshot", broken)
    with pytest.raises(sqlite3.OperationalError):
        store.get("sample")
    assert len(calls) == 1 and store.read_retries == 0
