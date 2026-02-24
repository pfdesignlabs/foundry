"""Tests for DocumentSummarizer (WI_0022a)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Source
from foundry.db.repository import Repository
from foundry.ingest.summarizer import DocumentSummarizer


@pytest.fixture
def repo(tmp_db):
    r = Repository(tmp_db)
    r.add_source(
        Source(id="src-1", path="doc.pdf", content_hash="abc", embedding_model="openai/text-embedding-3-small")
    )
    return r


def _mock_completion(text: str):
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = text
    return patch("foundry.ingest.summarizer.litellm.completion", return_value=mock)


def test_summarize_returns_summary(repo):
    with _mock_completion("This document describes the DMX512 protocol."):
        summarizer = DocumentSummarizer(repo)
        result = summarizer.summarize("src-1", "Full document text about DMX512.")
    assert result == "This document describes the DMX512 protocol."


def test_summarize_stores_in_db(repo):
    with _mock_completion("Summary of the document."):
        DocumentSummarizer(repo).summarize("src-1", "Document text.")
    stored = repo.get_summary("src-1")
    assert stored == "Summary of the document."


def test_summarize_upserts_on_second_call(repo):
    with _mock_completion("First summary."):
        DocumentSummarizer(repo).summarize("src-1", "Text v1.")
    with _mock_completion("Updated summary."):
        DocumentSummarizer(repo).summarize("src-1", "Text v2.")
    assert repo.get_summary("src-1") == "Updated summary."


def test_summarize_llm_failure_stores_empty(repo):
    with patch("foundry.ingest.summarizer.litellm.completion", side_effect=Exception("API error")):
        result = DocumentSummarizer(repo).summarize("src-1", "Document text.")
    assert result == ""
    assert repo.get_summary("src-1") == ""


def test_summarize_custom_model(repo):
    with _mock_completion("Summary.") as mock_call:
        DocumentSummarizer(repo, model="openai/gpt-4o").summarize("src-1", "text")
    call_kwargs = mock_call.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"


def test_summarize_max_tokens_passed(repo):
    with _mock_completion("Summary.") as mock_call:
        DocumentSummarizer(repo, max_tokens=200).summarize("src-1", "text")
    call_kwargs = mock_call.call_args[1]
    assert call_kwargs["max_tokens"] == 200


def test_summarize_truncates_long_text(repo):
    long_text = "x" * 20000
    with _mock_completion("Summary.") as mock_call:
        DocumentSummarizer(repo).summarize("src-1", long_text)
    prompt = mock_call.call_args[1]["messages"][0]["content"]
    # Prompt should use only first 8000 chars of document
    assert len(prompt) < 20000
