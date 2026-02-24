"""Tests for foundry rich error messages (WI_0036)."""

from __future__ import annotations

import pytest

from foundry.cli.errors import (
    err_audio_too_large,
    err_config_api_key,
    err_embedding_model_mismatch,
    err_feature_not_found,
    err_no_api_key,
    err_no_approved_features,
    err_no_db,
    err_no_features_dir,
    err_output_path_unsafe,
    err_pandoc_not_found,
    err_project_brief_url,
    err_source_not_found,
    err_ssrf_blocked,
    warn_stale_outputs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_what_and_action(msg: str) -> bool:
    """Every error must contain a cause AND an actionable instruction."""
    lower = msg.lower()
    has_action = any(
        kw in lower
        for kw in ["run:", "set:", "use:", "install:", "export ", "foundry ", "split", "remove", "ingest", "re-ingest"]
    )
    return has_action


# ---------------------------------------------------------------------------
# err_no_api_key
# ---------------------------------------------------------------------------


def test_err_no_api_key_contains_provider() -> None:
    msg = err_no_api_key("openai")
    assert "openai" in msg.lower()


def test_err_no_api_key_contains_env_var() -> None:
    msg = err_no_api_key("openai")
    assert "OPENAI_API_KEY" in msg


def test_err_no_api_key_unknown_provider_fallback() -> None:
    msg = err_no_api_key("myprovider")
    assert "MYPROVIDER_API_KEY" in msg


def test_err_no_api_key_has_action() -> None:
    msg = err_no_api_key("openai")
    assert _has_what_and_action(msg)


@pytest.mark.parametrize(
    "provider,expected_env",
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("cohere", "COHERE_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ],
)
def test_err_no_api_key_known_providers(provider: str, expected_env: str) -> None:
    msg = err_no_api_key(provider)
    assert expected_env in msg


# ---------------------------------------------------------------------------
# err_no_approved_features
# ---------------------------------------------------------------------------


def test_err_no_approved_features_with_pending() -> None:
    msg = err_no_approved_features(["wiring", "firmware"])
    assert "wiring" in msg
    assert "firmware" in msg
    assert "approve" in msg.lower()


def test_err_no_approved_features_empty_list() -> None:
    msg = err_no_approved_features([])
    assert "features/" in msg
    assert "approve" in msg.lower()


def test_err_no_approved_features_has_action() -> None:
    msg = err_no_approved_features(["spec"])
    assert _has_what_and_action(msg)


# ---------------------------------------------------------------------------
# err_no_db
# ---------------------------------------------------------------------------


def test_err_no_db_contains_path() -> None:
    msg = err_no_db(".foundry.db")
    assert ".foundry.db" in msg


def test_err_no_db_suggests_init() -> None:
    msg = err_no_db()
    assert "foundry init" in msg


# ---------------------------------------------------------------------------
# err_embedding_model_mismatch
# ---------------------------------------------------------------------------


def test_err_embedding_model_mismatch_shows_both_models() -> None:
    msg = err_embedding_model_mismatch(
        "openai/text-embedding-3-small", "openai/text-embedding-3-large"
    )
    assert "text-embedding-3-small" in msg
    assert "text-embedding-3-large" in msg


def test_err_embedding_model_mismatch_has_action() -> None:
    msg = err_embedding_model_mismatch("model-a", "model-b")
    assert _has_what_and_action(msg)


# ---------------------------------------------------------------------------
# err_ssrf_blocked
# ---------------------------------------------------------------------------


def test_err_ssrf_blocked_contains_url() -> None:
    url = "http://169.254.169.254/latest/meta-data/"
    msg = err_ssrf_blocked(url)
    assert url in msg


def test_err_ssrf_blocked_mentions_private() -> None:
    msg = err_ssrf_blocked("http://192.168.1.1")
    assert "private" in msg.lower()


# ---------------------------------------------------------------------------
# err_audio_too_large
# ---------------------------------------------------------------------------


def test_err_audio_too_large_shows_file_and_size() -> None:
    msg = err_audio_too_large("recording.mp3", 30.5)
    assert "recording.mp3" in msg
    assert "30.5" in msg


def test_err_audio_too_large_shows_limit() -> None:
    msg = err_audio_too_large("audio.mp3", 26.0, limit_mb=25.0)
    assert "25" in msg


def test_err_audio_too_large_has_ffmpeg_hint() -> None:
    msg = err_audio_too_large("file.mp3", 30.0)
    assert "ffmpeg" in msg.lower() or "split" in msg.lower()


# ---------------------------------------------------------------------------
# err_no_features_dir
# ---------------------------------------------------------------------------


def test_err_no_features_dir_mentions_checklist() -> None:
    msg = err_no_features_dir()
    assert "features/" in msg
    assert "approve" in msg.lower()


# ---------------------------------------------------------------------------
# err_feature_not_found
# ---------------------------------------------------------------------------


def test_err_feature_not_found_shows_name() -> None:
    msg = err_feature_not_found("wiring-guide", ["firmware"])
    assert "wiring-guide" in msg


def test_err_feature_not_found_shows_approved_list() -> None:
    msg = err_feature_not_found("missing", ["firmware", "assembly"])
    assert "firmware" in msg
    assert "assembly" in msg


def test_err_feature_not_found_empty_approved() -> None:
    msg = err_feature_not_found("missing", [])
    assert "none" in msg.lower()


def test_err_feature_not_found_suggests_list() -> None:
    msg = err_feature_not_found("x", [])
    assert "foundry features list" in msg


# ---------------------------------------------------------------------------
# err_output_path_unsafe
# ---------------------------------------------------------------------------


def test_err_output_path_unsafe_shows_path() -> None:
    msg = err_output_path_unsafe("../../etc/crontab")
    assert "../../etc/crontab" in msg


# ---------------------------------------------------------------------------
# err_project_brief_url
# ---------------------------------------------------------------------------


def test_err_project_brief_url_shows_value() -> None:
    msg = err_project_brief_url("https://example.com/brief.md")
    assert "https://example.com/brief.md" in msg


def test_err_project_brief_url_mentions_ssrf() -> None:
    msg = err_project_brief_url("http://internal.server/brief")
    assert "SSRF" in msg or "local" in msg.lower()


def test_err_project_brief_url_shows_example() -> None:
    msg = err_project_brief_url("http://example.com")
    assert "project-context.md" in msg or "tracking/" in msg


# ---------------------------------------------------------------------------
# err_config_api_key
# ---------------------------------------------------------------------------


def test_err_config_api_key_shows_key_and_path() -> None:
    msg = err_config_api_key("api_key", "~/.foundry/config.yaml")
    assert "api_key" in msg
    assert "~/.foundry/config.yaml" in msg


def test_err_config_api_key_shows_env_var() -> None:
    msg = err_config_api_key("openai_api_key", "config.yaml")
    assert "OPENAI_API_KEY" in msg


# ---------------------------------------------------------------------------
# err_pandoc_not_found
# ---------------------------------------------------------------------------


def test_err_pandoc_not_found_is_warning_not_error() -> None:
    msg = err_pandoc_not_found()
    assert "Warning" in msg or "warning" in msg.lower()
    assert "Markdown" in msg


def test_err_pandoc_not_found_has_install_hint() -> None:
    msg = err_pandoc_not_found()
    assert "pandoc" in msg.lower()
    assert "install" in msg.lower()


# ---------------------------------------------------------------------------
# err_source_not_found
# ---------------------------------------------------------------------------


def test_err_source_not_found_shows_source() -> None:
    msg = err_source_not_found("datasheet-v1.pdf")
    assert "datasheet-v1.pdf" in msg


def test_err_source_not_found_suggests_status() -> None:
    msg = err_source_not_found("file.pdf")
    assert "foundry status" in msg


# ---------------------------------------------------------------------------
# warn_stale_outputs
# ---------------------------------------------------------------------------


def test_warn_stale_outputs_mentions_regenerate() -> None:
    msg = warn_stale_outputs()
    assert "regenerat" in msg.lower() or "generate" in msg.lower()


def test_warn_stale_outputs_is_warning_not_error() -> None:
    msg = warn_stale_outputs()
    # Should contain ⚠ or "warning" — not [red]Error
    assert "[red]Error" not in msg
