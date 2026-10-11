import sqlite3

import pytest

from studio.storage import Store


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
