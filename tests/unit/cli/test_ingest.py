"""Tests for foundry ingest CLI command (WI_0023)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from foundry.cli.ingest import _compute_hash
from foundry.cli.main import app
from foundry.db.connection import Database
from foundry.db.models import Chunk, Source
from foundry.db.repository import Repository
from foundry.db.schema import initialize

runner = CliRunner()


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Path to a not-yet-created .foundry.db in tmp_path."""
    return tmp_path / ".foundry.db"


@pytest.fixture
def mock_pipeline():
    """Patch EmbeddingWriter + DocumentSummarizer to suppress litellm calls."""
    with (
        patch("foundry.cli.ingest.EmbeddingWriter") as mock_ew,
        patch("foundry.cli.ingest.DocumentSummarizer") as mock_ds,
    ):
        mock_ew.return_value.write.return_value = [1]
        mock_ds.return_value.summarize.return_value = "Summary."
        yield mock_ew, mock_ds


def _init_db(db_path: Path) -> None:
    """Create and initialise a DB file."""
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    conn.close()


def _open_repo(db_path: Path) -> tuple:
    db = Database(db_path)
    conn = db.connect()
    return Repository(conn), conn


# ------------------------------------------------------------------
# Input validation
# ------------------------------------------------------------------


def test_ingest_exits_without_source(db_path):
    result = runner.invoke(app, ["ingest", "--db", str(db_path)])
    assert result.exit_code == 1
    assert "source" in result.output.lower()


# ------------------------------------------------------------------
# DB creation
# ------------------------------------------------------------------


def test_ingest_creates_db_if_missing(tmp_path, mock_pipeline):
    db_path = tmp_path / "brand-new.db"
    src = tmp_path / "doc.txt"
    src.write_text("Creating a new database on first ingest.")

    assert not db_path.exists()
    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert db_path.exists()


# ------------------------------------------------------------------
# Deduplication
# ------------------------------------------------------------------


def test_ingest_skips_unchanged_source(tmp_path, db_path, mock_pipeline):
    """Source already in DB with matching hash + chunks → skip."""
    src = tmp_path / "doc.txt"
    src.write_text("Hello Foundry.")
    actual_hash = _compute_hash(str(src))

    # Pre-populate DB: source with correct hash + 1 chunk already stored
    _init_db(db_path)
    repo, conn = _open_repo(db_path)
    repo.add_source(
        Source(
            id="existing-id",
            path=str(src),
            content_hash=actual_hash,
            embedding_model="openai/text-embedding-3-small",
        )
    )
    repo.add_chunk(Chunk(source_id="existing-id", chunk_index=0, text="Hello Foundry."))
    conn.close()

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "Unchanged" in result.output


def test_ingest_reingest_on_hash_change(tmp_path, db_path, mock_pipeline):
    """Source in DB with different hash + chunks → re-ingest."""
    src = tmp_path / "doc.txt"
    src.write_text("Version 2.")

    # Pre-populate DB: source with OLD (stale) hash + 1 chunk
    _init_db(db_path)
    repo, conn = _open_repo(db_path)
    repo.add_source(
        Source(
            id="old-id",
            path=str(src),
            content_hash="stale-hash-different",
            embedding_model="openai/text-embedding-3-small",
        )
    )
    repo.add_chunk(Chunk(source_id="old-id", chunk_index=0, text="Version 1."))
    conn.close()

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "Re-ingesting" in result.output


def test_ingest_partial_recovery(tmp_path, db_path, mock_pipeline):
    """Source in DB with correct hash but 0 chunks → recovery re-ingest."""
    src = tmp_path / "doc.txt"
    src.write_text("Some text.")
    actual_hash = _compute_hash(str(src))

    # Pre-populate DB: source with correct hash but no chunks (partial ingest)
    _init_db(db_path)
    repo, conn = _open_repo(db_path)
    repo.add_source(
        Source(
            id="partial-id",
            path=str(src),
            content_hash=actual_hash,
            embedding_model="openai/text-embedding-3-small",
        )
    )
    conn.close()

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "Recovering" in result.output

    # New source ID should have been assigned
    repo2, conn2 = _open_repo(db_path)
    stored = repo2.get_source_by_path(str(src))
    assert stored is not None
    assert stored.id != "partial-id"
    conn2.close()


