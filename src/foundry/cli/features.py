"""foundry features CLI commands (WI_0032, WI_0033).

Commands:
  foundry features list             — show all feature specs with approval status
  foundry features approve <name>   — register approval in a spec file
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from foundry.gates.parser import FeatureSpec, load_all_specs, parse_spec

console = Console()

features_app = typer.Typer(
    name="features",
    help="Manage feature specs (list, approve).",
    add_completion=False,
)

_FEATURES_DIR = Path("features")


@features_app.command("list")
def features_list_cmd(
    features_dir: Annotated[
        Path,
        typer.Option("--features-dir", hidden=True, help="Override features/ path (for testing)."),
    ] = _FEATURES_DIR,
) -> None:
    """List all feature specs and their approval status."""
    if not features_dir.is_dir():
        console.print(
            "[yellow]No features/ directory found.[/]\n"
            "  Create feature specs in features/<name>.md\n"
            "  then run: foundry features approve <name>"
        )
        raise typer.Exit(0)

    specs = load_all_specs(features_dir)

    if not specs:
        console.print("[yellow]No feature specs found in features/.[/]")
        raise typer.Exit(0)

    table = Table(title="Feature Specs", show_header=True, header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Approved on")

    for spec in specs:
        status = "[green]✓ approved[/]" if spec.approved else "[yellow]✗ pending[/]"
        date_str = spec.approved_on or ""
        table.add_row(spec.name, status, date_str)

    console.print(table)

    approved_count = sum(1 for s in specs if s.approved)
    console.print(f"\n  {approved_count}/{len(specs)} approved")


@features_app.command("approve")
def features_approve_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Feature spec name without .md extension (e.g. wiring-guide)."),
    ],
    features_dir: Annotated[
        Path,
        typer.Option("--features-dir", hidden=True, help="Override features/ path (for testing)."),
    ] = _FEATURES_DIR,
) -> None:
    """Register approval for a feature spec by appending ## Approved + date."""
    spec_path = features_dir / f"{name}.md"

    if not spec_path.exists():
        console.print(
            f"[red]Error:[/] Feature spec not found: features/{name}.md\n"
            f"  Available specs: {', '.join(p.stem for p in sorted(features_dir.glob('*.md'))) if features_dir.is_dir() else '(no features/ dir)'}"
        )
        raise typer.Exit(1)

    spec = parse_spec(spec_path)

    if spec.approved:
        console.print(
            f"[yellow]Already approved:[/] features/{name}.md\n"
            + (f"  Approved on: {spec.approved_on}" if spec.approved_on else "")
        )
        raise typer.Exit(0)

    today = date.today().isoformat()
    approval_block = f"\n## Approved\nGoedgekeurd op {today}\n"

    existing = spec_path.read_text(encoding="utf-8")
    spec_path.write_text(existing.rstrip("\n") + approval_block, encoding="utf-8")

    console.print(f"[green]✓[/] Approved: features/{name}.md  (date: {today})")
