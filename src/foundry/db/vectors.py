"""Per-model sqlite-vec virtual table management (WI_0012a)."""

from __future__ import annotations

import re
import sqlite3


def model_to_slug(model: str) -> str:
    """Convert a provider/model string to a valid table name suffix.

    Examples:
        "openai/text-embedding-3-small" -> "openai_text_embedding_3_small"
        "openai/text-embedding-3-large" -> "openai_text_embedding_3_large"
    """
    return re.sub(r"[^a-z0-9]", "_", model.lower())


def vec_table_name(model_slug: str) -> str:
    """Return the full vec table name for a model slug."""
    return f"vec_chunks_{model_slug}"


def ensure_vec_table(conn: sqlite3.Connection, model_slug: str, dimensions: int) -> str:
    """Create vec_chunks_{model_slug} virtual table if it doesn't already exist.

    Args:
        conn: Active database connection (sqlite-vec must be loaded).
        model_slug: Sanitized model identifier (use model_to_slug() to generate).
        dimensions: Embedding vector dimensions (e.g. 1536 for text-embedding-3-small).

    Returns:
        The table name (vec_chunks_{model_slug}).
    """
    if not re.fullmatch(r"[a-z0-9_]+", model_slug):
        raise ValueError(
            f"Invalid model_slug '{model_slug}' — use model_to_slug() to sanitize."
        )
    if dimensions < 1:
        raise ValueError(f"dimensions must be >= 1, got {dimensions}")

    table = vec_table_name(model_slug)
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()

    if existing is None:
        conn.execute(
            f"CREATE VIRTUAL TABLE {table} USING vec0(embedding float[{dimensions}])"
        )
        conn.commit()

    return table
