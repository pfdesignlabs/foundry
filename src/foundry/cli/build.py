"""foundry build — consolidated delivery document assembler (WI_0040).

Reads the ``delivery:`` section from ``foundry.yaml`` and assembles a single
Markdown document from multiple section types:

  type: generated  — RAG + LLM generation per feature spec
  type: file       — checks if a file exists; warns if missing
  type: physical   — reads WI status from .forge/slice.yaml

Section ordering matches the ``delivery.sections`` list in ``foundry.yaml``.

Usage:
  foundry build
  foundry build --output report.md --yes
  foundry build --dry-run
  foundry build --pdf          (requires Pandoc on PATH — fail-open)
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import os
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from foundry.cli.errors import err_no_db, warn_stale_outputs
from foundry.config import DeliverySection, load_config
from foundry.db.connection import Database
from foundry.db.repository import Repository
from foundry.db.schema import initialize
from foundry.gates.parser import load_all_specs
from foundry.generate.templates import PromptConfig, build_prompt
from foundry.generate.writer import add_attribution, check_overwrite, write_output
from foundry.rag.assembler import AssemblerConfig, assemble
from foundry.rag.llm_client import complete, validate_api_key
from foundry.rag.retriever import RetrieverConfig, retrieve

console = Console()

_DEFAULT_DB = Path(".foundry.db")
_FEATURES_DIR = Path("features")
_FORGE_SLICE = Path(".forge") / "slice.yaml"

_EMBEDDING_MODEL = "openai/text-embedding-3-small"
_GENERATION_MODEL = "openai/gpt-4o"
_HYDE_MODEL = "openai/gpt-4o-mini"
_SCORER_MODEL = "openai/gpt-4o-mini"


def build_cmd(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output path for the delivery document. Overrides delivery.output in foundry.yaml."),
    ] = None,
    db: Annotated[
        Path,
        typer.Option("--db", help="Path to .foundry.db knowledge base."),
    ] = _DEFAULT_DB,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the delivery plan (sections, approval status) without calling the LLM."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip overwrite confirmation prompts (useful for CI/scripts)."),
    ] = False,
    pdf: Annotated[
        bool,
        typer.Option("--pdf", help="Also export a PDF via Pandoc. Requires Pandoc on PATH; skipped gracefully if not found."),
    ] = False,
    features_dir: Annotated[
        Path,
        typer.Option("--features-dir", hidden=True, help="Override features/ path (for testing)."),
    ] = _FEATURES_DIR,
    slice_path: Annotated[
        Path,
        typer.Option("--slice", hidden=True, help="Override .forge/slice.yaml path (for testing)."),
    ] = _FORGE_SLICE,
) -> None:
    """Assemble the official client delivery document from all approved features.

    Reads the delivery: section from foundry.yaml and builds a single Markdown
    document from three section types: generated (RAG + LLM), file (disk check),
    and physical (WI status from .forge/slice.yaml). Use 'foundry generate' to
    draft and review individual features before running build.
    """

    # ---- Config ----
    try:
        cfg = load_config(project_dir=db.parent if db != _DEFAULT_DB else None)
    except Exception:
        cfg = None

    sections = cfg.delivery.sections if cfg else []
    output_path = Path(output) if output else Path(cfg.delivery.output if cfg else "delivery.md")

    if not sections:
        console.print(
            "[red]Error:[/] No delivery sections configured in foundry.yaml.\n\n"
            "  Add a 'delivery:' section with at least one entry:\n\n"
            "    delivery:\n"
            "      output: delivery.md\n"
            "      sections:\n"
            "        - type: generated\n"
            "          feature: your-feature-name\n"
            "          topic: \"your topic\"\n"
            "          heading: \"Section Heading\"\n\n"
            "  Run: foundry init   to scaffold foundry.yaml with a template."
        )
        raise typer.Exit(1)

    # ---- Dry run: show plan ----
    if dry_run:
        _show_dry_run(sections, features_dir, slice_path)
        return

    # ---- DB check ----
    if not db.exists():
        console.print(err_no_db(str(db)))
        raise typer.Exit(1)

    # ---- Validate: all generated sections must be approved ----
    _validate_all_approved(sections, features_dir)

    # ---- Overwrite check ----
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not check_overwrite(output_path, yes=yes):
        console.print("  [dim]Cancelled.[/]")
        raise typer.Exit(0)

    # ---- Open DB ----
    conn = _open_db(db)
    repo = Repository(conn)

    # ---- Build each section ----
    parts: list[str] = []
    try:
        for i, section in enumerate(sections, start=1):
            heading = section.heading or section.feature or section.path or f"Section {i}"
            console.print(f"\n[bold][{i}/{len(sections)}] {heading}[/] ({section.type})")

            if section.type == "generated":
                content = _build_generated(section, features_dir, repo)
                if section.show_attributions:
                    # attribution is already appended inside _build_generated
                    parts.append(f"# {heading}\n\n{content}")
                else:
                    parts.append(f"# {heading}\n\n{content}")

            elif section.type == "file":
                content = _build_file(section)
                parts.append(f"# {heading}\n\n{content}")

            elif section.type == "physical":
                content = _build_physical(section, slice_path)
                parts.append(f"# {heading}\n\n{content}")

            else:
                console.print(f"  [yellow]⚠[/] Unknown section type '{section.type}' — skipped.")
    finally:
        conn.close()

    # ---- Assemble ----
    delivery_doc = "\n\n---\n\n".join(parts)

    # ---- Write ----
    write_output(output_path, delivery_doc)
    console.print(f"\n[bold green]✓[/] Delivery document written to [bold]{output_path}[/]")

    # ---- PDF (fail-open) ----
    if pdf:
        _export_pdf(output_path)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_generated(
    section: DeliverySection,
    features_dir: Path,
    repo: Repository,
) -> str:
    """Run RAG + LLM for a generated section. Returns the content string."""
    feature_name = section.feature or ""
    topic = section.topic or section.heading or feature_name

    # Load approved spec
    all_specs = load_all_specs(features_dir)
    approved = {s.name: s for s in all_specs if s.approved}
    matches = [s for name, s in approved.items() if feature_name in name]
    if not matches:
        console.print(
            f"  [yellow]⚠[/] Feature '{feature_name}' not found or not approved — skipping."
        )
        return f"*Feature '{feature_name}' is not approved. Run: foundry features approve {feature_name}*"

    feature_spec_content = matches[0].content

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

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as prog:
        prog.add_task("  Retrieving…", total=None)
        try:
            candidates = retrieve(topic, repo, retriever_config)
        except RuntimeError as exc:
            console.print(f"  [red]Error:[/] retrieve failed: {exc}")
            return f"*Retrieval failed for feature '{feature_name}': {exc}*"

    ctx = assemble(topic, candidates, assembler_config)

    summaries = [s for _, s in repo.list_summaries(limit=prompt_config.max_source_summaries)]
    prompt = build_prompt(
        query=topic,
        chunks=ctx.chunks,
        config=prompt_config,
        feature_spec=feature_spec_content,
        source_summaries=summaries,
    )

    validate_api_key(_GENERATION_MODEL)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as prog:
        prog.add_task(f"  Generating with {_GENERATION_MODEL}…", total=None)
        content = complete(
            model=_GENERATION_MODEL,
            messages=[
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_message},
            ],
            max_tokens=4096,
        )

    if section.show_attributions:
        content = add_attribution(content, ctx.chunks)

    console.print(f"  [green]✓[/] Generated ({len(ctx.chunks)} chunks)")
    return content


def _build_file(section: DeliverySection) -> str:
    """Return content block for a file section."""
    path_str = section.path or ""
    description = section.description or ""

    lines: list[str] = []
    if description:
        lines.append(description)
        lines.append("")

    if path_str:
        file_path = Path(path_str)
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            lines.append(f"**File:** `{path_str}`")
            lines.append(f"**Status:** ✓ Present ({size_mb:.1f} MB)")
            console.print(f"  [green]✓[/] File present: {path_str} ({size_mb:.1f} MB)")
        else:
            lines.append(f"**File:** `{path_str}`")
            lines.append("**Status:** ⚠ File missing — not yet delivered")
            console.print(f"  [yellow]⚠[/] File missing: {path_str}")
    else:
        lines.append("**Status:** (no path configured)")

    return "\n".join(lines)


def _build_physical(section: DeliverySection, slice_path: Path) -> str:
    """Return content block for a physical section. WI-ID never exposed."""
    description = section.description or ""
    tracking_wi = section.tracking_wi

    lines: list[str] = []
    if description:
        lines.append(description)
        lines.append("")

    if not slice_path.exists():
        lines.append("**Status:** ⚠ Physical tracking not available (no git scaffold)")
        console.print("  [yellow]⚠[/] No .forge/slice.yaml — physical status unavailable")
        return "\n".join(lines)

    slice_data = _load_slice(slice_path)
    if not slice_data or not tracking_wi:
        lines.append("**Status:** ✗ Pending")
        return "\n".join(lines)

    wi_status = _get_wi_status(slice_data, tracking_wi)
    if wi_status == "done":
        lines.append("**Status:** ✓ Delivered")
        console.print("  [green]✓[/] Physical: Delivered")
    elif wi_status == "in_progress":
        lines.append("**Status:** ⏳ In Progress")
        console.print("  [yellow]⏳[/] Physical: In Progress")
    else:
        lines.append("**Status:** ✗ Pending")
        console.print("  [dim]✗[/] Physical: Pending")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def _show_dry_run(
    sections: list[DeliverySection],
    features_dir: Path,
    slice_path: Path,
) -> None:
    console.print("\n[bold]Dry run — delivery plan:[/]\n")
    all_specs = load_all_specs(features_dir) if features_dir.is_dir() else []
    approved_names = {s.name for s in all_specs if s.approved}
    slice_data = _load_slice(slice_path) if slice_path.exists() else None

    for i, section in enumerate(sections, start=1):
        heading = section.heading or section.feature or section.path or f"Section {i}"
        stype = section.type

        if stype == "generated":
            fname = section.feature or ""
            approved = any(fname in name for name in approved_names)
            status = "[green]✓ Approved[/]" if approved else "[yellow]✗ Not approved[/]"
            console.print(f"  {i}. [bold]{heading}[/] (generated) — {status}")

        elif stype == "file":
            path_str = section.path or "(no path)"
            exists = Path(path_str).exists() if section.path else False
            status = "[green]✓ Present[/]" if exists else "[yellow]✗ Missing[/]"
            console.print(f"  {i}. [bold]{heading}[/] (file: {path_str}) — {status}")

        elif stype == "physical":
            if slice_data and section.tracking_wi:
                wi_status = _get_wi_status(slice_data, section.tracking_wi)
                if wi_status == "done":
                    status = "[green]✓ Done[/]"
                elif wi_status == "in_progress":
                    status = "[yellow]⏳ In Progress[/]"
                else:
                    status = "[dim]✗ Pending[/]"
            else:
                status = "[dim](no slice data)[/]"
            console.print(f"  {i}. [bold]{heading}[/] (physical) — {status}")

        else:
            console.print(f"  {i}. [bold]{heading}[/] ({stype}) — [red]unknown type[/]")

    console.print("\n[dim]No generation performed — dry run.[/]")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_all_approved(sections: list[DeliverySection], features_dir: Path) -> None:
    """Exit 1 if any type:generated section has an unapproved spec."""
    generated = [s for s in sections if s.type == "generated"]
    if not generated:
        return

    if not features_dir.is_dir():
        console.print(
            "[red]Error:[/] features/ directory not found — cannot validate generated sections.\n"
            "  Run: foundry features approve <name>"
        )
        raise typer.Exit(1)

    all_specs = load_all_specs(features_dir)
    approved_names = {s.name for s in all_specs if s.approved}

    unapproved = [
        s for s in generated if not any((s.feature or "") in name for name in approved_names)
    ]
    if unapproved:
        names = ", ".join(s.feature or "(unnamed)" for s in unapproved)
        console.print(
            f"[red]Error:[/] These generated sections have unapproved specs: {names}\n\n"
            "  Approve them first:\n"
            + "\n".join(
                f"    foundry features approve {s.feature}"
                for s in unapproved
                if s.feature
            )
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------


def _export_pdf(md_path: Path) -> None:
    """Convert *md_path* to PDF via Pandoc. Fail-open if Pandoc not found."""
    pandoc = shutil.which("pandoc")
    if not pandoc:
        console.print(
            "\n[yellow]⚠[/] Pandoc not found — PDF export skipped.\n"
            "  Install Pandoc: https://pandoc.org/installing.html\n"
            f"  Markdown output saved at: {md_path}"
        )
        return

    pdf_path = md_path.with_suffix(".pdf")
    try:
        import subprocess

        subprocess.run(
            [pandoc, str(md_path), "-o", str(pdf_path)],
            check=True,
            capture_output=True,
            shell=False,
        )
        console.print(f"  [green]✓[/] PDF written to [bold]{pdf_path}[/]")
    except Exception as exc:
        console.print(
            f"\n[yellow]⚠[/] Pandoc conversion failed: {exc}\n"
            f"  Markdown output saved at: {md_path}"
        )


# ---------------------------------------------------------------------------
# DB + slice helpers
# ---------------------------------------------------------------------------


def _open_db(db_path: Path) -> sqlite3.Connection:
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    return conn


def _load_slice(slice_path: Path) -> dict | None:
    if not slice_path.exists():
        return None
    try:
        data = yaml.safe_load(slice_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _get_wi_status(slice_data: dict, wi_id: str) -> str:
    for wi in slice_data.get("workitems", []):
        if wi.get("id") == wi_id:
            return str(wi.get("status", "pending"))
    return "pending"
