"""Tests for gates/parser.py (WI_0030)."""

from __future__ import annotations

from pathlib import Path

import pytest

from foundry.gates.parser import FeatureSpec, load_all_specs, parse_spec


# ------------------------------------------------------------------
# parse_spec — single file
# ------------------------------------------------------------------


def _write_spec(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_spec_not_approved(tmp_path: Path) -> None:
    p = _write_spec(tmp_path, "wiring", "# Wiring Guide\n\nSome content.\n")
    spec = parse_spec(p)
    assert spec.name == "wiring"
    assert spec.approved is False
    assert spec.approved_on is None
    assert "Wiring Guide" in spec.content


def test_parse_spec_approved_with_date(tmp_path: Path) -> None:
    content = "# Wiring Guide\n\n## Approved\nGoedgekeurd op 2026-03-15\n"
    p = _write_spec(tmp_path, "wiring", content)
    spec = parse_spec(p)
    assert spec.approved is True
    assert spec.approved_on == "Goedgekeurd op 2026-03-15"


def test_parse_spec_approved_without_date(tmp_path: Path) -> None:
    content = "# Wiring Guide\n\n## Approved\n"
    p = _write_spec(tmp_path, "wiring", content)
    spec = parse_spec(p)
    assert spec.approved is True
    assert spec.approved_on is None


def test_parse_spec_approved_exact_heading_only(tmp_path: Path) -> None:
    """## Approved must be exact — trailing text should not match."""
    content = "# Guide\n\n## Approved by someone\n"
    p = _write_spec(tmp_path, "guide", content)
    spec = parse_spec(p)
    assert spec.approved is False


def test_parse_spec_approved_wrong_case(tmp_path: Path) -> None:
    """## approved (lowercase) must not match."""
    content = "# Guide\n\n## approved\n"
    p = _write_spec(tmp_path, "guide", content)
    spec = parse_spec(p)
    assert spec.approved is False


def test_parse_spec_approved_wrong_level(tmp_path: Path) -> None:
    """# Approved (H1) must not match."""
    content = "# Approved\n"
    p = _write_spec(tmp_path, "guide", content)
    spec = parse_spec(p)
    assert spec.approved is False


def test_parse_spec_approved_h3_no_match(tmp_path: Path) -> None:
    """### Approved (H3) must not match."""
    content = "### Approved\n"
    p = _write_spec(tmp_path, "guide", content)
    spec = parse_spec(p)
    assert spec.approved is False


def test_parse_spec_approved_trailing_whitespace_ok(tmp_path: Path) -> None:
    """## Approved with trailing spaces should still match."""
    content = "# Guide\n\n## Approved   \nGoedgekeurd op 2026-03-10\n"
    p = _write_spec(tmp_path, "guide", content)
    spec = parse_spec(p)
    assert spec.approved is True


def test_parse_spec_name_is_stem(tmp_path: Path) -> None:
    p = _write_spec(tmp_path, "firmware-arch", "# Firmware\n\n## Approved\n")
    spec = parse_spec(p)
    assert spec.name == "firmware-arch"


def test_parse_spec_path_preserved(tmp_path: Path) -> None:
    p = _write_spec(tmp_path, "test-spec", "# Test\n")
    spec = parse_spec(p)
    assert spec.path == p


def test_parse_spec_oserror(tmp_path: Path) -> None:
    missing = tmp_path / "missing.md"
    with pytest.raises(OSError):
        parse_spec(missing)


# ------------------------------------------------------------------
# load_all_specs
# ------------------------------------------------------------------


def test_load_all_specs_empty_dir(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    specs = load_all_specs(features)
    assert specs == []


def test_load_all_specs_dir_not_exists(tmp_path: Path) -> None:
    specs = load_all_specs(tmp_path / "nonexistent")
    assert specs == []


def test_load_all_specs_returns_all_files(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    (features / "a.md").write_text("# A\n", encoding="utf-8")
    (features / "b.md").write_text("# B\n\n## Approved\n2026-03-01\n", encoding="utf-8")
    specs = load_all_specs(features)
    assert len(specs) == 2
    names = {s.name for s in specs}
    assert names == {"a", "b"}


def test_load_all_specs_sorted_alphabetically(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    for name in ["zebra", "alpha", "middle"]:
        (features / f"{name}.md").write_text("# X\n", encoding="utf-8")
    specs = load_all_specs(features)
    assert [s.name for s in specs] == ["alpha", "middle", "zebra"]


def test_load_all_specs_only_md_files(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    (features / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (features / "notes.txt").write_text("ignored\n", encoding="utf-8")
    specs = load_all_specs(features)
    assert len(specs) == 1
    assert specs[0].name == "spec"


def test_load_all_specs_mixed_approved(tmp_path: Path) -> None:
    features = tmp_path / "features"
    features.mkdir()
    (features / "approved.md").write_text("# A\n\n## Approved\n2026-03-01\n", encoding="utf-8")
    (features / "pending.md").write_text("# P\n\nNot yet.\n", encoding="utf-8")
    specs = load_all_specs(features)
    approved = [s for s in specs if s.approved]
    pending = [s for s in specs if not s.approved]
    assert len(approved) == 1
    assert len(pending) == 1
    assert approved[0].name == "approved"
