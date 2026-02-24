"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from foundry.db.connection import Database
from foundry.db.schema import initialize


@pytest.fixture
def tmp_db(tmp_path):
    """File-based DB in tmp_path with schema initialized, closed after test."""
    db = Database(tmp_path / ".foundry.db")
    conn = db.connect()
    initialize(conn)
    yield conn
    conn.close()
