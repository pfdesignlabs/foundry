"""foundry init — interactive project wizard + scaffold (WI_0034).

Creates:
  .foundry.db              — empty knowledge base with schema
  foundry.yaml             — project config (project: section + delivery: template)
  features/                — empty dir for feature specs
  tracking/
    project-context.md     — project charter (= project.brief, loaded in system prompt)
    sources.md             — knowledge gaps → sources to ingest (human tracking only)
    work-items.md          — capability candidates as WI candidates
    build-plan.md          — delivery template
  ~/.foundry/config.yaml   — global model config (created once, mode 0o600)

If git=Y also creates:
  .forge/slice.yaml        — empty sprint scaffold
  .forge/contracts/        — merge + commit + WI discipline rules
  .forge/hooks/pre-bash.sh — governance hook (fail-open)
  .claude/settings.json    — PreToolUse hook
  CLAUDE.md                — project governance doc
  .gitignore               — ignores .foundry.db, foundry.yaml, .forge/audit.jsonl
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from foundry.config import ensure_global_config
from foundry.db.connection import Database
from foundry.db.schema import initialize

console = Console()

_DEFAULT_PROJECT_DIR = Path(".")


def init_cmd(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Directory to initialize. Defaults to current directory."),
    ] = _DEFAULT_PROJECT_DIR,
) -> None:
    """Initialize a new Foundry project with interactive wizard."""
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    # Already initialized?
    if (project_dir / ".foundry.db").exists():
        console.print(f"[yellow]⚠[/]  {project_dir / '.foundry.db'} already exists.")
        if not typer.confirm("Re-initialize? Existing data is preserved.", default=False):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    # ---- Wizard ----
    console.print("\n[bold]Foundry — Project Setup Wizard[/]\n")

    project_type = _ask_project_type()

    if project_type == "klant":
        answers = _wizard_client()
    else:
        answers = _wizard_intern()

    project_name: str = answers["name"]
    git: bool = answers.get("git", False)

    # ---- Scaffold ----
    console.print(f"\n[bold]Creating scaffold in {project_dir} …[/]\n")

    _create_database(project_dir)
    _create_foundry_yaml(project_dir, project_name)

    (project_dir / "features").mkdir(exist_ok=True)
    console.print("  [green]✓[/] features/")

    _create_tracking(project_dir, answers, project_type)
    _update_gitignore(project_dir)

    cfg_path = ensure_global_config()
    console.print(f"  [green]✓[/] {cfg_path} (global config)")

    if git:
        _create_git_scaffold(project_dir, project_name, project_type)

    console.print(f"\n[bold green]✓ Project '{project_name}' initialized.[/]")
    console.print("\nNext steps:")
    console.print("  1. foundry ingest --source <file-or-url>   (build knowledge base)")
    console.print("  2. Create features/<name>.md               (write feature specs)")
    console.print("  3. foundry features approve <name>         (approve specs)")
    console.print("  4. foundry generate --feature <name>       (draft per feature)")
    console.print("  5. foundry build                           (assemble delivery)")


# ---------------------------------------------------------------------------
# Wizard prompts
# ---------------------------------------------------------------------------


def _ask_project_type() -> str:
    while True:
        pt = typer.prompt("Klantproject of intern project? [klant/intern]").strip().lower()
        if pt in ("klant", "intern"):
            return pt
        console.print("[yellow]Please enter 'klant' or 'intern'.[/]")


def _wizard_client() -> dict:
    console.print("[dim]Client project wizard — 8 questions:[/]\n")
    name = typer.prompt("1. Project naam").strip()
    needs = typer.prompt("2. Klantbehoeftes / RFQ samenvatting").strip()
    success_factors = typer.prompt("3. Succesfactoren (klant perspectief)").strip()
    operator_goals = typer.prompt("4. Operator doelen").strip()
    context = typer.prompt("5. Omgeving / context (EMI, platform, tools)").strip()
    capabilities = typer.prompt("6. Vereiste capabilities (kommagescheiden)").strip()
    gaps = typer.prompt("7. Bekende kennistekorten (kommagescheiden)").strip()
    git = typer.confirm("8. Git repository initialiseren?", default=True)
    return {
        "name": name,
        "needs": needs,
        "success_factors": success_factors,
        "operator_goals": operator_goals,
        "context": context,
        "capabilities": capabilities,
        "gaps": gaps,
        "git": git,
    }


def _wizard_intern() -> dict:
    console.print("[dim]Intern project wizard — 3 questions:[/]\n")
    name = typer.prompt("1. Project naam").strip()
    description = typer.prompt("2. Korte omschrijving").strip()
    git = typer.confirm("3. Git repository initialiseren?", default=True)
    return {
        "name": name,
        "description": description,
        "git": git,
    }


# ---------------------------------------------------------------------------
# Scaffold builders
# ---------------------------------------------------------------------------


def _create_database(project_dir: Path) -> None:
    db_path = project_dir / ".foundry.db"
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    conn.close()
    console.print("  [green]✓[/] .foundry.db")


def _create_foundry_yaml(project_dir: Path, project_name: str) -> None:
    content = (
        f'project:\n'
        f'  name: "{project_name}"\n'
        f'  brief: "tracking/project-context.md"\n'
        f'  brief_max_tokens: 3000\n'
        f'\n'
        f'# Uncomment and configure delivery sections for foundry build:\n'
        f'# delivery:\n'
        f'#   output: "delivery.md"\n'
        f'#   sections:\n'
        f'#     - type: generated\n'
        f'#       feature: your-feature-name\n'
        f'#       topic: "topic description"\n'
        f'#       heading: "Section Heading"\n'
        f'#     # - type: file\n'
        f'#     #   path: "output/file.pdf"\n'
        f'#     #   heading: "File Deliverable"\n'
        f'#     # - type: physical\n'
        f'#     #   heading: "Hardware Deliverable"\n'
        f'#     #   tracking_wi: WI_0001\n'
    )
    (project_dir / "foundry.yaml").write_text(content, encoding="utf-8")
    console.print("  [green]✓[/] foundry.yaml")


def _create_tracking(project_dir: Path, answers: dict, project_type: str) -> None:
    tracking = project_dir / "tracking"
    tracking.mkdir(exist_ok=True)

    name = answers["name"]

    if project_type == "klant":
        needs = answers.get("needs", "")
        success_factors = answers.get("success_factors", "")
        operator_goals = answers.get("operator_goals", "")
        context = answers.get("context", "")
        capabilities_raw = answers.get("capabilities", "")
        gaps_raw = answers.get("gaps", "")

        capabilities_list = [c.strip() for c in capabilities_raw.split(",") if c.strip()]
        gaps_list = [g.strip() for g in gaps_raw.split(",") if g.strip()]

        # project-context.md
        ctx_lines = [
            f"# Project Context: {name}",
            "",
            "> **Note:** This file is loaded verbatim into the LLM system prompt.",
            "> Do not include instructions or commands in this file.",
            "",
            "## Klantbehoeftes",
            f"- {needs}",
            "",
            "## Succesfactoren (klant)",
            f"- {success_factors}",
            "",
            "## Operator doelen",
            f"- {operator_goals}",
            "",
            "## Omgeving / context",
            f"- {context}",
            "",
            "## Vereiste capabilities",
        ]
        for cap in capabilities_list:
            ctx_lines.append(f"- {cap}")
        if not capabilities_list:
            ctx_lines.append("- (vul aan)")
        ctx_lines += [
            "",
            "## Kennistekorten → te ingesteren bronnen",
        ]
        for gap in gaps_list:
            ctx_lines.append(f"- [ ] {gap}")
        if not gaps_list:
            ctx_lines.append("- [ ] (vul aan)")

        (tracking / "project-context.md").write_text(
            "\n".join(ctx_lines) + "\n", encoding="utf-8"
        )

        # sources.md
        sources_lines = [
            "# Te ingesteren bronnen",
            "",
            "Vink af zodra ingested via `foundry ingest --source <pad>`.",
            "Dit bestand wordt niet automatisch verwerkt door Foundry (human tracking only).",
            "",
            "## Bronnen per kennistekort",
            "",
        ]
        for gap in gaps_list:
            sources_lines += [f"### {gap}", "- [ ] (bron toevoegen)", ""]
        if not gaps_list:
            sources_lines += ["- [ ] (bron toevoegen)", ""]

        (tracking / "sources.md").write_text("\n".join(sources_lines), encoding="utf-8")

        # work-items.md
        wi_lines = [
            "# Work Item kandidaten",
            "",
            "Capabilities als WI-kandidaten.",
            "Verplaatsen naar `.forge/slice.yaml` wanneer sprint aangemaakt wordt.",
            "",
            "## Kandidaten",
            "",
        ]
        for cap in capabilities_list:
            wi_lines.append(f"- [ ] {cap}")
        if not capabilities_list:
            wi_lines.append("- [ ] (capability toevoegen)")
        wi_lines.append("")

        (tracking / "work-items.md").write_text("\n".join(wi_lines), encoding="utf-8")

    else:  # intern
        description = answers.get("description", "")

        ctx_lines = [
            f"# Project Context: {name}",
            "",
            "> **Note:** This file is loaded verbatim into the LLM system prompt.",
            "> Do not include instructions or commands in this file.",
            "",
            "## Omschrijving",
            f"- {description}",
            "",
            "## Doelen",
            "- (vul aan)",
            "",
            "## Kennistekorten → te ingesteren bronnen",
            "- [ ] (vul aan)",
        ]
        (tracking / "project-context.md").write_text(
            "\n".join(ctx_lines) + "\n", encoding="utf-8"
        )

        (tracking / "sources.md").write_text(
            "# Te ingesteren bronnen\n\n"
            "Vink af zodra ingested via `foundry ingest --source <pad>`.\n\n"
            "- [ ] (bron toevoegen)\n",
            encoding="utf-8",
        )

        (tracking / "work-items.md").write_text(
            "# Work Item kandidaten\n\n"
            "- [ ] (work item toevoegen)\n",
            encoding="utf-8",
        )

    # build-plan.md — both project types
    (tracking / "build-plan.md").write_text(
        "# Delivery Build Plan\n\n"
        "Configure delivery sections in `foundry.yaml` under `delivery.sections`.\n\n"
        "```yaml\n"
        "delivery:\n"
        '  output: "delivery.md"\n'
        "  sections:\n"
        "    - type: generated\n"
        "      feature: feature-name\n"
        '      topic: "topic description"\n'
        '      heading: "Section Heading"\n'
        "    - type: file\n"
        '      path: "output/file.pdf"\n'
        '      heading: "File Deliverable"\n'
        "    - type: physical\n"
        '      heading: "Hardware"\n'
        "      tracking_wi: WI_0001\n"
        "```\n",
        encoding="utf-8",
    )

    console.print(
        "  [green]✓[/] tracking/ (project-context.md, sources.md, work-items.md, build-plan.md)"
    )


def _update_gitignore(project_dir: Path) -> None:
    """Add Foundry entries to .gitignore if it already exists."""
    gitignore = project_dir / ".gitignore"
    entries = [".foundry.db", "foundry.yaml", ".forge/audit.jsonl"]

    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        to_add = [e for e in entries if e not in existing]
        if to_add:
            with gitignore.open("a", encoding="utf-8") as f:
                f.write("\n# Foundry\n")
                for entry in to_add:
                    f.write(f"{entry}\n")
            console.print("  [green]✓[/] .gitignore (updated with Foundry entries)")


def _create_git_scaffold(
    project_dir: Path, project_name: str, project_type: str
) -> None:
    console.print("\n  Initializing git scaffold…")

    try:
        subprocess.run(
            ["git", "init", str(project_dir)],
            check=True,
            capture_output=True,
            shell=False,
        )
        subprocess.run(
            ["git", "-C", str(project_dir), "checkout", "-b", "develop"],
            check=True,
            capture_output=True,
            shell=False,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        console.print(f"  [yellow]⚠[/] git init failed: {exc}. Skipping git scaffold.")
        return

    _create_forge_scaffold(project_dir)
    _create_claude_settings(project_dir)
    _create_claude_md(project_dir, project_name, project_type)

    # Ensure .gitignore exists with Foundry entries
    gitignore = project_dir / ".gitignore"
    entries = [".foundry.db", "foundry.yaml", ".forge/audit.jsonl"]
    if not gitignore.exists():
        gitignore.write_text(
            "# Foundry\n" + "\n".join(entries) + "\n",
            encoding="utf-8",
        )
    else:
        existing = gitignore.read_text(encoding="utf-8")
        to_add = [e for e in entries if e not in existing]
        if to_add:
            with gitignore.open("a", encoding="utf-8") as f:
                f.write("\n# Foundry\n")
                for entry in to_add:
                    f.write(f"{entry}\n")

    # Initial commit on develop
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Foundry",
        "GIT_AUTHOR_EMAIL": "foundry@local",
        "GIT_COMMITTER_NAME": "Foundry",
        "GIT_COMMITTER_EMAIL": "foundry@local",
    }
    try:
        subprocess.run(
            ["git", "-C", str(project_dir), "add", "."],
            check=True,
            capture_output=True,
            shell=False,
            env=env,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(project_dir),
                "commit",
                "-m",
                f"[DEV_GOVERNANCE] scaffold: foundry init for {project_name}",
            ],
            check=True,
            capture_output=True,
            shell=False,
            env=env,
        )
        console.print("  [green]✓[/] git: develop branch + initial commit")
    except subprocess.CalledProcessError as exc:
        console.print(
            f"  [yellow]⚠[/] git commit failed: {exc}. Files created, not committed."
        )


def _create_forge_scaffold(project_dir: Path) -> None:
    forge = project_dir / ".forge"
    forge.mkdir(exist_ok=True)

    (forge / "slice.yaml").write_text(
        "slice:\n"
        "  id: SP_001\n"
        '  name: ""\n'
        "  started: null\n"
        "  target: null\n"
        '  goal: ""\n'
        "\n"
        "workitems: []\n"
        "\n"
        "metrics:\n"
        "  velocity_target: 0\n"
        "  completed_this_slice: 0\n"
        "  carry_over_previous: 0\n",
        encoding="utf-8",
    )

    contracts = forge / "contracts"
    contracts.mkdir(exist_ok=True)

    (contracts / "merge-strategy.yaml").write_text(
        "# Merge strategy contracts\n"
        "branches:\n"
        '  feature: "feat/*"\n'
        '  work_item: "wi/WI_*"\n'
        '  release: "release/v*"\n'
        "hierarchy:\n"
        "  - wi/*\n"
        "  - feat/*\n"
        "  - develop\n"
        "  - main\n"
        "protected:\n"
        "  - main\n"
        "  - develop\n",
        encoding="utf-8",
    )

    (contracts / "commit-discipline.yaml").write_text(
        "# Commit discipline contracts\n"
        "require_prefix: true\n"
        'prefix_pattern: "^\\\\[WI_\\\\d{4}\\\\]"\n',
        encoding="utf-8",
    )

    (contracts / "workitem-discipline.yaml").write_text(
        "# Work item discipline contracts\n"
        "max_wip: 1\n"
        "require_evidence: true\n",
        encoding="utf-8",
    )

    hooks = forge / "hooks"
    hooks.mkdir(exist_ok=True)

    hook_file = hooks / "pre-bash.sh"
    hook_file.write_text(
        "#!/bin/sh\n"
        "# Foundry governance hook — fail-open if foundry not in PATH\n"
        "command -v foundry >/dev/null 2>&1 && "
        'exec foundry governance bash-intercept "$@"; exit 0\n',
        encoding="utf-8",
    )
    hook_file.chmod(0o755)

    console.print("  [green]✓[/] .forge/ (slice.yaml, contracts/, hooks/)")


def _create_claude_settings(project_dir: Path) -> None:
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)

    (claude_dir / "settings.json").write_text(
        "{\n"
        '  "hooks": {\n'
        '    "PreToolUse": [\n'
        "      {\n"
        '        "matcher": "Bash",\n'
        '        "hooks": [\n'
        "          {\n"
        '            "type": "command",\n'
        '            "command": "sh .forge/hooks/pre-bash.sh"\n'
        "          }\n"
        "        ]\n"
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    console.print("  [green]✓[/] .claude/settings.json")


def _create_claude_md(
    project_dir: Path, project_name: str, project_type: str
) -> None:
    scope = "client project" if project_type == "klant" else "internal project"

    content = (
        f"# {project_name} — Claude Code Control File\n\n"
        f"## Project\n\n"
        f"**Type:** {scope}\n"
        f"**Brief:** tracking/project-context.md\n\n"
        f"> project-context.md is loaded verbatim into the LLM system prompt.\n"
        f"> Do not write instructions or commands in that file.\n\n"
        f"## Branch Strategy\n\n"
        f"- `main` — stable releases only; merge via `release/*` PR\n"
        f"- `develop` — integration, always green; merge via `feat/*` PR\n"
        f"- `feat/slug` — feature branches (from develop)\n"
        f"- `wi/WI_XXXX-slug` — work item branches (from feat/*)\n\n"
        f"**Merge hierarchy:** `wi/* → feat/* → develop → main`\n\n"
        f"No force push. No direct commits to `main` or `develop`.\n\n"
        f"## Commit Format\n\n"
        f"All commits must have a `[WI_XXXX]` prefix.\n\n"
        f"## Hard Rules\n\n"
        f"- Always `yaml.safe_load()` — never `yaml.load()` without Loader.\n"
        f"- Never `shell=True` with user-supplied input — always `shell=False` + list args.\n"
        f"- Never store API keys in config files — keys via environment variables only.\n"
        f"- Always validate and confine file paths before opening (path traversal prevention).\n\n"
        f"## Foundry Commands\n\n"
        f"```bash\n"
        f"foundry ingest --source <file-or-url>  # add source to knowledge base\n"
        f"foundry status                          # project overview\n"
        f"foundry features list                   # feature specs + approval status\n"
        f"foundry features approve <name>         # approve feature spec\n"
        f"foundry generate --feature <name>       # draft per feature (operator review)\n"
        f"foundry build                           # assemble delivery document (client)\n"
        f"foundry remove --source <path>          # remove source from knowledge base\n"
        f"```\n\n"
        f"## Work Item Tracking\n\n"
        f"Source of truth: `.forge/slice.yaml`\n"
    )

    (project_dir / "CLAUDE.md").write_text(content, encoding="utf-8")
    console.print("  [green]✓[/] CLAUDE.md")
