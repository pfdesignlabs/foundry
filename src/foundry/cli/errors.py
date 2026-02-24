"""Foundry rich error messages — actionable feedback (WI_0036).

Every error shown to the user must contain:
  1. What went wrong (clear cause)
  2. The exact action the user should take to fix it

Usage:
    from foundry.cli.errors import err_no_api_key, err_no_db
    console.print(err_no_api_key("openai"))
    raise typer.Exit(1)
"""

from __future__ import annotations


def err_no_api_key(provider: str) -> str:
    """No API key for *provider*.

    Example:
        No API key for 'openai'. Set:  export OPENAI_API_KEY=sk-...
    """
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "cohere": "COHERE_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "azure": "AZURE_API_KEY",
    }
    env_var = env_map.get(provider.lower(), f"{provider.upper()}_API_KEY")
    return (
        f"[red]Error:[/] No API key for '{provider}'.\n"
        f"  Set:  export {env_var}=sk-..."
    )


def err_no_approved_features(pending_names: list[str]) -> str:
    """No approved feature specs — show full checklist."""
    if pending_names:
        checklist = "\n".join(f"    [ ] foundry features approve {n}" for n in pending_names)
        return (
            "[red]Error:[/] No approved feature specs found.\n\n"
            "  Pending specs (approve one to proceed):\n"
            f"{checklist}"
        )
    return (
        "[red]Error:[/] No approved feature specs found.\n\n"
        "  Checklist:\n"
        "    [ ] Add a feature spec: features/<name>.md\n"
        "    [ ] Approve it: foundry features approve <name>"
    )


def err_no_db(db_path: str = ".foundry.db") -> str:
    """No .foundry.db found in current directory."""
    return (
        f"[red]Error:[/] No database found at '{db_path}'.\n"
        "  Run:  foundry init"
    )


def err_embedding_model_mismatch(db_model: str, config_model: str) -> str:
    """Embedding model stored in DB does not match current config."""
    return (
        f"[red]Error:[/] Embedding model mismatch.\n"
        f"  Database uses:  {db_model}\n"
        f"  Config has:     {config_model}\n"
        "  Re-ingest your sources or update the config to match the database model."
    )


def err_ssrf_blocked(url: str) -> str:
    """URL resolves to a private/reserved address."""
    return (
        f"[red]Error:[/] URL resolves to private address (SSRF protection): '{url}'\n"
        "  Use a publicly reachable URL."
    )


def err_audio_too_large(path: str, size_mb: float, limit_mb: float = 25.0) -> str:
    """Audio file exceeds the Whisper API limit."""
    return (
        f"[red]Error:[/] Audio file exceeds {limit_mb:.0f} MB limit: '{path}' ({size_mb:.1f} MB)\n"
        "  Split the file into smaller segments and ingest separately.\n"
        "  Tip:  ffmpeg -i input.mp3 -f segment -segment_time 600 -c copy part%03d.mp3"
    )


def err_no_features_dir() -> str:
    """features/ directory does not exist."""
    return (
        "[red]Error:[/] No features/ directory found.\n\n"
        "  To use foundry generate, you need at least one approved feature spec.\n"
        "  Checklist:\n"
        "    [ ] Create a features/ directory in your project root\n"
        "    [ ] Add a feature spec: features/<name>.md\n"
        "    [ ] Approve it: foundry features approve <name>"
    )


def err_feature_not_found(name: str, approved_names: list[str]) -> str:
    """Specific feature not found or not approved."""
    approved_list = ", ".join(approved_names) if approved_names else "(none)"
    return (
        f"[red]Error:[/] Feature spec '{name}' not found or not approved.\n"
        f"  Approved specs: {approved_list}\n"
        f"  Run:  foundry features list"
    )


def err_output_path_unsafe(path: str) -> str:
    """--output path fails security validation."""
    return (
        f"[red]Error:[/] Output path is not allowed: '{path}'\n"
        "  Use a path within the current working directory."
    )


def err_project_brief_url(brief: str) -> str:
    """project.brief is a URL — only local paths are allowed."""
    return (
        f"[red]Error:[/] project.brief must be a local file path, not a URL: '{brief}'\n"
        "  URLs are not allowed (SSRF prevention).\n"
        "  Example:  project.brief: tracking/project-context.md"
    )


def err_config_api_key(key_name: str, config_path: str) -> str:
    """Config file contains an API key field."""
    env_var = key_name.upper().replace("-", "_")
    return (
        f"[red]Error:[/] Config file '{config_path}' contains a forbidden key '{key_name}'.\n"
        "  API keys must be set via environment variables, not config files.\n"
        f"  Remove the key from {config_path} and use:\n"
        f"    export {env_var}=<value>"
    )


def err_pandoc_not_found() -> str:
    """Pandoc not installed — PDF export not available."""
    return (
        "[yellow]Warning:[/] Pandoc not found. Install pandoc for PDF export.\n"
        "  Markdown output saved.\n"
        "  Install: https://pandoc.org/installing.html"
    )


def err_source_not_found(source: str) -> str:
    """Source not found in database."""
    return (
        f"[yellow]Source not found:[/] '{source}' is not in the knowledge base.\n"
        "  Run:  foundry status  to see all ingested sources."
    )


def warn_stale_outputs() -> str:
    """Warning shown after foundry remove — drafts may be stale."""
    return (
        "[yellow]⚠[/] Existing draft outputs may reference this source.\n"
        "  Consider regenerating affected features:\n"
        "    foundry generate --topic <topic> --feature <name> --output <path>"
    )
