"""Tests for output writer (WI_0028)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from foundry.db.models import Chunk
from foundry.generate.writer import (
    _short_source_label,
    add_attribution,
    check_overwrite,
    validate_output_path,
    write_output,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _chunk(source_id: str = "doc.pdf", chunk_index: int = 0) -> Chunk:
    return Chunk(source_id=source_id, chunk_index=chunk_index, text="text")


# ------------------------------------------------------------------
# _short_source_label
# ------------------------------------------------------------------


def test_short_source_label_plain_id():
    chunk = _chunk("my-source", 3)
    assert _short_source_label(chunk) == "my-source, chunk 3"


def test_short_source_label_file_path():
    chunk = _chunk("/long/path/to/datasheet.pdf", 5)
    label = _short_source_label(chunk)
    assert "datasheet.pdf" in label
    assert "/long/path" not in label


def test_short_source_label_url_like():
    chunk = _chunk("https://example.com/doc", 1)
    label = _short_source_label(chunk)
    assert "chunk 1" in label


# ------------------------------------------------------------------
# add_attribution
# ------------------------------------------------------------------


def test_add_attribution_no_chunks():
    result = add_attribution("Some content.", [])
    assert result == "Some content."


def test_add_attribution_appends_footnotes():
    chunks = [_chunk("a.pdf", 0), _chunk("b.pdf", 2)]
    result = add_attribution("Content here.", chunks)
    assert "[^1]: a.pdf, chunk 0" in result
    assert "[^2]: b.pdf, chunk 2" in result


def test_add_attribution_separator_present():
    result = add_attribution("Body text.", [_chunk()])
    assert "---" in result


def test_add_attribution_preserves_content():
    content = "# Heading\n\nSome text."
    result = add_attribution(content, [_chunk()])
    assert "# Heading" in result
    assert "Some text." in result


def test_add_attribution_footnotes_numbered_sequentially():
    chunks = [_chunk(f"src{i}", i) for i in range(5)]
    result = add_attribution("text", chunks)
    for i in range(1, 6):
        assert f"[^{i}]:" in result


# ------------------------------------------------------------------
# validate_output_path
# ------------------------------------------------------------------


def test_validate_output_path_simple_name(tmp_path):
    resolved = validate_output_path("output.md", allowed_base=tmp_path)
    assert resolved == tmp_path / "output.md"


def test_validate_output_path_subdir(tmp_path):
    resolved = validate_output_path("drafts/output.md", allowed_base=tmp_path)
    assert resolved == tmp_path / "drafts" / "output.md"


def test_validate_output_path_traversal_blocked(tmp_path):
    with pytest.raises(ValueError, match="Path traversal"):
        validate_output_path("../../etc/passwd", allowed_base=tmp_path)


def test_validate_output_path_absolute_accepted(tmp_path):
    # Absolute paths are accepted as-is (user explicitly chose the location)
    inside = str(tmp_path / "output.md")
    resolved = validate_output_path(inside, allowed_base=tmp_path)
    assert resolved == (tmp_path / "output.md").resolve()


def test_validate_output_path_absolute_inside_allowed(tmp_path):
    inside = str(tmp_path / "output.md")
    resolved = validate_output_path(inside, allowed_base=tmp_path)
    assert resolved == tmp_path / "output.md"


def test_validate_output_path_defaults_to_cwd():
    # Should not raise for a simple relative path
    resolved = validate_output_path("output.md")
    assert resolved.name == "output.md"
    assert resolved.is_absolute()


# ------------------------------------------------------------------
# check_overwrite
# ------------------------------------------------------------------


def test_check_overwrite_file_not_exists(tmp_path):
    path = tmp_path / "new.md"
    assert check_overwrite(path, yes=False) is True


def test_check_overwrite_yes_flag_skips_prompt(tmp_path):
    path = tmp_path / "exists.md"
    path.write_text("old content")
    assert check_overwrite(path, yes=True) is True


def test_check_overwrite_user_confirms(tmp_path):
    path = tmp_path / "exists.md"
    path.write_text("old content")
    with patch("foundry.generate.writer.typer.confirm", return_value=True):
        assert check_overwrite(path, yes=False) is True


def test_check_overwrite_user_declines(tmp_path):
    path = tmp_path / "exists.md"
    path.write_text("old content")
    with patch("foundry.generate.writer.typer.confirm", return_value=False):
        assert check_overwrite(path, yes=False) is False


# ------------------------------------------------------------------
# write_output
# ------------------------------------------------------------------


def test_write_output_creates_file(tmp_path):
    path = tmp_path / "output.md"
    write_output(path, "# Hello\n\nContent.")
    assert path.exists()
    assert path.read_text() == "# Hello\n\nContent."


def test_write_output_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "output.md"
    write_output(path, "content")
    assert path.exists()


def test_write_output_overwrites_existing(tmp_path):
    path = tmp_path / "output.md"
    path.write_text("old")
    write_output(path, "new content")
    assert path.read_text() == "new content"


def test_write_output_no_temp_files_on_success(tmp_path):
    path = tmp_path / "output.md"
    write_output(path, "content")
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []
