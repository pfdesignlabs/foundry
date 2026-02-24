"""Tests for foundry config loader (WI_0038)."""

from __future__ import annotations

import os
import stat
import warnings
from pathlib import Path

import pytest
import yaml

from foundry.config import (
    ConfigError,
    DeliverySection,
    EmbeddingCfg,
    FoundryConfig,
    GenerationCfg,
    RetrievalCfg,
    ensure_global_config,
    load_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Defaults — no config files present
# ---------------------------------------------------------------------------


def test_load_config_defaults_no_files(tmp_path: Path) -> None:
    """No config files → all hardcoded defaults."""
    missing_global = tmp_path / "nonexistent" / "config.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)

    assert cfg.embedding.model == "openai/text-embedding-3-small"
    assert cfg.generation.model == "openai/gpt-4o"
    assert cfg.generation.max_source_summaries == 10
    assert cfg.retrieval.top_k == 10
    assert cfg.retrieval.token_budget == 8_192
    assert cfg.chunkers.default.chunk_size == 512
    assert cfg.chunkers.pdf.chunk_size == 400
    assert cfg.chunkers.json.chunk_size == 300
    assert cfg.project.name == ""
    assert cfg.project.brief is None


# ---------------------------------------------------------------------------
# Global config
# ---------------------------------------------------------------------------


def test_load_config_global_overrides_defaults(tmp_path: Path) -> None:
    """Global config overrides hardcoded defaults."""
    global_cfg = tmp_path / "config.yaml"
    _write_yaml(global_cfg, {"generation": {"model": "anthropic/claude-3-5-sonnet-20241022"}})

    cfg = load_config(project_dir=tmp_path, global_config_path=global_cfg)
    assert cfg.generation.model == "anthropic/claude-3-5-sonnet-20241022"
    # Other defaults unchanged
    assert cfg.embedding.model == "openai/text-embedding-3-small"


def test_load_config_global_empty_file(tmp_path: Path) -> None:
    """Empty global config file → defaults (no crash)."""
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text("", encoding="utf-8")

    cfg = load_config(project_dir=tmp_path, global_config_path=global_cfg)
    assert cfg.generation.model == "openai/gpt-4o"


def test_load_config_global_null_yaml(tmp_path: Path) -> None:
    """Global config with only comments/null → defaults."""
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text("# nothing here\n", encoding="utf-8")

    cfg = load_config(project_dir=tmp_path, global_config_path=global_cfg)
    assert cfg.embedding.model == "openai/text-embedding-3-small"


# ---------------------------------------------------------------------------
# Per-project config
# ---------------------------------------------------------------------------


def test_load_config_project_overrides_global(tmp_path: Path) -> None:
    """Per-project foundry.yaml overrides global config."""
    global_cfg = tmp_path / "global.yaml"
    _write_yaml(global_cfg, {"generation": {"model": "openai/gpt-4o-mini"}})

    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"generation": {"model": "openai/gpt-4o"}})

    cfg = load_config(project_dir=tmp_path, global_config_path=global_cfg)
    assert cfg.generation.model == "openai/gpt-4o"


def test_load_config_project_partial_override(tmp_path: Path) -> None:
    """Per-project can override a single field; global values for other fields survive."""
    global_cfg = tmp_path / "global.yaml"
    _write_yaml(global_cfg, {"retrieval": {"top_k": 20, "token_budget": 4096}})

    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"retrieval": {"top_k": 5}})

    cfg = load_config(project_dir=tmp_path, global_config_path=global_cfg)
    assert cfg.retrieval.top_k == 5
    assert cfg.retrieval.token_budget == 4096  # global value preserved


def test_load_config_project_name_and_brief(tmp_path: Path) -> None:
    """project.name and local project.brief are loaded correctly."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(
        project_cfg,
        {"project": {"name": "DMX Controller", "brief": "tracking/project-context.md"}},
    )

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.project.name == "DMX Controller"
    assert cfg.project.brief == "tracking/project-context.md"


# ---------------------------------------------------------------------------
# Chunker config
# ---------------------------------------------------------------------------


def test_load_config_chunker_overrides(tmp_path: Path) -> None:
    """foundry.yaml can override chunker settings per type."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(
        project_cfg,
        {"chunkers": {"pdf": {"chunk_size": 600, "overlap": 0.15}}},
    )

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.chunkers.pdf.chunk_size == 600
    assert cfg.chunkers.pdf.overlap == pytest.approx(0.15)
    # Other chunker types unchanged
    assert cfg.chunkers.json.chunk_size == 300


