"""Tests for per-model sqlite-vec virtual tables (WI_0012a)."""

from __future__ import annotations

import pytest

from foundry.db.vectors import ensure_vec_table, model_to_slug, vec_table_name


# --- model_to_slug ---

@pytest.mark.parametrize("model,expected", [
    ("openai/text-embedding-3-small", "openai_text_embedding_3_small"),
    ("openai/text-embedding-3-large", "openai_text_embedding_3_large"),
    ("cohere/embed-english-v3.0", "cohere_embed_english_v3_0"),
    ("local/all-MiniLM-L6-v2", "local_all_minilm_l6_v2"),
])
def test_model_to_slug(model, expected):
    assert model_to_slug(model) == expected


def test_vec_table_name():
    slug = model_to_slug("openai/text-embedding-3-small")
    assert vec_table_name(slug) == "vec_chunks_openai_text_embedding_3_small"


# --- ensure_vec_table ---

def test_ensure_vec_table_creates_table(tmp_db):
    slug = model_to_slug("openai/text-embedding-3-small")
    table = ensure_vec_table(tmp_db, slug, dimensions=1536)
    assert table == "vec_chunks_openai_text_embedding_3_small"
    row = tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    assert row is not None


def test_ensure_vec_table_idempotent(tmp_db):
    slug = model_to_slug("openai/text-embedding-3-small")
    table1 = ensure_vec_table(tmp_db, slug, dimensions=1536)
    table2 = ensure_vec_table(tmp_db, slug, dimensions=1536)
    assert table1 == table2


def test_ensure_vec_table_multiple_models(tmp_db):
    slug_small = model_to_slug("openai/text-embedding-3-small")
    slug_large = model_to_slug("openai/text-embedding-3-large")
    ensure_vec_table(tmp_db, slug_small, dimensions=1536)
    ensure_vec_table(tmp_db, slug_large, dimensions=3072)
    for slug in (slug_small, slug_large):
        row = tmp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (f"vec_chunks_{slug}",),
        ).fetchone()
        assert row is not None


def test_ensure_vec_table_insert_and_lookup(tmp_db):
    import json
    slug = model_to_slug("openai/text-embedding-3-small")
    table = ensure_vec_table(tmp_db, slug, dimensions=4)

    # Insert with explicit rowid matching chunks.rowid
    embedding = "[0.1, 0.2, 0.3, 0.4]"
    tmp_db.execute(f"INSERT INTO {table}(rowid, embedding) VALUES (42, ?)", (embedding,))

    row = tmp_db.execute(
        f"SELECT rowid FROM {table} WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
        (embedding,),
    ).fetchone()
    assert row[0] == 42


def test_ensure_vec_table_invalid_slug(tmp_db):
    with pytest.raises(ValueError, match="model_slug"):
        ensure_vec_table(tmp_db, "invalid/slug!", dimensions=128)


def test_ensure_vec_table_invalid_dimensions(tmp_db):
    with pytest.raises(ValueError, match="dimensions"):
        ensure_vec_table(tmp_db, "valid_slug", dimensions=0)
