"""foundry generate CLI command (WI_0029).

Operator review tool — generates a per-feature draft document via RAG + LLM.
(Not the delivery tool — that is `foundry build`, F05-CLI WI_0040.)

Usage:
  foundry generate --topic "DMX wiring" --output drafts/wiring.md [--feature spec-name]

Flags:
  --topic TEXT      Query / topic for retrieval (required)
  --output PATH     Output file path (required); path traversal blocked
  --feature NAME    Feature spec name without .md (auto-selected if only one approved)
  --db PATH         Path to .foundry.db (default: .foundry.db)
  --dry-run         Show retrieval + prompt without LLM generation
  --yes             Skip overwrite + cost prompts
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from foundry.db.connection import Database
from foundry.db.repository import Repository
from foundry.db.schema import initialize
from foundry.db.vectors import model_to_slug
from foundry.generate.templates import PromptConfig, build_prompt
from foundry.generate.writer import (
    add_attribution,
    check_overwrite,
    validate_output_path,
    write_output,
)
from foundry.rag.assembler import AssemblerConfig, assemble
from foundry.rag.llm_client import complete, count_tokens, validate_api_key
from foundry.rag.retriever import RetrieverConfig, retrieve

console = Console()

_DEFAULT_DB = ".foundry.db"
_EMBEDDING_MODEL = "openai/text-embedding-3-small"
_GENERATION_MODEL = "openai/gpt-4o"
_HYDE_MODEL = "openai/gpt-4o-mini"
_SCORER_MODEL = "openai/gpt-4o-mini"

_FEATURES_DIR = Path("features")


def generate_cmd(
    topic: Annotated[
        str,
        typer.Option("--topic", "-t", help="Query / topic for retrieval (required)."),
    ],
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output file path (required)."),
    ],
    feature: Annotated[
        str | None,
        typer.Option(
            "--feature",
            "-f",
            help="Feature spec name without .md extension (auto-selected if only one approved).",
        ),
    ] = None,
    db: Annotated[
        Path,
        typer.Option("--db", help="Path to .foundry.db (created if missing)."),
    ] = Path(_DEFAULT_DB),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show retrieval + assembled prompt without LLM generation."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts."),
    ] = False,
) -> None:
    """Generate a document for a feature using RAG + LLM."""

    # ---- Output path validation (security) ----
    try:
        output_path = validate_output_path(output)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)

    # ---- Overwrite check ----
    if not check_overwrite(output_path, yes=yes):
        console.print("  [dim]Cancelled.[/]")
        raise typer.Exit(0)

    # ---- Feature spec ----
    feature_spec_content = _load_feature_spec(feature)

    # ---- DB ----
    conn = _open_db(db)
    repo = Repository(conn)

    retriever_config = RetrieverConfig(
        embedding_model=_EMBEDDING_MODEL,
        mode="hybrid",
        top_k=10,
        hyde=True,
        hyde_model=_HYDE_MODEL,
    )
    assembler_config = AssemblerConfig(
        scorer_model=_SCORER_MODEL,
        relevance_threshold=4,
        token_budget=8_192,
        generation_model=_GENERATION_MODEL,
    )
    prompt_config = PromptConfig(
        generation_model=_GENERATION_MODEL,
        max_source_summaries=10,
        token_budget=8_192,
    )

    try:
        # ---- Retrieve ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task("Retrieving relevant chunks…", total=None)
            try:
                candidates = retrieve(topic, repo, retriever_config)
            except RuntimeError as exc:
                console.print(f"[red]Error:[/] {exc}")
                raise typer.Exit(1)

        console.print(f"  [dim]Retrieved {len(candidates)} candidate chunks[/]")

        # ---- Assemble context ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task("Scoring + assembling context…", total=None)
            ctx = assemble(topic, candidates, assembler_config)

        console.print(f"  [dim]Assembled {len(ctx.chunks)} chunks ({ctx.total_tokens:,} tokens)[/]")

        # ---- Conflict warnings ----
        if ctx.conflicts:
            console.print("\n  [yellow]⚠ Conflicts detected:[/]")
            for conflict in ctx.conflicts:
                console.print(f"    {conflict.source_a} ↔ {conflict.source_b}: {conflict.description}")

        # ---- Source summaries ----
        summaries = [s for _, s in repo.list_summaries(limit=prompt_config.max_source_summaries)]

        # ---- Build prompt ----
        prompt = build_prompt(
            query=topic,
            chunks=ctx.chunks,
            config=prompt_config,
            feature_spec=feature_spec_content,
            source_summaries=summaries,
        )

        if prompt.budget_warning:
            console.print(f"\n{prompt.budget_warning}")

        # ---- Dry run ----
        if dry_run:
            console.print("\n[bold]Dry run — assembled context:[/]")
            console.print(f"  System prompt length: {count_tokens(_GENERATION_MODEL, prompt.system_prompt):,} tokens")
            console.print(f"  Chunks: {len(ctx.chunks)}")
            console.print("\n[dim]No LLM generation performed.[/]")
            return

        # ---- API key validation ----
        try:
            validate_api_key(_GENERATION_MODEL)
        except EnvironmentError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise typer.Exit(1)

        # ---- Generate ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task(f"Generating with {_GENERATION_MODEL}…", total=None)
            content = complete(
                model=_GENERATION_MODEL,
                messages=[
                    {"role": "system", "content": prompt.system_prompt},
                    {"role": "user", "content": prompt.user_message},
                ],
                max_tokens=4096,
            )

        # ---- Attribution ----
        content_with_attribution = add_attribution(content, ctx.chunks)

        # ---- Write ----
        write_output(output_path, content_with_attribution)
        console.print(f"\n  [green]✓[/] Written to [bold]{output_path}[/]")

    finally:
        conn.close()


# ------------------------------------------------------------------
# Feature spec loading
# ------------------------------------------------------------------


def _load_feature_spec(feature_name: str | None) -> str | None:
    """Load an approved feature spec by name.

    If feature_name is None and only one approved spec exists → auto-select.
    If multiple approved specs exist and feature_name is None → hard fail with list.
    Returns the spec content or None if no features directory exists.
    """
    if not _FEATURES_DIR.exists():
        return None

    approved = _find_approved_specs()

    if not approved:
        return None

    if feature_name:
        # Exact match or substring
        matches = [s for s in approved if feature_name in s.stem]
        if not matches:
            console.print(
                f"[red]Error:[/] Feature spec '{feature_name}' not found or not approved.\n"
                f"  Approved specs: {', '.join(s.stem for s in approved)}"
            )
            raise typer.Exit(1)
        return matches[0].read_text(encoding="utf-8")

    if len(approved) == 1:
        return approved[0].read_text(encoding="utf-8")

    # Multiple approved specs → require --feature
    console.print(
        "[red]Error:[/] Multiple approved feature specs found. "
        "Use --feature NAME to select one:\n"
        + "\n".join(f"  - {s.stem}" for s in approved)
    )
    raise typer.Exit(1)


def _find_approved_specs() -> list[Path]:
    """Return list of feature spec files that contain '## Approved'."""
    specs = []
    for path in sorted(_FEATURES_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            if "## Approved" in content:
                specs.append(path)
        except OSError:
            continue
    return specs


# ------------------------------------------------------------------
# DB helper
# ------------------------------------------------------------------


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the project database and run migrations."""
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    return conn
