"""Output writer: Markdown with footnote attribution + security guards (WI_0028).

Responsibilities:
  1. Receive raw LLM output (Markdown string) and a list of source chunks.
  2. Append footnote-style source attribution: [^1] inline → [^1]: source §chunk
  3. Validate output path: confine to CWD or an explicitly allowed directory.
     Path traversal (../../etc/passwd) → hard fail.
  4. Overwrite protection: if file exists, prompt user (--yes skips).
  5. Write final document atomically (temp file → rename).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import typer

from foundry.db.models import Chunk


# ------------------------------------------------------------------
# Attribution
# ------------------------------------------------------------------


def add_attribution(content: str, chunks: list[Chunk]) -> str:
    """Append footnote attribution block to *content*.

    If the LLM output already contains [^N] references, we leave them as-is
    and just append the source list. If not, we append a plain sources section.

    Format:
      [^1]: source_id, chunk N
      [^2]: source_id, chunk M
    """
    if not chunks:
        return content

    footnotes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        source_label = _short_source_label(chunk)
        footnotes.append(f"[^{i}]: {source_label}")

    attribution_block = "\n\n---\n\n" + "\n".join(footnotes)
    return content.rstrip() + attribution_block


def _short_source_label(chunk: Chunk) -> str:
    """Return a human-readable source label for footnote attribution."""
    # Use last path component if the source_id looks like a file path
    source = chunk.source_id
    if "/" in source or "\\" in source:
        source = Path(source).name
    return f"{source}, chunk {chunk.chunk_index}"


# ------------------------------------------------------------------
# Path validation (security — path traversal prevention)
# ------------------------------------------------------------------


def validate_output_path(output: str, allowed_base: Path | None = None) -> Path:
    """Normalize and validate the output path.

    Security model:
    - Absolute paths are accepted as-is (user explicitly chose the location).
    - Relative paths are confined to *allowed_base* (default: CWD).
      Traversal sequences like '../../etc/passwd' are hard-blocked.

    Args:
        output: The raw output path string from the user.
        allowed_base: Base directory to confine relative paths to. Defaults to CWD.

    Returns:
        Resolved absolute Path.

    Raises:
        ValueError: If a relative path escapes the allowed base directory.
    """
    path = Path(output)

    if path.is_absolute():
        return path.resolve()

    # Relative path — confine to allowed_base
    if allowed_base is None:
        allowed_base = Path.cwd()

    allowed_base = allowed_base.resolve()
    resolved = (allowed_base / path).resolve()

    try:
        resolved.relative_to(allowed_base)
    except ValueError:
        raise ValueError(
            f"Output path '{output}' resolves outside the allowed directory "
            f"('{allowed_base}'). Path traversal is not permitted."
        )

    return resolved


# ------------------------------------------------------------------
# Overwrite guard
# ------------------------------------------------------------------


def check_overwrite(path: Path, yes: bool) -> bool:
    """Return True if we should proceed with writing, False if user declines.

    If *yes* is True, skip the prompt and return True.
    If the file does not exist, return True.
    Otherwise, ask the user.
    """
    if yes or not path.exists():
        return True

    confirmed = typer.confirm(f"  File exists: {path.name}\n  Overwrite?", default=False)
    return confirmed


# ------------------------------------------------------------------
# Atomic write
# ------------------------------------------------------------------


def write_output(path: Path, content: str) -> None:
    """Write *content* to *path* atomically (temp → rename).

    Creates parent directories if needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory, then rename
    dir_ = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
