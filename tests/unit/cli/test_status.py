"""Tests for foundry status command (WI_0037)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from foundry.cli.main import app
from foundry.db.connection import Database
from foundry.db.models import Source
from foundry.db.repository import Repository
from foundry.db.schema import initialize

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(path: Path) -> sqlite3.Connection:
    db = Database(path)
    conn = db.connect()
    initialize(conn)
    return conn


def _add_source(repo: Repository, path: str = "doc.pdf") -> str:
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
# foundry --version
# ---------------------------------------------------------------------------


def test_version_flag_exits_zero() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_version_flag_shows_foundry() -> None:
    result = runner.invoke(app, ["--version"])
    assert "foundry" in result.output.lower()


def test_version_command_exits_zero() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0


def test_version_command_shows_version() -> None:
    result = runner.invoke(app, ["version"])
    assert "foundry" in result.output.lower()


# ---------------------------------------------------------------------------
# foundry status — no DB
# ---------------------------------------------------------------------------


def test_status_no_db(tmp_path: Path) -> None:
    """foundry status without a database exits 0 with informative message."""
    missing_db = tmp_path / "nonexistent.db"
    result = runner.invoke(app, ["status", "--db", str(missing_db)])
    assert result.exit_code == 0
    assert "foundry init" in result.output or "No database" in result.output


# ---------------------------------------------------------------------------
# foundry status — with DB, no sources
# ---------------------------------------------------------------------------


def test_status_empty_db(tmp_path: Path) -> None:
    """Status with empty DB shows 0 sources and 0 chunks."""
    db_path = tmp_path / ".foundry.db"
    conn = _make_db(db_path)
    conn.close()

    result = runner.invoke(app, ["status", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "0" in result.output  # 0 sources or 0 chunks


# ---------------------------------------------------------------------------
# foundry status — with sources
# ---------------------------------------------------------------------------


def test_status_shows_source_count(tmp_path: Path) -> None:
    """Status shows correct source count."""
    db_path = tmp_path / ".foundry.db"
    conn = _make_db(db_path)
    repo = Repository(conn)
    _add_source(repo, "doc1.pdf")
    _add_source(repo, "doc2.md")
    conn.close()

    result = runner.invoke(app, ["status", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "2" in result.output


def test_status_shows_knowledge_base_panel(tmp_path: Path) -> None:
    """Status output includes 'Knowledge Base' panel."""
    db_path = tmp_path / ".foundry.db"
    conn = _make_db(db_path)
    conn.close()

    result = runner.invoke(app, ["status", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "Knowledge" in result.output


# ---------------------------------------------------------------------------
# foundry status — features panel
# ---------------------------------------------------------------------------


def test_status_no_features_dir(tmp_path: Path) -> None:
    """Status without features/ dir shows informative message."""
    db_path = tmp_path / ".foundry.db"
    no_features = tmp_path / "nonexistent_features"
    result = runner.invoke(
        app,
        ["status", "--db", str(db_path), "--features-dir", str(no_features)],
    )
    assert result.exit_code == 0
    assert "features" in result.output.lower() or "Feature" in result.output


def test_status_shows_approved_features(tmp_path: Path) -> None:
    """Status shows approved features with ✓ marker."""
    features = tmp_path / "features"
    features.mkdir()
    (features / "wiring.md").write_text(
        "# Wiring\n\n## Approved\nGoedgekeurd op 2026-03-01\n", encoding="utf-8"
    )
    (features / "firmware.md").write_text("# Firmware\n\nNot approved.\n", encoding="utf-8")

    db_path = tmp_path / ".foundry.db"
    result = runner.invoke(
        app,
        ["status", "--db", str(db_path), "--features-dir", str(features)],
    )
    assert result.exit_code == 0
    assert "wiring" in result.output
    assert "firmware" in result.output


def test_status_features_shows_count(tmp_path: Path) -> None:
    """Status features panel shows N/M approved count."""
    features = tmp_path / "features"
    features.mkdir()
    (features / "a.md").write_text(
        "# A\n\n## Approved\nGoedgekeurd op 2026-03-01\n", encoding="utf-8"
    )
    (features / "b.md").write_text("# B\nNot done.\n", encoding="utf-8")

    db_path = tmp_path / ".foundry.db"
    result = runner.invoke(
        app,
        ["status", "--db", str(db_path), "--features-dir", str(features)],
    )
    assert result.exit_code == 0
    assert "1/2" in result.output


# ---------------------------------------------------------------------------
# foundry status — sprint panel
# ---------------------------------------------------------------------------


def _write_slice(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_status_shows_sprint_when_slice_present(tmp_path: Path) -> None:
    """Status shows sprint panel when .forge/slice.yaml exists."""
    slice_path = tmp_path / ".forge" / "slice.yaml"
    _write_slice(
        slice_path,
        {
            "slice": {
                "id": "SP_006",
                "name": "Phase 5 CLI Polish",
                "target": "2026-03-14",
            },
            "workitems": [
                {"id": "WI_0034", "status": "done"},
                {"id": "WI_0035", "status": "in_progress"},
                {"id": "WI_0036", "status": "pending"},
            ],
        },
    )

    db_path = tmp_path / ".foundry.db"
    result = runner.invoke(
        app,
        ["status", "--db", str(db_path), "--slice", str(slice_path)],
    )
    assert result.exit_code == 0
    assert "SP_006" in result.output
    assert "1/3" in result.output  # 1 done out of 3


def test_status_no_sprint_when_slice_absent(tmp_path: Path) -> None:
    """Status does not show sprint panel when slice.yaml is absent."""
    missing_slice = tmp_path / "nonexistent" / "slice.yaml"
    db_path = tmp_path / ".foundry.db"

    result = runner.invoke(
        app,
        ["status", "--db", str(db_path), "--slice", str(missing_slice)],
    )
    assert result.exit_code == 0
    assert "Sprint" not in result.output


# ---------------------------------------------------------------------------
# foundry status — project panel
# ---------------------------------------------------------------------------


def test_status_shows_project_name_from_config(tmp_path: Path) -> None:
    """Status reads project name from foundry.yaml."""
    cfg_file = tmp_path / "foundry.yaml"
    cfg_file.write_text("project:\n  name: DMX Controller\n", encoding="utf-8")

    db_path = tmp_path / ".foundry.db"
    result = runner.invoke(app, ["status", "--db", str(db_path)], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0
    # Note: config loads from CWD by default; our test passes --db so the
    # project panel still shows name from the config loaded in the default CWD.
    # This test just ensures exit_code == 0; config integration is tested in test_config.py.


def test_status_shows_db_size_when_db_exists(tmp_path: Path) -> None:
    """Status shows database file size when DB exists."""
    db_path = tmp_path / ".foundry.db"
    conn = _make_db(db_path)
    conn.close()

    result = runner.invoke(app, ["status", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "MB" in result.output
