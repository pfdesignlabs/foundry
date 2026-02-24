"""Foundry CLI entry point (WI_0023, WI_0029, WI_0032, WI_0033, WI_0037, WI_0039, WI_0034)."""

from __future__ import annotations

import importlib.metadata
from typing import Annotated

import typer

from foundry.cli.features import features_app
from foundry.cli.generate import generate_cmd
from foundry.cli.init import init_cmd
from foundry.cli.ingest import ingest_cmd
from foundry.cli.remove import remove_cmd
from foundry.cli.status import status_cmd


def _version_callback(value: bool) -> None:
    if value:
        try:
            ver = importlib.metadata.version("foundry")
        except importlib.metadata.PackageNotFoundError:
            ver = "dev"
        typer.echo(f"foundry {ver}")
        raise typer.Exit()


app = typer.Typer(
    name="foundry",
    help=(
        "Foundry — knowledge-to-document CLI.\n\n"
        "  foundry generate  Operator review tool: per-feature draft via RAG + LLM.\n"
        "  foundry build     Client delivery: assemble all approved features into one document."
    ),
    add_completion=False,
)


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Foundry — knowledge-to-document CLI."""


app.command("init")(init_cmd)
app.command("ingest")(ingest_cmd)
app.command("generate")(generate_cmd)
app.command("status")(status_cmd)
app.command("remove")(remove_cmd)
app.add_typer(features_app, name="features")


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
