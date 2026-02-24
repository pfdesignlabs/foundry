"""Foundry configuration loader (WI_0038).

Priority (high → low):
  1. CLI flags           (handled at call site — not in this module)
  2. Environment variables  (FOUNDRY_GENERATION_MODEL, FOUNDRY_EMBEDDING_MODEL)
  3. Per-project foundry.yaml  (next to .foundry.db)
  4. Global ~/.foundry/config.yaml  (model defaults only — no API keys)
  5. Hardcoded defaults

Global config must never contain API keys; use environment variables instead.
project.brief must be a local file path — no URLs (SSRF prevention).
All YAML reads use yaml.safe_load() — never yaml.load().
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GLOBAL_CONFIG_DIR: Path = Path.home() / ".foundry"
_GLOBAL_CONFIG_PATH: Path = _GLOBAL_CONFIG_DIR / "config.yaml"
_PROJECT_CONFIG_NAME: str = "foundry.yaml"

# Fields that suggest an API key — forbidden in global config.
# Matches: api_key, apikey, api-key, api_secret, _token (suffix), standalone token,
# standalone secret, _secret (suffix), password, passwd, credential(s).
# Does NOT match legitimate config keys like token_budget, max_tokens, rrf_k.
_API_KEY_RE: re.Pattern[str] = re.compile(
    r"api[_\-]?(?:key|secret)"  # api_key, api-key, api_secret, apikey
    r"|_token$"                  # github_token, access_token, auth_token (suffix)
    r"|^token$"                  # exactly "token" (standalone)
    r"|_secret$"                 # my_secret, client_secret (suffix)
    r"|^secret$"                 # exactly "secret" (standalone)
    r"|passw(?:ord|d)"           # password, passwd
    r"|credential",              # credential, credentials
    re.IGNORECASE,
)

# Known top-level sections — unknown keys produce a warning
_KNOWN_SECTIONS: frozenset[str] = frozenset(
    ["project", "embedding", "generation", "retrieval", "chunkers", "delivery", "plan"]
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when a config file contains an invalid or forbidden value."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingCfg:
    """Embedding model configuration (foundry.yaml: embedding:)."""

    model: str = "openai/text-embedding-3-small"


@dataclass
class GenerationCfg:
    """LLM generation configuration (foundry.yaml: generation:)."""

    model: str = "openai/gpt-4o"
    max_source_summaries: int = 10


@dataclass
class RetrievalCfg:
    """Retrieval pipeline configuration (foundry.yaml: retrieval:)."""

    top_k: int = 10
    rrf_k: int = 60
    relevance_threshold: int = 4
    token_budget: int = 8_192


@dataclass
class ChunkerTypeCfg:
    """Chunk size and overlap for a single chunker type."""

    chunk_size: int = 512
    overlap: float = 0.10


@dataclass
class ChunkersCfg:
    """Per-type chunker configuration (foundry.yaml: chunkers:)."""

    default: ChunkerTypeCfg = field(default_factory=ChunkerTypeCfg)
    pdf: ChunkerTypeCfg = field(
        default_factory=lambda: ChunkerTypeCfg(chunk_size=400, overlap=0.20)
    )
    json: ChunkerTypeCfg = field(
        default_factory=lambda: ChunkerTypeCfg(chunk_size=300, overlap=0.0)
    )
    plaintext: ChunkerTypeCfg = field(default_factory=ChunkerTypeCfg)
    markdown: ChunkerTypeCfg = field(default_factory=ChunkerTypeCfg)
    audio: ChunkerTypeCfg = field(default_factory=ChunkerTypeCfg)
    git: ChunkerTypeCfg = field(default_factory=ChunkerTypeCfg)
    web: ChunkerTypeCfg = field(default_factory=ChunkerTypeCfg)


@dataclass
class ProjectCfg:
    """Project-level metadata (foundry.yaml: project:).

    Attributes:
        name: Human-readable project name.
        brief: Local path to the project context file (loaded verbatim into the
            system prompt). URLs are rejected to prevent SSRF.
        brief_max_tokens: Token limit for the brief; a warning is shown if exceeded.
    """

    name: str = ""
    brief: str | None = None  # local path only — no URLs (SSRF prevention)
    brief_max_tokens: int = 3_000


@dataclass
class DeliverySection:
    """A single section in the delivery document (foundry.yaml: delivery.sections[]).

    Attributes:
        type: Section type — 'generated' (RAG+LLM), 'file' (disk check),
            or 'physical' (WI status from slice.yaml).
        feature: Feature spec name (type: generated only).
        topic: Retrieval topic override (type: generated; falls back to heading).
        heading: H1 heading for this section in the output document.
        description: Descriptive text included in the section.
        path: File path to check (type: file only).
        tracking_wi: Work item ID to look up (type: physical only; never shown in output).
        show_attributions: Whether to append footnote source attribution (default True).
    """

    type: str = "generated"  # generated | file | physical
    feature: str | None = None
    topic: str | None = None
    heading: str = ""
    description: str = ""
    path: str | None = None
    tracking_wi: str | None = None
    show_attributions: bool = True


@dataclass
class DeliveryCfg:
    """Delivery document assembly configuration (foundry.yaml: delivery:)."""

    output: str = "delivery.md"
    sections: list[DeliverySection] = field(default_factory=list)


@dataclass
class PlanCfg:
    """LLM-assisted planning configuration (foundry.yaml: plan:)."""

    model: str = "openai/gpt-4o"
    max_summaries: int = 20


@dataclass
class FoundryConfig:
    """Root configuration object, built by load_config() from merged YAML layers."""

    project: ProjectCfg = field(default_factory=ProjectCfg)
    embedding: EmbeddingCfg = field(default_factory=EmbeddingCfg)
    generation: GenerationCfg = field(default_factory=GenerationCfg)
    retrieval: RetrievalCfg = field(default_factory=RetrievalCfg)
    chunkers: ChunkersCfg = field(default_factory=ChunkersCfg)
    delivery: DeliveryCfg = field(default_factory=DeliveryCfg)
    plan: PlanCfg = field(default_factory=PlanCfg)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _check_no_api_keys(data: dict[str, Any], source: Path) -> None:
    """Raise ConfigError if *data* contains any API-key-like key names.

    Global config must never store credentials; they belong in env vars.
    """

    def _scan(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                full = f"{path}.{k}" if path else k
                if _API_KEY_RE.search(str(k)):
                    raise ConfigError(
                        f"Global config '{source}' contains a forbidden key '{full}'.\n"
                        f"  API keys must be set via environment variables, not config files.\n"
                        f"  Remove '{full}' from {source.name} and use:\n"
                        f"    export {str(k).upper().replace('-', '_')}=<value>"
                    )
                _scan(v, full)

    _scan(data, "")


def _validate_brief_path(brief: str) -> None:
    """Raise ConfigError if *brief* is a URL rather than a local path.

    project.brief must be a local path for SSRF prevention.
    """
    if brief.startswith(("http://", "https://", "ftp://", "//")):
        raise ConfigError(
            f"project.brief must be a local file path, not a URL: '{brief}'\n"
            "  URLs are not allowed (SSRF prevention).\n"
            "  Example: project.brief: tracking/project-context.md"
        )


def _warn_unknown_keys(data: dict[str, Any], source: Path) -> None:
    """Emit a UserWarning for unrecognised top-level keys."""
    for key in data:
        if key not in _KNOWN_SECTIONS:
            warnings.warn(
                f"Unknown config key '{key}' in '{source}' — ignored.",
                UserWarning,
                stacklevel=4,
            )


# ---------------------------------------------------------------------------
# Merge + build
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict that is *base* deep-merged with *override*."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _parse_chunker(raw: dict[str, Any], defaults: ChunkerTypeCfg) -> ChunkerTypeCfg:
    return ChunkerTypeCfg(
        chunk_size=int(raw.get("chunk_size", defaults.chunk_size)),
        overlap=float(raw.get("overlap", defaults.overlap)),
    )


def _cfg_from_dict(data: dict[str, Any]) -> FoundryConfig:
    """Build a *FoundryConfig* from a merged raw YAML dict."""
    cfg = FoundryConfig()

    if "embedding" in data:
        e = data["embedding"]
        cfg.embedding = EmbeddingCfg(
            model=str(e.get("model", cfg.embedding.model)),
        )

    if "generation" in data:
        g = data["generation"]
        cfg.generation = GenerationCfg(
            model=str(g.get("model", cfg.generation.model)),
            max_source_summaries=int(
                g.get("max_source_summaries", cfg.generation.max_source_summaries)
            ),
        )

    if "retrieval" in data:
        r = data["retrieval"]
        cfg.retrieval = RetrievalCfg(
            top_k=int(r.get("top_k", cfg.retrieval.top_k)),
            rrf_k=int(r.get("rrf_k", cfg.retrieval.rrf_k)),
            relevance_threshold=int(
                r.get("relevance_threshold", cfg.retrieval.relevance_threshold)
            ),
            token_budget=int(r.get("token_budget", cfg.retrieval.token_budget)),
        )

    if "project" in data:
        p = data["project"]
        cfg.project = ProjectCfg(
            name=str(p.get("name", cfg.project.name)),
            brief=p.get("brief") or cfg.project.brief,
            brief_max_tokens=int(
                p.get("brief_max_tokens", cfg.project.brief_max_tokens)
            ),
        )

    if "chunkers" in data:
        ch = data["chunkers"]
        cfg.chunkers = ChunkersCfg(
            default=_parse_chunker(ch.get("default", {}), cfg.chunkers.default),
            pdf=_parse_chunker(ch.get("pdf", {}), cfg.chunkers.pdf),
            json=_parse_chunker(ch.get("json", {}), cfg.chunkers.json),
            plaintext=_parse_chunker(ch.get("plaintext", {}), cfg.chunkers.plaintext),
            markdown=_parse_chunker(ch.get("markdown", {}), cfg.chunkers.markdown),
            audio=_parse_chunker(ch.get("audio", {}), cfg.chunkers.audio),
            git=_parse_chunker(ch.get("git", {}), cfg.chunkers.git),
            web=_parse_chunker(ch.get("web", {}), cfg.chunkers.web),
        )

    if "delivery" in data:
        d = data["delivery"]
        sections: list[DeliverySection] = []
        for s in d.get("sections", []):
            sections.append(
                DeliverySection(
                    type=str(s.get("type", "generated")),
                    feature=s.get("feature"),
                    topic=s.get("topic"),
                    heading=str(s.get("heading", "")),
                    description=str(s.get("description", "")),
                    path=s.get("path"),
                    tracking_wi=s.get("tracking_wi"),
                    show_attributions=bool(s.get("show_attributions", True)),
                )
            )
        cfg.delivery = DeliveryCfg(
            output=str(d.get("output", cfg.delivery.output)),
            sections=sections,
        )

    if "plan" in data:
        pl = data["plan"]
        cfg.plan = PlanCfg(
            model=str(pl.get("model", cfg.plan.model)),
            max_summaries=int(pl.get("max_summaries", cfg.plan.max_summaries)),
        )

    return cfg


def _apply_env_overrides(cfg: FoundryConfig) -> FoundryConfig:
    """Apply FOUNDRY_* environment variable overrides (layer 2)."""
    if model := os.environ.get("FOUNDRY_GENERATION_MODEL"):
        cfg.generation.model = model
    if model := os.environ.get("FOUNDRY_EMBEDDING_MODEL"):
        cfg.embedding.model = model
    return cfg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(
    project_dir: Path | None = None,
    *,
    global_config_path: Path | None = None,
) -> FoundryConfig:
    """Load and return a merged *FoundryConfig*.

    Applies layers in order: global → per-project → env vars.
    CLI flag overrides must be applied by the caller after this function.

    Args:
        project_dir: Directory to search for *foundry.yaml*. Defaults to CWD.
        global_config_path: Override the global config path (for testing).

    Returns:
        Fully merged *FoundryConfig* with env var overrides applied.

    Raises:
        ConfigError: If global config contains API-key-like fields, or if
            ``project.brief`` is a URL rather than a local path.
    """
    global_path = global_config_path if global_config_path is not None else _GLOBAL_CONFIG_PATH
    search_dir = project_dir if project_dir is not None else Path.cwd()

    merged: dict[str, Any] = {}

    # Layer 1: global config
    if global_path.exists():
        raw_global = yaml.safe_load(global_path.read_text(encoding="utf-8")) or {}
        _check_no_api_keys(raw_global, global_path)
        _warn_unknown_keys(raw_global, global_path)
        merged = _deep_merge(merged, raw_global)

    # Layer 2: per-project config
    project_cfg_path = search_dir / _PROJECT_CONFIG_NAME
    if project_cfg_path.exists():
        raw_project = yaml.safe_load(project_cfg_path.read_text(encoding="utf-8")) or {}
        _warn_unknown_keys(raw_project, project_cfg_path)
        merged = _deep_merge(merged, raw_project)

    cfg = _cfg_from_dict(merged)

    # Validate project.brief (SSRF prevention)
    if cfg.project.brief:
        _validate_brief_path(cfg.project.brief)

    # Layer 3: env var overrides
    cfg = _apply_env_overrides(cfg)

    return cfg


def ensure_global_config(
    global_config_path: Path | None = None,
) -> Path:
    """Create ``~/.foundry/config.yaml`` with defaults if it does not exist.

    Creates parent directory with mode 0o700 and the config file with
    mode 0o600 (owner-readable only).

    Args:
        global_config_path: Override path (for testing).

    Returns:
        Path to the global config file.
    """
    target = global_config_path if global_config_path is not None else _GLOBAL_CONFIG_PATH
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    if not target.exists():
        content = (
            "# Foundry global configuration — model defaults only.\n"
            "# NEVER store API keys here — use environment variables:\n"
            "#   export OPENAI_API_KEY=sk-...\n"
            "#   export ANTHROPIC_API_KEY=sk-ant-...\n"
            "\n"
            "embedding:\n"
            "  model: openai/text-embedding-3-small\n"
            "\n"
            "generation:\n"
            "  model: openai/gpt-4o\n"
        )
        target.write_text(content, encoding="utf-8")
        target.chmod(0o600)

    return target
