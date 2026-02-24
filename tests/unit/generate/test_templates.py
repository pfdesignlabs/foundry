"""Tests for prompt templates (WI_0027)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from foundry.db.models import Chunk
from foundry.generate.templates import (
    PromptConfig,
    PromptComponents,
    TokenBudgetBreakdown,
    _format_chunks,
    _format_summaries,
    _load_brief,
    build_prompt,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _chunk(rowid: int, text: str = "chunk content", source_id: str = "src") -> Chunk:
    return Chunk(source_id=source_id, chunk_index=rowid, text=text, rowid=rowid)


def _patch_tokens(n: int):
    return patch("foundry.generate.templates.count_tokens", return_value=n)


def _patch_window(n: int):
    return patch("foundry.generate.templates.get_context_window", return_value=n)


# ------------------------------------------------------------------
# _load_brief
# ------------------------------------------------------------------


def test_load_brief_returns_empty_if_none():
    result = _load_brief(None, 3000, "openai/gpt-4o")
    assert result == ""


def test_load_brief_returns_empty_if_file_missing(tmp_path):
    result = _load_brief(str(tmp_path / "nonexistent.md"), 3000, "openai/gpt-4o")
    assert result == ""


def test_load_brief_reads_local_file(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Project context here.")

    with patch("foundry.generate.templates.count_tokens", return_value=10):
        result = _load_brief(str(brief), 3000, "openai/gpt-4o")

    assert result == "Project context here."


def test_load_brief_truncates_if_too_long(tmp_path):
    brief = tmp_path / "brief.md"
    text = " ".join(["word"] * 200)
    brief.write_text(text)

    with patch("foundry.generate.templates.count_tokens", return_value=500):
        result = _load_brief(str(brief), 100, "openai/gpt-4o")

    assert "[brief truncated" in result


def test_load_brief_rejects_http_url():
    with pytest.raises(ValueError, match="local file path"):
        _load_brief("https://example.com/brief.md", 3000, "openai/gpt-4o")


def test_load_brief_rejects_https_url():
    with pytest.raises(ValueError, match="local file path"):
        _load_brief("https://example.com/brief.md", 3000, "openai/gpt-4o")


def test_load_brief_rejects_git_at_url():
    with pytest.raises(ValueError, match="local file path"):
        _load_brief("git@github.com:user/repo.git", 3000, "openai/gpt-4o")


# ------------------------------------------------------------------
# _format_summaries
# ------------------------------------------------------------------


def test_format_summaries_empty():
    assert _format_summaries([]) == ""


def test_format_summaries_formats_as_bullets():
    result = _format_summaries(["Summary A.", "Summary B."])
    assert "- Summary A." in result
    assert "- Summary B." in result


# ------------------------------------------------------------------
# _format_chunks
# ------------------------------------------------------------------


def test_format_chunks_empty():
    assert _format_chunks([]) == ""


def test_format_chunks_includes_source_label():
    chunk = _chunk(1, text="The voltage is 3.3V.", source_id="datasheet.pdf")
    result = _format_chunks([chunk])
    assert "datasheet.pdf" in result
    assert "The voltage is 3.3V." in result
    assert "[1]" in result


def test_format_chunks_numbered_sequentially():
    chunks = [_chunk(i) for i in range(3)]
    result = _format_chunks(chunks)
    assert "[1]" in result
    assert "[2]" in result
    assert "[3]" in result


# ------------------------------------------------------------------
# TokenBudgetBreakdown.total
# ------------------------------------------------------------------


def test_token_budget_breakdown_total():
    bd = TokenBudgetBreakdown(
        brief_tokens=100,
        feature_spec_tokens=200,
        summaries_tokens=300,
        chunk_budget=400,
    )
    assert bd.total == 1000


# ------------------------------------------------------------------
# build_prompt — structure
# ------------------------------------------------------------------


def test_build_prompt_includes_context_tags():
    chunks = [_chunk(1, "relevant content")]
    with (
        _patch_tokens(50),
        _patch_window(128_000),
    ):
        result = build_prompt("What is the voltage?", chunks, PromptConfig())

    assert "<context>" in result.system_prompt
    assert "</context>" in result.system_prompt


def test_build_prompt_includes_untrusted_data_instruction():
    chunks = [_chunk(1)]
    with (_patch_tokens(50), _patch_window(128_000)):
        result = build_prompt("query", chunks, PromptConfig())
    assert "untrusted source data" in result.system_prompt


def test_build_prompt_includes_feature_spec():
    with (_patch_tokens(50), _patch_window(128_000)):
        result = build_prompt(
            "query", [], PromptConfig(), feature_spec="## Approved\nBuild something."
        )
    assert "Build something." in result.system_prompt


def test_build_prompt_includes_source_summaries():
    with (_patch_tokens(50), _patch_window(128_000)):
        result = build_prompt(
            "query",
            [],
            PromptConfig(),
            source_summaries=["Doc A summary.", "Doc B summary."],
        )
    assert "Doc A summary." in result.system_prompt
    assert "Doc B summary." in result.system_prompt


def test_build_prompt_caps_summaries_at_max():
    summaries = [f"Summary {i}" for i in range(20)]
    config = PromptConfig(max_source_summaries=5)
    with (_patch_tokens(50), _patch_window(128_000)):
        result = build_prompt("q", [], config, source_summaries=summaries)
    # Only first 5 summaries should appear
    assert "Summary 0" in result.system_prompt
    assert "Summary 5" not in result.system_prompt


def test_build_prompt_user_message_is_query():
    with (_patch_tokens(50), _patch_window(128_000)):
        result = build_prompt("What is DMX512?", [], PromptConfig())
    assert result.user_message == "What is DMX512?"


def test_build_prompt_system_prompt_order():
    """Brief → spec → summaries → context (in that order)."""
    brief_text = "PROJECT BRIEF"
    spec_text = "FEATURE SPEC"
    summary_text = "SUMMARY A"
    chunk_text = "CHUNK TEXT"

    chunks = [_chunk(1, text=chunk_text)]

    # Write a brief file
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(brief_text)
        brief_path = f.name

    try:
        config = PromptConfig(project_brief=brief_path)
        with (_patch_tokens(50), _patch_window(128_000)):
            result = build_prompt(
                "query", chunks, config,
                feature_spec=spec_text,
                source_summaries=[summary_text],
            )
    finally:
        os.unlink(brief_path)

    sp = result.system_prompt
    assert sp.index(brief_text) < sp.index(spec_text)
    assert sp.index(spec_text) < sp.index(summary_text)
    assert sp.index(summary_text) < sp.index(chunk_text)


def test_build_prompt_no_warning_under_threshold():
    with (
        _patch_tokens(100),
        _patch_window(128_000),
    ):
        result = build_prompt("q", [_chunk(1)], PromptConfig(token_budget=8192))
    assert result.budget_warning is None


def test_build_prompt_warning_above_threshold():
    # total = 4 × count_tokens return + chunk_budget
    # We need total > window × 0.85
    # Set window=1000, tokens=300 each, budget=300 → total=1200 > 850
    with (
        _patch_tokens(300),
        _patch_window(1000),
    ):
        config = PromptConfig(token_budget=300)
        result = build_prompt(
            "q",
            [_chunk(1)],
            config,
            feature_spec="spec",
            source_summaries=["s1"],
        )
    assert result.budget_warning is not None
    assert "⚠ Token budget warning" in result.budget_warning
    assert "Total:" in result.budget_warning


def test_build_prompt_breakdown_populated():
    # brief is None → count_tokens not called for brief
    # call order: spec_tokens, summaries_tokens
    with (
        patch("foundry.generate.templates.count_tokens", side_effect=[50, 30]),
        _patch_window(128_000),
    ):
        config = PromptConfig(token_budget=8192)
        result = build_prompt(
            "q", [], config, feature_spec="spec", source_summaries=["s"]
        )
    assert result.breakdown.feature_spec_tokens == 50
    assert result.breakdown.summaries_tokens == 30
    assert result.breakdown.chunk_budget == 8192
