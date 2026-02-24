"""Tests for foundry generate CLI command (WI_0029, WI_0031)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from foundry.cli.main import app
from foundry.db.connection import Database
from foundry.db.models import Chunk, Source
from foundry.db.repository import Repository
from foundry.db.schema import initialize
from foundry.db.vectors import ensure_vec_table, model_to_slug

runner = CliRunner()

_MODEL = "openai/text-embedding-3-small"
_DIMS = 1536
_FAKE_EMBEDDING = [0.1] * _DIMS


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".foundry.db"


@pytest.fixture
def populated_db(db_path: Path):
    """DB with one source, one chunk, and one embedding."""
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    repo = Repository(conn)
    slug = model_to_slug(_MODEL)
    vec_table = ensure_vec_table(conn, slug, _DIMS)

    repo.add_source(
        Source(
            id="src-1",
            path="doc.txt",
            content_hash="abc",
            embedding_model=_MODEL,
        )
    )
    rowid = repo.add_chunk(
        Chunk(source_id="src-1", chunk_index=0, text="DMX512 uses 512 channels.")
    )
    repo.add_embedding(vec_table, rowid, _FAKE_EMBEDDING)
    repo.add_summary("src-1", "A document about DMX512.")
    conn.close()
    return db_path


@pytest.fixture
def approved_features_dir(tmp_path: Path) -> Path:
    """A features/ directory with one approved spec."""
    features = tmp_path / "features"
    features.mkdir()
    (features / "wiring.md").write_text(
        "# Wiring Guide\n\n## Approved\nGoedgekeurd op 2026-03-01\n",
        encoding="utf-8",
    )
    return features


def _mock_pipeline():
    """Context manager that mocks all LLM calls in generate pipeline."""
    mock_completion_resp = MagicMock()
    mock_completion_resp.choices[0].message.content = "Generated content."
    mock_emb_resp = MagicMock()
    mock_emb_resp.data = [{"embedding": _FAKE_EMBEDDING}]

    return (
        patch("foundry.rag.retriever.litellm.completion", return_value=mock_completion_resp),
        patch("foundry.rag.retriever.litellm.embedding", return_value=mock_emb_resp),
        patch("foundry.rag.assembler.complete", side_effect=["[9]", "[]"]),
        patch("foundry.rag.assembler.count_tokens", return_value=10),
        patch("foundry.generate.templates.count_tokens", return_value=50),
        patch("foundry.generate.templates.get_context_window", return_value=128_000),
        patch("foundry.rag.llm_client.litellm.token_counter", return_value=50),
        patch("foundry.cli.generate.complete", return_value="Generated content."),
        patch("foundry.cli.generate.validate_api_key"),
    )


# ------------------------------------------------------------------
# Input validation
# ------------------------------------------------------------------


def test_generate_missing_topic(tmp_path, db_path):
    result = runner.invoke(
        app,
        ["generate", "--output", "out.md", "--db", str(db_path)],
    )
    assert result.exit_code != 0


def test_generate_missing_output(tmp_path, db_path):
    result = runner.invoke(
        app,
        ["generate", "--topic", "DMX wiring", "--db", str(db_path)],
    )
    assert result.exit_code != 0


def test_generate_path_traversal_blocked(populated_db):
    result = runner.invoke(
        app,
        [
            "generate",
            "--topic", "wiring",
            "--output", "../../etc/passwd",
            "--db", str(populated_db),
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "traversal" in result.output.lower() or "Error" in result.output


# ------------------------------------------------------------------
# Feature gate (WI_0031)
# ------------------------------------------------------------------


def test_generate_no_features_dir_hard_fails(tmp_path, populated_db):
    """features/ missing → hard fail with scaffold instruction."""
    out = tmp_path / "draft.md"
    no_features_dir = tmp_path / "nonexistent_features"

    with patch("foundry.cli.generate._FEATURES_DIR", no_features_dir):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 1
    assert "features" in result.output.lower()
    assert "Checklist" in result.output or "checklist" in result.output.lower()


def test_generate_empty_features_dir_hard_fails(tmp_path, populated_db):
    """features/ exists but has no .md files → hard fail."""
    out = tmp_path / "draft.md"
    features_dir = tmp_path / "features"
    features_dir.mkdir()

    with patch("foundry.cli.generate._FEATURES_DIR", features_dir):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 1
    assert "Error" in result.output


def test_generate_no_approved_specs_hard_fails(tmp_path, populated_db):
    """features/ has specs but none approved → hard fail with full checklist."""
    out = tmp_path / "draft.md"
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    (features_dir / "wiring.md").write_text("# Wiring\n\nNot approved yet.\n")
    (features_dir / "firmware.md").write_text("# Firmware\n\nNot approved yet.\n")

    with patch("foundry.cli.generate._FEATURES_DIR", features_dir):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 1
    # Both spec names should appear in the checklist
    assert "wiring" in result.output
    assert "firmware" in result.output


# ------------------------------------------------------------------
# No embeddings → error
# ------------------------------------------------------------------


def test_generate_no_embeddings_fails(tmp_path, db_path, approved_features_dir):
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    conn.close()

    with patch("foundry.cli.generate._FEATURES_DIR", approved_features_dir):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(tmp_path / "out.md"),
                "--db", str(db_path),
                "--yes",
            ],
        )
    assert result.exit_code == 1
    assert "No embeddings" in result.output or "Error" in result.output


# ------------------------------------------------------------------
# Dry run
# ------------------------------------------------------------------


def test_generate_dry_run_no_file_written(tmp_path, populated_db, approved_features_dir):
    out = tmp_path / "draft.md"
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", approved_features_dir),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--dry-run",
                "--yes",
            ],
        )

    assert result.exit_code == 0
    assert not out.exists()
    assert "Dry run" in result.output or "dry" in result.output.lower()


# ------------------------------------------------------------------
# Successful generation
# ------------------------------------------------------------------


def test_generate_writes_output_file(tmp_path, populated_db, approved_features_dir):
    out = tmp_path / "draft.md"
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", approved_features_dir),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text()
    assert "Generated content." in content


def test_generate_output_includes_attribution(tmp_path, populated_db, approved_features_dir):
    out = tmp_path / "draft.md"
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", approved_features_dir),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "DMX wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 0
    content = out.read_text()
    assert "[^" in content or "---" in content


# ------------------------------------------------------------------
# Feature spec selection
# ------------------------------------------------------------------


def test_generate_feature_not_found_fails(tmp_path, populated_db):
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    (features_dir / "other.md").write_text("# Other\n\n## Approved\nGoedgekeurd op 2026-03-01\n")

    out = tmp_path / "draft.md"
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", features_dir),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--feature", "nonexistent",
                "--yes",
            ],
        )

    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "Error" in result.output


def test_generate_multiple_specs_without_feature_flag_fails(tmp_path, populated_db):
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    (features_dir / "spec-a.md").write_text("# A\n\n## Approved\nGoedgekeurd op 2026-03-01\n")
    (features_dir / "spec-b.md").write_text("# B\n\n## Approved\nGoedgekeurd op 2026-03-01\n")

    out = tmp_path / "draft.md"
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", features_dir),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 1
    assert "Multiple" in result.output or "feature" in result.output.lower()


def test_generate_auto_selects_single_approved_spec(tmp_path, populated_db):
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    (features_dir / "wiring.md").write_text("# Wiring\n\n## Approved\nGoedgekeurd op 2026-03-01\n")

    out = tmp_path / "draft.md"
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", features_dir),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "wiring",
                "--output", str(out),
                "--db", str(populated_db),
                "--yes",
            ],
        )

    assert result.exit_code == 0


# ------------------------------------------------------------------
# Overwrite protection
# ------------------------------------------------------------------


def test_generate_overwrite_protection_user_declines(tmp_path, populated_db, approved_features_dir):
    out = tmp_path / "existing.md"
    out.write_text("old content")
    mocks = _mock_pipeline()

    with (
        patch("foundry.cli.generate._FEATURES_DIR", approved_features_dir),
        patch("foundry.generate.writer.typer.confirm", return_value=False),
        mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8],
    ):
        result = runner.invoke(
            app,
            [
                "generate",
                "--topic", "wiring",
                "--output", str(out),
                "--db", str(populated_db),
            ],
        )

    assert result.exit_code == 0
    assert out.read_text() == "old content"  # unchanged
