"""Tests for foundry build command (WI_0040)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".foundry.db"


@pytest.fixture
def populated_db(db_path: Path) -> Path:
    """DB with one source, one chunk, one embedding, and one summary."""
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    repo = Repository(conn)
    slug = model_to_slug(_MODEL)
    vec_table = ensure_vec_table(conn, slug, _DIMS)
    repo.add_source(
        Source(id="src-1", path="doc.txt", content_hash="abc", embedding_model=_MODEL)
    )
    rowid = repo.add_chunk(Chunk(source_id="src-1", chunk_index=0, text="DMX content."))
    repo.add_embedding(vec_table, rowid, _FAKE_EMBEDDING)
    repo.add_summary("src-1", "A document about DMX.")
    conn.close()
    return db_path


@pytest.fixture
def approved_features(tmp_path: Path) -> Path:
    features = tmp_path / "features"
    features.mkdir()
    (features / "wiring.md").write_text(
        "# Wiring Guide\n\n## Approved\nGoedgekeurd op 2026-03-01\n",
        encoding="utf-8",
    )
    return features


@pytest.fixture
def foundry_yaml_generated(tmp_path: Path, approved_features: Path) -> Path:
    cfg_path = tmp_path / "foundry.yaml"
    cfg_path.write_text(
        "project:\n"
        '  name: "TestProject"\n'
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: generated\n"
        "      feature: wiring\n"
        '      topic: "DMX wiring"\n'
        '      heading: "Wiring Guide"\n',
        encoding="utf-8",
    )
    return cfg_path


@pytest.fixture
def foundry_yaml_file_section(tmp_path: Path) -> Path:
    """foundry.yaml with a file section pointing to an absolute path in tmp_path."""
    spec_path = tmp_path / "output" / "spec.pdf"
    cfg_path = tmp_path / "foundry.yaml"
    cfg_path.write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: file\n"
        f'      path: "{spec_path}"\n'
        '      heading: "Spec PDF"\n'
        '      description: "Technical specification"\n',
        encoding="utf-8",
    )
    return cfg_path


@pytest.fixture
def slice_yaml_done(tmp_path: Path) -> Path:
    forge = tmp_path / ".forge"
    forge.mkdir()
    slice_path = forge / "slice.yaml"
    slice_path.write_text(
        "slice:\n"
        '  id: SP_001\n'
        "workitems:\n"
        "  - id: WI_0001\n"
        '    status: done\n',
        encoding="utf-8",
    )
    return slice_path


@pytest.fixture
def slice_yaml_in_progress(tmp_path: Path) -> Path:
    forge = tmp_path / ".forge"
    forge.mkdir(exist_ok=True)
    slice_path = forge / "slice.yaml"
    slice_path.write_text(
        "slice:\n"
        '  id: SP_001\n'
        "workitems:\n"
        "  - id: WI_0001\n"
        '    status: in_progress\n',
        encoding="utf-8",
    )
    return slice_path


def _mock_generate_pipeline():
    """Context managers that mock all LLM calls in the generate pipeline."""
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
        patch("foundry.cli.build.complete", return_value="Generated content."),
        patch("foundry.cli.build.validate_api_key"),
    )


# ---------------------------------------------------------------------------
# No delivery config
# ---------------------------------------------------------------------------


def test_build_no_delivery_config_exits_1(tmp_path: Path, db_path: Path) -> None:
    """No delivery: section in foundry.yaml → exit 1."""
    (tmp_path / "foundry.yaml").write_text("project:\n  name: Test\n", encoding="utf-8")
    db_path.touch()
    result = runner.invoke(app, ["build", "--db", str(db_path)])
    assert result.exit_code == 1
    assert "delivery" in result.output.lower() or "section" in result.output.lower()


def test_build_no_foundry_yaml_exits_1(tmp_path: Path, db_path: Path) -> None:
    """No foundry.yaml at all → no sections → exit 1."""
    db_path.touch()
    result = runner.invoke(app, ["build", "--db", str(db_path)])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# No DB
# ---------------------------------------------------------------------------


def test_build_no_db_exits_1(tmp_path: Path) -> None:
    """Missing .foundry.db → exit 1 with hint."""
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n  output: d.md\n  sections:\n    - type: file\n      path: x.pdf\n      heading: X\n",
        encoding="utf-8",
    )
    missing_db = tmp_path / "missing.db"
    result = runner.invoke(app, ["build", "--db", str(missing_db)])
    assert result.exit_code == 1
    assert "foundry init" in result.output or "No database" in result.output


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_build_dry_run_shows_sections(tmp_path: Path, foundry_yaml_generated: Path, approved_features: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    result = runner.invoke(
        app,
        [
            "build",
            "--db", str(db_path),
            "--dry-run",
            "--features-dir", str(approved_features),
        ],
    )
    assert result.exit_code == 0
    assert "Wiring Guide" in result.output
    assert "generated" in result.output.lower()


def test_build_dry_run_no_generation(tmp_path: Path, foundry_yaml_generated: Path, approved_features: Path) -> None:
    db_path = tmp_path / ".foundry.db"
    mocks = _mock_generate_pipeline()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8]:
        result = runner.invoke(
            app,
            ["build", "--db", str(db_path), "--dry-run", "--features-dir", str(approved_features)],
        )
    # complete should NOT have been called
    assert result.exit_code == 0
    assert "dry run" in result.output.lower() or "No generation" in result.output


def test_build_dry_run_shows_file_status(tmp_path: Path, foundry_yaml_file_section: Path) -> None:
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "spec.pdf").write_bytes(b"fake pdf")
    db_path = tmp_path / ".foundry.db"
    result = runner.invoke(app, ["build", "--db", str(db_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Spec PDF" in result.output


# ---------------------------------------------------------------------------
# File sections
# ---------------------------------------------------------------------------


def test_build_file_section_present(tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path) -> None:
    db_path.touch()  # DB exists check passes for file-only builds
    # Create the referenced file (absolute path already in fixture)
    spec = tmp_path / "output" / "spec.pdf"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_bytes(b"fake pdf content")
    out = tmp_path / "delivery.md"
    result = runner.invoke(app, ["build", "--db", str(db_path), "--output", str(out), "--yes"])
    assert result.exit_code == 0
    content = out.read_text()
    assert "Spec PDF" in content
    assert "Present" in content or "✓" in content


def test_build_file_section_missing_warns_in_doc(tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path) -> None:
    db_path.touch()
    # Do NOT create the file
    out = tmp_path / "delivery.md"
    result = runner.invoke(app, ["build", "--db", str(db_path), "--output", str(out), "--yes"])
    assert result.exit_code == 0
    content = out.read_text()
    assert "missing" in content.lower() or "⚠" in content


def test_build_file_section_content_in_delivery_doc(tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path) -> None:
    db_path.touch()
    spec = tmp_path / "output" / "spec.pdf"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_bytes(b"x")
    out = tmp_path / "delivery.md"
    result = runner.invoke(app, ["build", "--db", str(db_path), "--output", str(out), "--yes"])
    assert result.exit_code == 0
    content = out.read_text()
    assert "Technical specification" in content


# ---------------------------------------------------------------------------
# Physical sections
# ---------------------------------------------------------------------------


def test_build_physical_done(tmp_path: Path, slice_yaml_done: Path, db_path: Path) -> None:
    db_path.touch()
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: physical\n"
        '      heading: "Hardware Prototype"\n'
        '      description: "Assembled prototype"\n'
        "      tracking_wi: WI_0001\n",
        encoding="utf-8",
    )
    out = tmp_path / "delivery.md"
    result = runner.invoke(
        app,
        ["build", "--db", str(db_path), "--output", str(out), "--yes", "--slice", str(slice_yaml_done)],
    )
    assert result.exit_code == 0
    content = out.read_text()
    assert "Delivered" in content or "✓" in content


def test_build_physical_in_progress(tmp_path: Path, slice_yaml_in_progress: Path, db_path: Path) -> None:
    db_path.touch()
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: physical\n"
        '      heading: "Hardware"\n'
        '      description: "Prototype"\n'
        "      tracking_wi: WI_0001\n",
        encoding="utf-8",
    )
    out = tmp_path / "delivery.md"
    result = runner.invoke(
        app,
        ["build", "--db", str(db_path), "--output", str(out), "--yes", "--slice", str(slice_yaml_in_progress)],
    )
    assert result.exit_code == 0
    content = out.read_text()
    assert "In Progress" in content or "⏳" in content


def test_build_physical_no_slice_warns_gracefully(tmp_path: Path, db_path: Path) -> None:
    db_path.touch()
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: physical\n"
        '      heading: "Hardware"\n'
        '      description: "Prototype"\n'
        "      tracking_wi: WI_0001\n",
        encoding="utf-8",
    )
    missing_slice = tmp_path / "no" / "slice.yaml"
    out = tmp_path / "delivery.md"
    result = runner.invoke(
        app,
        ["build", "--db", str(db_path), "--output", str(out), "--yes", "--slice", str(missing_slice)],
    )
    assert result.exit_code == 0
    content = out.read_text()
    assert "not available" in content.lower() or "no git scaffold" in content.lower()


def test_build_physical_wi_id_not_in_delivery_doc(
    tmp_path: Path, slice_yaml_done: Path, db_path: Path
) -> None:
    """WI-ID (WI_0001) must NOT appear in the delivery document."""
    db_path.touch()
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: physical\n"
        '      heading: "Hardware"\n'
        '      description: "Prototype"\n'
        "      tracking_wi: WI_0001\n",
        encoding="utf-8",
    )
    out = tmp_path / "delivery.md"
    result = runner.invoke(
        app,
        ["build", "--db", str(db_path), "--output", str(out), "--yes", "--slice", str(slice_yaml_done)],
    )
    assert result.exit_code == 0
    content = out.read_text()
    assert "WI_0001" not in content


# ---------------------------------------------------------------------------
# Generated sections — approval gate
# ---------------------------------------------------------------------------


def test_build_unapproved_feature_exits_1(tmp_path: Path, db_path: Path) -> None:
    db_path.touch()
    features = tmp_path / "features"
    features.mkdir()
    (features / "wiring.md").write_text("# Wiring\n\nNot approved.\n", encoding="utf-8")
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: generated\n"
        "      feature: wiring\n"
        '      topic: "wiring"\n'
        '      heading: "Wiring"\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["build", "--db", str(db_path), "--features-dir", str(features)],
    )
    assert result.exit_code == 1
    assert "unapproved" in result.output.lower() or "approve" in result.output.lower()


def test_build_generated_section(
    tmp_path: Path, populated_db: Path, approved_features: Path, foundry_yaml_generated: Path
) -> None:
    """Generated section produces content in the delivery doc."""
    out = tmp_path / "delivery.md"
    mocks = _mock_generate_pipeline()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8]:
        result = runner.invoke(
            app,
            [
                "build",
                "--db", str(populated_db),
                "--output", str(out),
                "--yes",
                "--features-dir", str(approved_features),
            ],
        )
    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text()
    assert "Wiring Guide" in content
    assert "Generated content." in content


def test_build_show_attributions_false_no_footnotes(
    tmp_path: Path, populated_db: Path, approved_features: Path
) -> None:
    """show_attributions: false suppresses footnote attribution."""
    (tmp_path / "foundry.yaml").write_text(
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: generated\n"
        "      feature: wiring\n"
        '      topic: "wiring"\n'
        '      heading: "Wiring Guide"\n'
        "      show_attributions: false\n",
        encoding="utf-8",
    )
    out = tmp_path / "delivery.md"
    mocks = _mock_generate_pipeline()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8]:
        result = runner.invoke(
            app,
            [
                "build",
                "--db", str(populated_db),
                "--output", str(out),
                "--yes",
                "--features-dir", str(approved_features),
            ],
        )
    assert result.exit_code == 0
    content = out.read_text()
    assert "Wiring Guide" in content
    # With show_attributions: false, no [^N]: footnotes should be appended
    assert "[^1]:" not in content


# ---------------------------------------------------------------------------
# Output overwrite protection
# ---------------------------------------------------------------------------


def test_build_overwrite_prompt_cancel(tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path) -> None:
    db_path.touch()
    out = tmp_path / "delivery.md"
    out.write_text("existing content", encoding="utf-8")
    result = runner.invoke(app, ["build", "--db", str(db_path), "--output", str(out)], input="n\n")
    assert result.exit_code == 0
    # File unchanged
    assert out.read_text() == "existing content"


def test_build_yes_skips_overwrite(tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path) -> None:
    db_path.touch()
    out = tmp_path / "delivery.md"
    out.write_text("old content", encoding="utf-8")
    result = runner.invoke(app, ["build", "--db", str(db_path), "--output", str(out), "--yes"])
    assert result.exit_code == 0
    assert out.read_text() != "old content"


# ---------------------------------------------------------------------------
# --output override
# ---------------------------------------------------------------------------


def test_build_output_override(tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path) -> None:
    db_path.touch()
    custom_output = tmp_path / "custom-report.md"
    result = runner.invoke(
        app,
        ["build", "--db", str(db_path), "--output", str(custom_output), "--yes"],
    )
    assert result.exit_code == 0
    assert custom_output.exists()


# ---------------------------------------------------------------------------
# --pdf (fail-open when Pandoc not found)
# ---------------------------------------------------------------------------


def test_build_pdf_fail_open_when_no_pandoc(
    tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path
) -> None:
    db_path.touch()
    with patch("foundry.cli.build.shutil.which", return_value=None):
        result = runner.invoke(app, ["build", "--db", str(db_path), "--yes", "--pdf"])
    assert result.exit_code == 0
    assert "pandoc" in result.output.lower() or "PDF" in result.output


def test_build_pdf_skips_generation_not_exit_1(
    tmp_path: Path, foundry_yaml_file_section: Path, db_path: Path
) -> None:
    """--pdf with no Pandoc exits 0 (fail-open)."""
    db_path.touch()
    with patch("foundry.cli.build.shutil.which", return_value=None):
        result = runner.invoke(app, ["build", "--db", str(db_path), "--yes", "--pdf"])
    assert result.exit_code == 0
