"""Tests for LiteLLM client wrapper (WI_0026)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from foundry.rag.llm_client import (
    complete,
    count_tokens,
    embed,
    get_context_window,
    validate_api_key,
)


# ------------------------------------------------------------------
# validate_api_key
# ------------------------------------------------------------------


def test_validate_api_key_raises_if_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="OPENAI_API_KEY"):
        validate_api_key("openai/gpt-4o")


def test_validate_api_key_passes_if_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    validate_api_key("openai/gpt-4o")  # should not raise


def test_validate_api_key_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        validate_api_key("anthropic/claude-3-5-sonnet-20241022")


def test_validate_api_key_ollama_no_key_required():
    # Ollama is local — no env var needed, should never raise
    validate_api_key("ollama/llama2")


def test_validate_api_key_unknown_provider_treated_as_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Unknown provider falls back to openai key check
    with pytest.raises(EnvironmentError):
        validate_api_key("unknown-provider-model")


# ------------------------------------------------------------------
# complete()
# ------------------------------------------------------------------


def test_complete_returns_content():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Hello, world!"

    with patch("foundry.rag.llm_client.litellm.completion", return_value=mock_response):
        result = complete("openai/gpt-4o", [{"role": "user", "content": "Hi"}])

    assert result == "Hello, world!"


def test_complete_returns_empty_string_on_none_content():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = None

    with patch("foundry.rag.llm_client.litellm.completion", return_value=mock_response):
        result = complete("openai/gpt-4o", [{"role": "user", "content": "Hi"}])

    assert result == ""


def test_complete_passes_params_to_litellm():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "ok"

    with patch("foundry.rag.llm_client.litellm.completion", return_value=mock_response) as mock_c:
        complete(
            "openai/gpt-4o-mini",
            [{"role": "user", "content": "test"}],
            max_tokens=512,
            temperature=0.5,
            num_retries=2,
        )

    call_kwargs = mock_c.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-4o-mini"
    assert call_kwargs["max_tokens"] == 512
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["num_retries"] == 2


# ------------------------------------------------------------------
# embed()
# ------------------------------------------------------------------


def test_embed_returns_vector():
    mock_response = MagicMock()
    mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

    with patch("foundry.rag.llm_client.litellm.embedding", return_value=mock_response):
        result = embed("openai/text-embedding-3-small", "hello")

    assert result == [0.1, 0.2, 0.3]


def test_embed_passes_text_as_list():
    mock_response = MagicMock()
    mock_response.data = [{"embedding": [0.0]}]

    with patch("foundry.rag.llm_client.litellm.embedding", return_value=mock_response) as mock_e:
        embed("openai/text-embedding-3-small", "test text")

    assert mock_e.call_args.kwargs["input"] == ["test text"]


# ------------------------------------------------------------------
# count_tokens()
# ------------------------------------------------------------------


def test_count_tokens_uses_litellm():
    with patch("foundry.rag.llm_client.litellm.token_counter", return_value=42):
        result = count_tokens("openai/gpt-4o", "some text")
    assert result == 42


def test_count_tokens_fallback_on_error():
    with patch(
        "foundry.rag.llm_client.litellm.token_counter", side_effect=Exception("unsupported")
    ):
        result = count_tokens("unknown/model", "a" * 100)
    # 100 chars / 4 = 25 tokens (approx)
    assert result == 25


def test_count_tokens_fallback_minimum_one():
    with patch(
        "foundry.rag.llm_client.litellm.token_counter", side_effect=Exception("err")
    ):
        result = count_tokens("x", "")
    assert result == 1


# ------------------------------------------------------------------
# get_context_window()
# ------------------------------------------------------------------


def test_get_context_window_uses_litellm_info():
    with patch(
        "foundry.rag.llm_client.litellm.get_model_info",
        return_value={"max_input_tokens": 128_000},
    ):
        result = get_context_window("openai/gpt-4o")
    assert result == 128_000


def test_get_context_window_fallback_table():
    with patch(
        "foundry.rag.llm_client.litellm.get_model_info", side_effect=Exception("err")
    ):
        result = get_context_window("openai/gpt-4o")
    assert result == 128_000


def test_get_context_window_unknown_model_returns_default():
    with patch(
        "foundry.rag.llm_client.litellm.get_model_info", side_effect=Exception("err")
    ):
        result = get_context_window("totally/unknown-model")
    assert result == 8_192