def test_load_config_default_chunker_override(tmp_path: Path) -> None:
    """Overriding the 'default' chunker type works."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"chunkers": {"default": {"chunk_size": 256, "overlap": 0.05}}})

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.chunkers.default.chunk_size == 256


# ---------------------------------------------------------------------------
# Delivery sections
# ---------------------------------------------------------------------------


def test_load_config_delivery_sections(tmp_path: Path) -> None:
    """Delivery sections are parsed with correct types and defaults."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(
        project_cfg,
        {
            "delivery": {
                "output": "build-guide.md",
                "sections": [
                    {
                        "type": "generated",
                        "feature": "wiring-guide",
                        "heading": "Wiring Guide",
                        "show_attributions": True,
                    },
                    {
                        "type": "file",
                        "path": "output/bom.xlsx",
                        "heading": "BOM",
                        "description": "Bill of materials",
                    },
                    {
                        "type": "physical",
                        "heading": "Prototype",
                        "tracking_wi": "WI_0004",
                        "show_attributions": False,
                    },
                ],
            }
        },
    )

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)

    assert cfg.delivery.output == "build-guide.md"
    assert len(cfg.delivery.sections) == 3

    s0 = cfg.delivery.sections[0]
    assert s0.type == "generated"
    assert s0.feature == "wiring-guide"
    assert s0.heading == "Wiring Guide"
    assert s0.show_attributions is True

    s1 = cfg.delivery.sections[1]
    assert s1.type == "file"
    assert s1.path == "output/bom.xlsx"
    assert s1.show_attributions is True  # default

    s2 = cfg.delivery.sections[2]
    assert s2.type == "physical"
    assert s2.tracking_wi == "WI_0004"
    assert s2.show_attributions is False


def test_load_config_delivery_default_type_is_generated(tmp_path: Path) -> None:
    """Section without explicit type defaults to 'generated'."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(
        project_cfg,
        {"delivery": {"sections": [{"feature": "spec", "heading": "Spec"}]}},
    )

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.delivery.sections[0].type == "generated"


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    ["api_key", "apikey", "OPENAI_API_KEY", "secret", "password", "token", "api-key"],
)
def test_global_config_rejects_api_key_fields(tmp_path: Path, bad_key: str) -> None:
    """Global config containing API key-like field names raises ConfigError."""
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text(f"{bad_key}: sk-abc123\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="forbidden key"):
        load_config(project_dir=tmp_path, global_config_path=global_cfg)


def test_global_config_rejects_nested_api_key(tmp_path: Path) -> None:
    """Nested API key-like field also raises ConfigError."""
    global_cfg = tmp_path / "config.yaml"
    _write_yaml(global_cfg, {"openai": {"api_key": "sk-secret"}})

    with pytest.raises(ConfigError, match="forbidden key"):
        load_config(project_dir=tmp_path, global_config_path=global_cfg)


def test_project_config_api_key_not_checked(tmp_path: Path) -> None:
    """Per-project foundry.yaml is not checked for API keys (only global is)."""
    project_cfg = tmp_path / "foundry.yaml"
    # This is unusual but per-project config is not validated for API keys
    _write_yaml(project_cfg, {"project": {"name": "test"}})

    missing_global = tmp_path / "nonexistent.yaml"
    # Should not raise
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.project.name == "test"


# ---------------------------------------------------------------------------
# project.brief URL validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_brief",
    [
        "http://example.com/context.md",
        "https://github.com/user/repo/context.md",
        "ftp://files.example.com/brief.pdf",
        "//cdn.example.com/brief.md",
    ],
)
def test_project_brief_url_raises_config_error(tmp_path: Path, bad_brief: str) -> None:
    """project.brief set to a URL raises ConfigError (SSRF prevention)."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"project": {"brief": bad_brief}})

    missing_global = tmp_path / "nonexistent.yaml"
    with pytest.raises(ConfigError, match="local file path"):
        load_config(project_dir=tmp_path, global_config_path=missing_global)


def test_project_brief_local_path_ok(tmp_path: Path) -> None:
    """project.brief set to a local path does not raise."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"project": {"brief": "tracking/project-context.md"}})

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.project.brief == "tracking/project-context.md"


def test_project_brief_absolute_local_path_ok(tmp_path: Path) -> None:
    """Absolute local paths are valid for project.brief."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"project": {"brief": str(tmp_path / "context.md")}})

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.project.brief is not None


# ---------------------------------------------------------------------------
# Unknown key warnings
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_warns(tmp_path: Path) -> None:
    """Unknown top-level key in config emits UserWarning (not error)."""
    global_cfg = tmp_path / "config.yaml"
    _write_yaml(global_cfg, {"unknown_section": {"foo": "bar"}})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = load_config(project_dir=tmp_path, global_config_path=global_cfg)

    assert any("unknown_section" in str(w.message) for w in caught)
    # Should still return a valid config
    assert cfg.generation.model == "openai/gpt-4o"


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