# ------------------------------------------------------------------
# Dry run
# ------------------------------------------------------------------


def test_ingest_dry_run_no_db_writes(tmp_path, db_path, mock_pipeline):
    src = tmp_path / "doc.txt"
    src.write_text("Some content here.")

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--dry-run"]
    )

    assert result.exit_code == 0
    assert "Dry run" in result.output

    # DB must not contain the source
    _init_db(db_path)  # idempotent if CLI already created it
    repo, conn = _open_repo(db_path)
    assert repo.get_source_by_path(str(src)) is None
    conn.close()


# ------------------------------------------------------------------
# Source type routing
# ------------------------------------------------------------------


def test_ingest_plaintext_file(tmp_path, db_path, mock_pipeline):
    src = tmp_path / "notes.txt"
    src.write_text("Foundry processes plain text documents.")

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "chunks" in result.output


def test_ingest_markdown_file(tmp_path, db_path, mock_pipeline):
    src = tmp_path / "spec.md"
    src.write_text("# Heading\n\nSome markdown content here.")

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "chunks" in result.output


def test_ingest_json_file(tmp_path, db_path, mock_pipeline):
    src = tmp_path / "data.json"
    src.write_text('[{"key": "value1"}, {"key": "value2"}]')

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "chunks" in result.output


def test_ingest_unsupported_extension_skipped(tmp_path, db_path):
    src = tmp_path / "image.xyz"
    src.write_bytes(b"\xff\xd8\xff fake image")

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "Unsupported" in result.output or "unsupported" in result.output.lower()


def test_ingest_empty_source_skipped(tmp_path, db_path, mock_pipeline):
    src = tmp_path / "empty.txt"
    src.write_text("")

    result = runner.invoke(
        app, ["ingest", "--source", str(src), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "No chunks" in result.output


# ------------------------------------------------------------------
# Directory scanning
# ------------------------------------------------------------------


def test_ingest_directory_scans_files(tmp_path, db_path, mock_pipeline):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("Content A.")
    (docs / "b.md").write_text("# B\n\nContent B.")
    (docs / "c.xyz").write_bytes(b"ignored binary")

    result = runner.invoke(
        app, ["ingest", "--source", str(docs), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "a.txt" in result.output
    assert "b.md" in result.output
    assert "c.xyz" not in result.output


def test_ingest_directory_not_recursive_by_default(tmp_path, db_path, mock_pipeline):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "top.txt").write_text("Top level.")
    sub = docs / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("Nested content.")

    result = runner.invoke(
        app, ["ingest", "--source", str(docs), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "top.txt" in result.output
    assert "nested.txt" not in result.output


def test_ingest_recursive_flag_finds_nested_files(tmp_path, db_path, mock_pipeline):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "top.txt").write_text("Top level.")
    sub = docs / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("Nested content.")

    result = runner.invoke(
        app,
        ["ingest", "--source", str(docs), "--db", str(db_path), "--yes", "--recursive"],
    )

    assert result.exit_code == 0
    assert "nested.txt" in result.output


def test_ingest_exclude_pattern(tmp_path, db_path, mock_pipeline):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "keep.txt").write_text("Keep this file.")
    (docs / "ignore.log").write_text("Debug log — should be excluded.")

    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            str(docs),
            "--db",
            str(db_path),
            "--yes",
            "--exclude",
            "*.log",
        ],
    )

    assert result.exit_code == 0
    assert "keep.txt" in result.output
    assert "ignore.log" not in result.output


def test_ingest_empty_directory_warns(tmp_path, db_path):
    docs = tmp_path / "empty_dir"
    docs.mkdir()

    result = runner.invoke(
        app, ["ingest", "--source", str(docs), "--db", str(db_path), "--yes"]
    )

    assert result.exit_code == 0
    assert "No supported files" in result.output
