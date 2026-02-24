"""Tests for Database connection layer (WI_0012)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from foundry.db.connection import Database


def test_connect_creates_file(tmp_path):
    db_path = tmp_path / ".foundry.db"
    db = Database(db_path)
    conn = db.connect()
    conn.close()
    assert db_path.exists()


def test_sqlite_vec_loads(tmp_path):
    db = Database(tmp_path / ".foundry.db")
    conn = db.connect()
    version = conn.execute("SELECT vec_version()").fetchone()[0]
    conn.close()
    assert version.startswith("v")


def test_foreign_keys_enabled(tmp_path):
    db = Database(tmp_path / ".foundry.db")
    conn = db.connect()
    result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.close()
    assert result == 1


def test_wal_journal_mode(tmp_path):
    db = Database(tmp_path / ".foundry.db")
    conn = db.connect()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


def test_row_factory_set(tmp_path):
    db = Database(tmp_path / ".foundry.db")
    conn = db.connect()
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    row = conn.execute("SELECT x FROM t").fetchone()
    conn.close()
    assert row["x"] == 42


def test_context_manager_closes_connection(tmp_path):
    db = Database(tmp_path / ".foundry.db")
    with db as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
    # Connection should be closed — further use raises ProgrammingError
    with pytest.raises(Exception):
        conn.execute("SELECT 1")


def test_context_manager_accepts_path_str(tmp_path):
    db = Database(str(tmp_path / ".foundry.db"))
    assert isinstance(db.db_path, Path)
    with db as conn:
        result = conn.execute("SELECT 1").fetchone()[0]
    assert result == 1
