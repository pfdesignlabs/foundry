"""Tests for foundry remove command (WI_0039)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from foundry.cli.main import app
from foundry.db.connection import Database
from foundry.db.models import Source
from foundry.db.repository import Repository
from foundry.db.schema import initialize
from foundry.db.vectors import ensure_vec_table, model_to_slug

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(path: Path) -> tuple[sqlite3.Connection, Repository]:
    db = Database(path)
    conn = db.connect()
    initialize(conn)
    return conn, Repository(conn)


def _add_source(repo: Repository, path: str = "datasheet.pdf") -> str:
    source_id = f"src-{path}"
    repo.add_source(
        Source(
            id=source_id,
            path=path,
            content_hash="abc",
            embedding_model="openai/text-embedding-3-small",
        )
    )
    return source_id


# ---------------------------------------------------------------------------
# foundry remove — no DB
# ---------------------------------------------------------------------------


def test_remove_no_db_exits_1(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    result = runner.invoke(
        app, ["remove", "--source", "doc.pdf", "--db", str(missing), "--yes"]
    )
    assert result.exit_code == 1
    assert "foundry init" in result.output or "No database" in result.output


# ---------------------------------------------------------------------------
# foundry remove — source not found
# ---------------------------------------------------------------------------


def test_remove_source_not_found_exits_0(tmp_path: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    conn, _ = _make_db(db_path)
    conn.close()

    result = runner.invoke(
        app, ["remove", "--source", "nonexistent.pdf", "--db", str(db_path), "--yes"]
    )
    assert result.exit_code == 0
    assert "not found" in result.output.lower() or "nonexistent" in result.output


# ---------------------------------------------------------------------------
# foundry remove — confirmation prompt
# ---------------------------------------------------------------------------


def test_remove_asks_confirmation_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    _add_source(repo, "doc.pdf")
    conn.close()

    # Provide "n" to cancel
    result = runner.invoke(
        app, ["remove", "--source", "doc.pdf", "--db", str(db_path)], input="n\n"
    )
    assert result.exit_code == 0
    assert "Cancelled" in result.output or "cancel" in result.output.lower()


def test_remove_yes_skips_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    _add_source(repo, "doc.pdf")
    conn.close()

    result = runner.invoke(
        app, ["remove", "--source", "doc.pdf", "--db", str(db_path), "--yes"]
    )
    assert result.exit_code == 0
    assert "Removed" in result.output or "removed" in result.output.lower()


# ---------------------------------------------------------------------------
# foundry remove — data deletion
# ---------------------------------------------------------------------------


def test_remove_deletes_source_record(tmp_path: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    _add_source(repo, "doc.pdf")
    conn.close()

    runner.invoke(app, ["remove", "--source", "doc.pdf", "--db", str(db_path), "--yes"])

    conn2, repo2 = _make_db(db_path)
    assert repo2.get_source_by_path("doc.pdf") is None
    conn2.close()


def test_remove_deletes_summary(tmp_path: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    source_id = _add_source(repo, "doc.pdf")
    repo.add_summary(source_id, "A summary of this document.")
    conn.close()

    runner.invoke(app, ["remove", "--source", "doc.pdf", "--db", str(db_path), "--yes"])

    conn2, repo2 = _make_db(db_path)
    assert repo2.get_summary(source_id) is None
    conn2.close()


def test_remove_shows_chunk_count_in_prompt(tmp_path: Path) -> None:
    """Confirmation prompt shows chunk count."""
    from foundry.db.models import Chunk

    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    source_id = _add_source(repo, "doc.pdf")
    # Add 3 chunks manually
    for i in range(3):
        repo.add_chunk(Chunk(source_id=source_id, chunk_index=i, text=f"Chunk {i}"))
    conn.close()

    result = runner.invoke(
        app, ["remove", "--source", "doc.pdf", "--db", str(db_path)], input="n\n"
    )
    assert "3" in result.output


# ---------------------------------------------------------------------------
# foundry remove — stale outputs warning
# ---------------------------------------------------------------------------


def test_remove_shows_stale_warning_after_delete(tmp_path: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    _add_source(repo, "doc.pdf")
    conn.close()

    result = runner.invoke(
        app, ["remove", "--source", "doc.pdf", "--db", str(db_path), "--yes"]
    )
    assert result.exit_code == 0
    # Warning about stale outputs should be present
    assert "stale" in result.output.lower() or "regenerat" in result.output.lower()


# ---------------------------------------------------------------------------
# delete_embeddings_by_source (repository method)
# ---------------------------------------------------------------------------


def test_delete_embeddings_by_source_removes_vec_entries(tmp_path: Path) -> None:
    """delete_embeddings_by_source removes entries from all vec tables."""
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    source_id = _add_source(repo, "doc.pdf")

    from foundry.db.models import Chunk

    chunk = Chunk(source_id=source_id, chunk_index=0, text="Test chunk.")
    rowid = repo.add_chunk(chunk)

    slug = model_to_slug("openai/text-embedding-3-small")
    vec_table = ensure_vec_table(conn, slug, dimensions=3)
    repo.add_embedding(vec_table, rowid, [0.1, 0.2, 0.3])

    deleted = repo.delete_embeddings_by_source(source_id)
    assert deleted >= 0  # return value is non-negative (sqlite-vec rowcount varies)

    # Vec table should now be empty for this rowid
    results = repo.search_vec(vec_table, [0.1, 0.2, 0.3], limit=10)
    assert len(results) == 0
    conn.close()


def test_delete_embeddings_no_source_returns_zero(tmp_path: Path) -> None:
    """delete_embeddings_by_source with no matching source returns 0."""
    db_path = tmp_path / ".foundry.db"
    conn, repo = _make_db(db_path)
    deleted = repo.delete_embeddings_by_source("nonexistent-id")
    assert deleted == 0
    conn.close()
