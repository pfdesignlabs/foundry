"""Foundry CLI entry point (WI_0023)."""

from __future__ import annotations

import importlib.metadata

import typer

from foundry.cli.ingest import ingest_cmd

app = typer.Typer(
    name="foundry",
    help="Foundry — knowledge-to-document CLI.",
    add_completion=False,
)

app.command("ingest")(ingest_cmd)


@app.command("version")
def version_cmd() -> None:
    """Show the installed Foundry version."""
    try:
        ver = importlib.metadata.version("foundry")
    except importlib.metadata.PackageNotFoundError:
        ver = "dev"
    typer.echo(f"foundry {ver}")


if __name__ == "__main__":
    app()
