"""foundry generate CLI command (WI_0029, WI_0031).

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

Gate enforcement (WI_0031):
  - features/ directory missing → hard fail with scaffold instruction
  - no .md files in features/   → hard fail
  - no approved specs            → hard fail with full spec checklist
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
from foundry.gates.parser import FeatureSpec, load_all_specs
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

    # ---- Feature gate (WI_0031) ----
    feature_spec_content = _load_feature_spec(feature, _FEATURES_DIR)

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
        # ---- Step 1/5: Retrieve ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task("[1/5] Retrieving…", total=None)
            try:
                candidates = retrieve(topic, repo, retriever_config)
            except RuntimeError as exc:
                console.print(f"[red]Error:[/] {exc}")
                raise typer.Exit(1)

        console.print(f"  [dim]✓ Retrieving — {len(candidates)} candidate chunks[/]")

        # ---- Step 2/5: Score ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task("[2/5] Scoring…", total=None)
            ctx = assemble(topic, candidates, assembler_config)

        console.print(f"  [dim]✓ Scoring — {len(ctx.chunks)} chunks kept ({ctx.total_tokens:,} tokens)[/]")

        # ---- Step 3/5: Check conflicts ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task("[3/5] Checking conflicts…", total=None)

        if ctx.conflicts:
            console.print(f"  [yellow]⚠ Checking conflicts — {len(ctx.conflicts)} found:[/]")
            for conflict in ctx.conflicts:
                console.print(f"    {conflict.source_a} ↔ {conflict.source_b}: {conflict.description}")
        else:
            console.print("  [dim]✓ Checking conflicts — none[/]")

        # ---- Step 4/5: Assemble prompt ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task("[4/5] Assembling…", total=None)
            summaries = [s for _, s in repo.list_summaries(limit=prompt_config.max_source_summaries)]
            prompt = build_prompt(
                query=topic,
                chunks=ctx.chunks,
                config=prompt_config,
                feature_spec=feature_spec_content,
                source_summaries=summaries,
            )

        console.print(f"  [dim]✓ Assembling — {count_tokens(_GENERATION_MODEL, prompt.system_prompt):,} prompt tokens[/]")

        if prompt.budget_warning:
            console.print(f"\n{prompt.budget_warning}")

        # ---- Dry run ----
        if dry_run:
            console.print("\n[bold]Dry run — assembled context:[/]")
            console.print(f"  System prompt: {count_tokens(_GENERATION_MODEL, prompt.system_prompt):,} tokens")
            console.print(f"  Chunks: {len(ctx.chunks)}")
            console.print("\n[dim]No LLM generation performed.[/]")
            return

        # ---- API key validation ----
        try:
            validate_api_key(_GENERATION_MODEL)
        except EnvironmentError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise typer.Exit(1)

        # ---- Step 5/5: Generate ----
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            prog.add_task(f"[5/5] Generating with {_GENERATION_MODEL}…", total=None)
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
# Feature gate (WI_0031)
# ------------------------------------------------------------------


def _load_feature_spec(feature_name: str | None, features_dir: Path = _FEATURES_DIR) -> str:
    """Load an approved feature spec, enforcing the feature gate (WI_0031).

    Hard fail (exit 1) in all cases where generation must not proceed:
      1. features/ directory does not exist → scaffold instruction
      2. No .md files in features/          → no specs created yet
      3. No approved specs                  → full checklist of pending specs
      4. feature_name not found / not approved

    If feature_name is None and only one approved spec exists → auto-select.
    If multiple approved specs and feature_name is None → hard fail with list.

    Returns:
        The approved spec's content as a string.
    """
    # Gate 1: directory missing
    if not features_dir.is_dir():
        console.print(
            "[red]Error:[/] No features/ directory found.\n\n"
            "  To use foundry generate, you need at least one approved feature spec.\n"
            "  Checklist:\n"
            "    [ ] Create a features/ directory in your project root\n"
            "    [ ] Add a feature spec: features/<name>.md\n"
            "    [ ] Approve it: foundry features approve <name>"
        )
        raise typer.Exit(1)

    all_specs = load_all_specs(features_dir)

    # Gate 2: no .md files at all
    if not all_specs:
        console.print(
            "[red]Error:[/] No feature specs found in features/.\n\n"
            "  Checklist:\n"
            "    [ ] Add a feature spec: features/<name>.md\n"
            "    [ ] Approve it: foundry features approve <name>"
        )
        raise typer.Exit(1)

    approved = [s for s in all_specs if s.approved]

    # Gate 3: no approved specs — show full checklist
    if not approved:
        pending_list = "\n".join(f"    [ ] foundry features approve {s.name}" for s in all_specs)
        console.print(
            "[red]Error:[/] No approved feature specs found.\n\n"
            "  Pending specs (approve one to proceed):\n"
            f"{pending_list}"
        )
        raise typer.Exit(1)

    # Gate 4a: specific feature requested
    if feature_name:
        matches = [s for s in approved if feature_name in s.name]
        if not matches:
            approved_names = ", ".join(s.name for s in approved)
            console.print(
                f"[red]Error:[/] Feature spec '{feature_name}' not found or not approved.\n"
                f"  Approved specs: {approved_names}"
            )
            raise typer.Exit(1)
        return matches[0].content

    # Gate 4b: auto-select if exactly one approved
    if len(approved) == 1:
        return approved[0].content

    # Gate 4c: multiple approved → require --feature
    console.print(
        "[red]Error:[/] Multiple approved feature specs found. "
        "Use --feature NAME to select one:\n"
        + "\n".join(f"  - {s.name}" for s in approved)
    )
    raise typer.Exit(1)


# ------------------------------------------------------------------
# DB helper
# ------------------------------------------------------------------


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the project database and run migrations."""
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    return conn
