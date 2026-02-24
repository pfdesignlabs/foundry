"""Feature spec parser (WI_0030).

Reads *.md files from a project's features/ directory.
Detects approval via exact heading match: ^## Approved$ (case-sensitive, no trailing text).

Approval date is read from the line immediately following the ## Approved heading,
if present and non-empty.

Usage:
    specs = load_all_specs(Path("features"))
    for spec in specs:
        print(spec.name, spec.approved, spec.approved_on)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Exact match: line that IS "## Approved" with nothing else (strips trailing whitespace)
_APPROVED_RE = re.compile(r"^## Approved\s*$", re.MULTILINE)


@dataclass
class FeatureSpec:
    name: str            # filename without .md extension
    path: Path
    content: str
    approved: bool
    approved_on: str | None = field(default=None)  # date string if found, else None


def parse_spec(path: Path) -> FeatureSpec:
    """Parse a single feature spec file.

    Args:
        path: Path to the .md spec file.

    Returns:
        FeatureSpec with approval status and optional date.

    Raises:
        OSError: if the file cannot be read.
    """
    content = path.read_text(encoding="utf-8")
    name = path.stem

    match = _APPROVED_RE.search(content)
    if not match:
        return FeatureSpec(name=name, path=path, content=content, approved=False)

    # Try to read the date from the line immediately after "## Approved"
    after = content[match.end():]
    date_line = after.lstrip("\r").lstrip("\n")
    # Take first non-empty line after the heading
    first_line = date_line.split("\n", 1)[0].strip()
    approved_on = first_line if first_line else None

    return FeatureSpec(
        name=name,
        path=path,
        content=content,
        approved=True,
        approved_on=approved_on,
    )


def load_all_specs(features_dir: Path) -> list[FeatureSpec]:
    """Load all *.md feature specs from a directory.

    Returns an empty list if the directory does not exist.
    Files that cannot be read are silently skipped.
    """
    if not features_dir.is_dir():
        return []

    specs = []
    for md_file in sorted(features_dir.glob("*.md")):
        try:
            specs.append(parse_spec(md_file))
        except OSError:
            continue
    return specs
