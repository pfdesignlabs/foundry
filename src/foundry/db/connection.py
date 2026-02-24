"""SQLite connection layer with sqlite-vec extension."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec


class Database:
    """Per-project SQLite database with sqlite-vec vector search support."""

    def __init__(self, db_path: Path | str) -> None:
        """Store the database path. Call connect() to open the connection.

        Args:
            db_path: Path to the SQLite database file (created if missing).
        """
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
        """Open the database and return the connection (context manager support)."""
        self._conn = self.connect()
        return self._conn

    def __exit__(self, *args: object) -> None:
        """Close the connection when leaving the context manager."""
        if self._conn:
            self._conn.close()
            self._conn = None
