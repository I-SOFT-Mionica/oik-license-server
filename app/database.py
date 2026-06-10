import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import app.config as config

_DDL = """
CREATE TABLE IF NOT EXISTS licenses (
    id            TEXT PRIMARY KEY,
    license_code  TEXT UNIQUE NOT NULL,
    issued_to     TEXT NOT NULL,
    updates_until TEXT NOT NULL,
    modules       TEXT NOT NULL DEFAULT '["full"]',
    hid           TEXT,
    revoked       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
"""


def init_db() -> None:
    db = config.db_path()
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.executescript(_DDL)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(config.db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
