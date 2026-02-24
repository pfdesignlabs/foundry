"""Tests for JsonChunker (WI_0019)."""

from __future__ import annotations

import json

import pytest

from foundry.db.models import Chunk
from foundry.ingest.json_chunker import JsonChunker


def test_json_default_settings():
    assert JsonChunker().chunk_size == 300
    assert JsonChunker().overlap == 0.0


def test_json_empty_content():
    assert JsonChunker().chunk("src-1", "") == []
    assert JsonChunker().chunk("src-1", "   ") == []


def test_json_returns_list_of_chunks():
    chunks = JsonChunker().chunk("src-1", '[{"a": 1}]')
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_json_source_id_set():
    chunks = JsonChunker().chunk("my-source", '[{"x": 1}]')
    assert all(c.source_id == "my-source" for c in chunks)


def test_json_chunk_index_sequential():
    # chunk_size=1 → each item its own chunk
    data = json.dumps([{"id": i, "val": "x" * 20} for i in range(5)])
    chunks = JsonChunker(chunk_size=1).chunk("src-1", data)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_json_array_of_objects_splits():
    # 5 objects, chunk_size=1 → each object in its own chunk
    data = json.dumps([{"id": i} for i in range(5)])
    chunks = JsonChunker(chunk_size=1).chunk("src-1", data)
    assert len(chunks) == 5


def test_json_array_of_objects_groups():
    # Small objects, large chunk_size → all grouped in one chunk
    data = json.dumps([{"id": i} for i in range(3)])
    chunks = JsonChunker(chunk_size=512).chunk("src-1", data)
    assert len(chunks) == 1
    for i in range(3):
        assert str(i) in chunks[0].text


def test_json_flat_dict_splits():
    # key-value pairs, chunk_size=1 → each pair its own chunk
    data = json.dumps({f"key{i}": f"value{i}" * 10 for i in range(4)})
    chunks = JsonChunker(chunk_size=1).chunk("src-1", data)
    assert len(chunks) == 4


def test_json_flat_dict_grouped():
    data = json.dumps({"a": 1, "b": 2, "c": 3})
    chunks = JsonChunker(chunk_size=512).chunk("src-1", data)
    assert len(chunks) == 1
    assert '"a"' in chunks[0].text
    assert '"b"' in chunks[0].text


def test_json_scalar_string():
    chunks = JsonChunker().chunk("src-1", '"hello world"')
    assert len(chunks) == 1
    assert "hello world" in chunks[0].text


def test_json_scalar_number():
    chunks = JsonChunker().chunk("src-1", "42")
    assert len(chunks) == 1


def test_json_invalid_json_fallback_fixed_window():
    # Invalid JSON → plain text fixed window
    chunker = JsonChunker(chunk_size=5, overlap=0.0)
    bad_json = "not json at all " * 20
    chunks = chunker.chunk("src-1", bad_json)
    assert len(chunks) > 0
    assert all(isinstance(c, Chunk) for c in chunks)


def test_json_array_of_scalars():
    data = json.dumps([1, 2, 3, 4, 5])
    chunks = JsonChunker(chunk_size=512).chunk("src-1", data)
    assert len(chunks) == 1
