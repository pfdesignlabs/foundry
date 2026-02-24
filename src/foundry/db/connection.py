"""SQLite connection layer with sqlite-vec extension."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec


class Database:
    """Per-project SQLite database with sqlite-vec vector search support."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        """Open a connection, load sqlite-vec, and return the connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def __enter__(self) -> sqlite3.Connection:
        self._conn = self.connect()
        return self._conn

    def __exit__(self, *args: object) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
