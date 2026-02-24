"""Tests for foundry features CLI commands (WI_0032, WI_0033)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from foundry.cli.main import app

runner = CliRunner()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _write_spec(features_dir: Path, name: str, content: str) -> Path:
    p = features_dir / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


# ------------------------------------------------------------------
# WI_0032: foundry features list
# ------------------------------------------------------------------


def test_features_list_no_dir(tmp_path: Path) -> None:
    """No features/ dir → friendly message, exit 0."""
    no_dir = tmp_path / "nonexistent"
    result = runner.invoke(app, ["features", "list", "--features-dir", str(no_dir)])
    assert result.exit_code == 0
    assert "features" in result.output.lower()


def test_features_list_empty_dir(tmp_path: Path) -> None:
    """features/ exists but is empty → message, exit 0."""
    features = tmp_path / "features"
    features.mkdir()
    result = runner.invoke(app, ["features", "list", "--features-dir", str(features)])
    assert result.exit_code == 0
    assert "No feature specs" in result.output or "feature" in result.output.lower()


def test_features_list_shows_all_specs(tmp_path: Path) -> None:
    """Shows all specs with correct status."""
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "wiring", "# Wiring\n\n## Approved\nGoedgekeurd op 2026-03-01\n")
    _write_spec(features, "firmware", "# Firmware\n\nNot approved.\n")

    result = runner.invoke(app, ["features", "list", "--features-dir", str(features)])
    assert result.exit_code == 0
    assert "wiring" in result.output
    assert "firmware" in result.output


def test_features_list_shows_approved_marker(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "spec-a", "# A\n\n## Approved\nGoedgekeurd op 2026-03-01\n")

    result = runner.invoke(app, ["features", "list", "--features-dir", str(features)])
    assert result.exit_code == 0
    assert "approved" in result.output.lower() or "✓" in result.output


def test_features_list_shows_pending_marker(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "spec-b", "# B\n\nNot done.\n")

    result = runner.invoke(app, ["features", "list", "--features-dir", str(features)])
    assert result.exit_code == 0
    assert "pending" in result.output.lower() or "✗" in result.output


def test_features_list_shows_count(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "a", "# A\n\n## Approved\nGoedgekeurd op 2026-03-01\n")
    _write_spec(features, "b", "# B\n\nNot done.\n")

    result = runner.invoke(app, ["features", "list", "--features-dir", str(features)])
    assert result.exit_code == 0
    assert "1/2" in result.output


def test_features_list_shows_date(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "spec", "# S\n\n## Approved\nGoedgekeurd op 2026-03-15\n")

    result = runner.invoke(app, ["features", "list", "--features-dir", str(features)])
    assert result.exit_code == 0
    assert "2026-03-15" in result.output or "Goedgekeurd" in result.output


# ------------------------------------------------------------------
# WI_0033: foundry features approve
# ------------------------------------------------------------------


def test_features_approve_adds_approved_heading(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "wiring", "# Wiring Guide\n\nSome content.\n")

    result = runner.invoke(
        app, ["features", "approve", "wiring", "--features-dir", str(features)]
    )
    assert result.exit_code == 0

    content = (features / "wiring.md").read_text(encoding="utf-8")
    assert "## Approved" in content


def test_features_approve_adds_date(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "spec", "# Spec\n\nContent.\n")

    result = runner.invoke(
        app, ["features", "approve", "spec", "--features-dir", str(features)]
    )
    assert result.exit_code == 0

    content = (features / "spec.md").read_text(encoding="utf-8")
    # Date should be in YYYY-MM-DD format
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", content)


def test_features_approve_already_approved_no_overwrite(tmp_path: Path) -> None:
    """If spec is already approved, do not add a second ## Approved."""
    features = tmp_path / "features"
    features.mkdir()
    original = "# Guide\n\n## Approved\nGoedgekeurd op 2026-01-01\n"
    _write_spec(features, "guide", original)

    result = runner.invoke(
        app, ["features", "approve", "guide", "--features-dir", str(features)]
    )
    assert result.exit_code == 0
    assert "Already approved" in result.output or "already" in result.output.lower()

    # File must not have changed
    content = (features / "guide.md").read_text(encoding="utf-8")
    assert content.count("## Approved") == 1


def test_features_approve_nonexistent_spec_fails(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()

    result = runner.invoke(
        app, ["features", "approve", "doesnotexist", "--features-dir", str(features)]
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "Error" in result.output


def test_features_approve_success_message(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "my-spec", "# Spec\n\nContent.\n")

    result = runner.invoke(
        app, ["features", "approve", "my-spec", "--features-dir", str(features)]
    )
    assert result.exit_code == 0
    assert "my-spec" in result.output or "Approved" in result.output


def test_features_approve_exact_heading_not_modified(tmp_path: Path) -> None:
    """The ## Approved heading appended should be exact (parseable back)."""
    from foundry.gates.parser import parse_spec

    features = tmp_path / "features"
    features.mkdir()
    _write_spec(features, "verify", "# Verify\n\nContent here.\n")

    runner.invoke(app, ["features", "approve", "verify", "--features-dir", str(features)])

    spec = parse_spec(features / "verify.md")
    assert spec.approved is True
    assert spec.approved_on is not None