def test_env_var_generation_model_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FOUNDRY_GENERATION_MODEL env var overrides config file value."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"generation": {"model": "openai/gpt-4o-mini"}})

    monkeypatch.setenv("FOUNDRY_GENERATION_MODEL", "anthropic/claude-3-5-sonnet-20241022")
    missing_global = tmp_path / "nonexistent.yaml"

    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.generation.model == "anthropic/claude-3-5-sonnet-20241022"


def test_env_var_embedding_model_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FOUNDRY_EMBEDDING_MODEL env var overrides config file value."""
    monkeypatch.setenv("FOUNDRY_EMBEDDING_MODEL", "openai/text-embedding-3-large")
    missing_global = tmp_path / "nonexistent.yaml"

    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.embedding.model == "openai/text-embedding-3-large"


def test_env_var_absent_does_not_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If env vars are not set, config file values are used."""
    monkeypatch.delenv("FOUNDRY_GENERATION_MODEL", raising=False)
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"generation": {"model": "openai/gpt-4o-mini"}})

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.generation.model == "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# Plan config
# ---------------------------------------------------------------------------


def test_load_config_plan_section(tmp_path: Path) -> None:
    """plan: section is loaded correctly."""
    project_cfg = tmp_path / "foundry.yaml"
    _write_yaml(project_cfg, {"plan": {"model": "openai/gpt-4o-mini", "max_summaries": 5}})

    missing_global = tmp_path / "nonexistent.yaml"
    cfg = load_config(project_dir=tmp_path, global_config_path=missing_global)
    assert cfg.plan.model == "openai/gpt-4o-mini"
    assert cfg.plan.max_summaries == 5


# ---------------------------------------------------------------------------
# ensure_global_config
# ---------------------------------------------------------------------------


def test_ensure_global_config_creates_file(tmp_path: Path) -> None:
    """ensure_global_config creates the config file if it doesn't exist."""
    target = tmp_path / ".foundry" / "config.yaml"
    result = ensure_global_config(global_config_path=target)

    assert result == target
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "embedding" in content
    assert "generation" in content

    # The parsed YAML (not the comments) must not contain API key fields
    parsed = yaml.safe_load(content) or {}
    from foundry.config import _API_KEY_RE

    def _no_api_keys(obj: object) -> bool:
        if isinstance(obj, dict):
            return all(
                not _API_KEY_RE.search(str(k)) and _no_api_keys(v) for k, v in obj.items()
            )
        return True

    assert _no_api_keys(parsed)


def test_ensure_global_config_file_mode(tmp_path: Path) -> None:
    """ensure_global_config creates file with mode 0o600 (owner-only)."""
    target = tmp_path / ".foundry" / "config.yaml"
    ensure_global_config(global_config_path=target)

    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600


def test_ensure_global_config_idempotent(tmp_path: Path) -> None:
    """Calling ensure_global_config twice does not overwrite existing file."""
    target = tmp_path / ".foundry" / "config.yaml"
    ensure_global_config(global_config_path=target)

    # Modify the file
    target.write_text("# custom\ngeneration:\n  model: openai/gpt-4o-mini\n", encoding="utf-8")

    ensure_global_config(global_config_path=target)  # should not overwrite
    content = target.read_text(encoding="utf-8")
    assert "gpt-4o-mini" in content


def test_ensure_global_config_returns_path(tmp_path: Path) -> None:
    """ensure_global_config returns the config file path."""
    target = tmp_path / ".foundry" / "config.yaml"
    result = ensure_global_config(global_config_path=target)
    assert result == target


# ---------------------------------------------------------------------------
# yaml.safe_load enforcement (regression guard)
# ---------------------------------------------------------------------------


def test_config_does_not_execute_yaml_load(tmp_path: Path) -> None:
    """Config loader uses safe_load — malicious YAML constructs are not executed."""
    # A YAML file with a Python object tag that yaml.load() would execute
    # yaml.safe_load() raises yaml.constructor.ConstructorError for this
    evil_yaml = "!!python/object/apply:os.system ['echo pwned']\n"
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text(evil_yaml, encoding="utf-8")

    # Should raise (yaml.safe_load raises ConstructorError for python tags)
    # rather than executing the system call
    import yaml as _yaml

    with pytest.raises(_yaml.YAMLError):
        load_config(project_dir=tmp_path, global_config_path=global_cfg)
