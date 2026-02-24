"""Tests for foundry init command (WI_0034)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from foundry.cli.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Wizard input sequences
_CLIENT_NO_GIT = (
    "klant\n"         # project type
    "MyProject\n"     # naam
    "Custom PCB\n"    # klantbehoeftes
    "8 weeks\n"       # succesfactoren
    "Build docs\n"    # operator doelen
    "Theater, EMI\n"  # omgeving
    "DMX512, WiFi\n"  # capabilities
    "DMX spec, ESP32\n"  # gaps
    "n\n"             # git
)

_INTERN_NO_GIT = (
    "intern\n"
    "InternalTool\n"
    "A tool for internal use\n"
    "n\n"
)

_CLIENT_WITH_GIT = (
    "klant\n"
    "GitProject\n"
    "Custom PCB\n"
    "8 weeks\n"
    "Build docs\n"
    "Theater, EMI\n"
    "DMX512, WiFi\n"
    "DMX spec, ESP32\n"
    "y\n"
)


def _run_init(tmp_path: Path, input_str: str, global_cfg: Path | None = None) -> object:
    """Run foundry init in tmp_path with given wizard input."""
    args = [str(tmp_path)]
    result = runner.invoke(app, ["init"] + args, input=input_str)
    return result


# ---------------------------------------------------------------------------
# Basic scaffold — client project, no git
# ---------------------------------------------------------------------------


def test_init_creates_database(tmp_path: Path) -> None:
    result = _run_init(tmp_path, _CLIENT_NO_GIT)
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".foundry.db").exists()


def test_init_creates_foundry_yaml(tmp_path: Path) -> None:
    result = _run_init(tmp_path, _CLIENT_NO_GIT)
    assert result.exit_code == 0
    assert (tmp_path / "foundry.yaml").exists()


def test_foundry_yaml_has_project_name(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    data = yaml.safe_load((tmp_path / "foundry.yaml").read_text())
    assert data["project"]["name"] == "MyProject"


def test_foundry_yaml_has_brief(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    data = yaml.safe_load((tmp_path / "foundry.yaml").read_text())
    assert data["project"]["brief"] == "tracking/project-context.md"


def test_init_creates_features_dir(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert (tmp_path / "features").is_dir()


def test_init_creates_tracking_dir(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert (tmp_path / "tracking").is_dir()


def test_init_creates_project_context(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert (tmp_path / "tracking" / "project-context.md").exists()


def test_init_creates_sources_md(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert (tmp_path / "tracking" / "sources.md").exists()


def test_init_creates_work_items_md(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert (tmp_path / "tracking" / "work-items.md").exists()


def test_init_creates_build_plan_md(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert (tmp_path / "tracking" / "build-plan.md").exists()


def test_init_exits_zero(tmp_path: Path) -> None:
    result = _run_init(tmp_path, _CLIENT_NO_GIT)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Client wizard content
# ---------------------------------------------------------------------------


def test_client_project_context_has_klantbehoeftes(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / "tracking" / "project-context.md").read_text()
    assert "Custom PCB" in content


def test_client_project_context_has_capabilities(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / "tracking" / "project-context.md").read_text()
    assert "DMX512" in content
    assert "WiFi" in content


def test_client_sources_md_has_gaps(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / "tracking" / "sources.md").read_text()
    assert "DMX spec" in content
    assert "ESP32" in content


def test_client_work_items_md_has_capabilities(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / "tracking" / "work-items.md").read_text()
    assert "DMX512" in content
    assert "WiFi" in content


def test_client_project_context_has_system_prompt_note(tmp_path: Path) -> None:
    """Warn that project-context.md is loaded verbatim as system prompt."""
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / "tracking" / "project-context.md").read_text()
    assert "system prompt" in content.lower() or "verbatim" in content.lower()


# ---------------------------------------------------------------------------
# Intern wizard
# ---------------------------------------------------------------------------


def test_intern_project_creates_files(tmp_path: Path) -> None:
    result = _run_init(tmp_path, _INTERN_NO_GIT)
    assert result.exit_code == 0
    assert (tmp_path / ".foundry.db").exists()
    assert (tmp_path / "foundry.yaml").exists()


def test_intern_project_context_has_description(tmp_path: Path) -> None:
    _run_init(tmp_path, _INTERN_NO_GIT)
    content = (tmp_path / "tracking" / "project-context.md").read_text()
    assert "A tool for internal use" in content


def test_intern_foundry_yaml_has_project_name(tmp_path: Path) -> None:
    _run_init(tmp_path, _INTERN_NO_GIT)
    data = yaml.safe_load((tmp_path / "foundry.yaml").read_text())
    assert data["project"]["name"] == "InternalTool"


# ---------------------------------------------------------------------------
# .gitignore update
# ---------------------------------------------------------------------------


def test_init_updates_existing_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / ".gitignore").read_text()
    assert ".foundry.db" in content


def test_init_no_gitignore_does_not_crash(tmp_path: Path) -> None:
    result = _run_init(tmp_path, _CLIENT_NO_GIT)
    assert result.exit_code == 0


def test_init_does_not_duplicate_gitignore_entries(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".foundry.db\nfoundry.yaml\n", encoding="utf-8")
    _run_init(tmp_path, _CLIENT_NO_GIT)
    content = (tmp_path / ".gitignore").read_text()
    assert content.count(".foundry.db") == 1


# ---------------------------------------------------------------------------
# Invalid project type input
# ---------------------------------------------------------------------------


def test_init_invalid_project_type_then_valid(tmp_path: Path) -> None:
    """Wizard re-prompts on invalid project type."""
    input_str = "INVALID\nklant\nMyProject\nX\nX\nX\nX\nX\nX\nn\n"
    result = runner.invoke(app, ["init", str(tmp_path)], input=input_str)
    assert result.exit_code == 0
    assert (tmp_path / ".foundry.db").exists()


# ---------------------------------------------------------------------------
# Already initialized
# ---------------------------------------------------------------------------


def test_init_already_exists_cancel(tmp_path: Path) -> None:
    """If .foundry.db exists, user can cancel re-init."""
    (tmp_path / ".foundry.db").touch()
    result = runner.invoke(app, ["init", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output or "cancel" in result.output.lower()


def test_init_already_exists_continue(tmp_path: Path) -> None:
    """If .foundry.db exists, user can confirm re-init."""
    (tmp_path / ".foundry.db").touch()
    result = runner.invoke(app, ["init", str(tmp_path)], input="y\n" + _CLIENT_NO_GIT)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Git scaffold
# ---------------------------------------------------------------------------


def test_init_git_scaffold_creates_forge_dir(tmp_path: Path) -> None:
    result = _run_init(tmp_path, _CLIENT_WITH_GIT)
    assert result.exit_code == 0
    assert (tmp_path / ".forge").is_dir()


def test_init_git_scaffold_creates_slice_yaml(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    assert (tmp_path / ".forge" / "slice.yaml").exists()


def test_init_git_scaffold_slice_is_valid_yaml(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    data = yaml.safe_load((tmp_path / ".forge" / "slice.yaml").read_text())
    assert "slice" in data
    assert "workitems" in data


def test_init_git_scaffold_creates_contracts(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    contracts = tmp_path / ".forge" / "contracts"
    assert (contracts / "merge-strategy.yaml").exists()
    assert (contracts / "commit-discipline.yaml").exists()
    assert (contracts / "workitem-discipline.yaml").exists()


def test_init_git_scaffold_creates_hook(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    hook = tmp_path / ".forge" / "hooks" / "pre-bash.sh"
    assert hook.exists()


def test_init_git_hook_is_executable(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    hook = tmp_path / ".forge" / "hooks" / "pre-bash.sh"
    assert hook.stat().st_mode & 0o100  # owner-execute bit


def test_init_git_hook_is_fail_open(tmp_path: Path) -> None:
    """Hook exits 0 if foundry not in PATH (fail-open)."""
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    content = (tmp_path / ".forge" / "hooks" / "pre-bash.sh").read_text()
    assert "exit 0" in content


def test_init_git_scaffold_creates_claude_settings(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_init_git_scaffold_creates_claude_md(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    assert (tmp_path / "CLAUDE.md").exists()


def test_init_git_scaffold_claude_md_has_project_name(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert "GitProject" in content


def test_init_git_scaffold_creates_gitignore(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_WITH_GIT)
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert ".foundry.db" in content
    assert "foundry.yaml" in content
    assert ".forge/audit.jsonl" in content


def test_init_git_no_skips_forge_dir(tmp_path: Path) -> None:
    """When git=N, .forge/ should not be created."""
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert not (tmp_path / ".forge").exists()


def test_init_git_no_skips_claude_md(tmp_path: Path) -> None:
    _run_init(tmp_path, _CLIENT_NO_GIT)
    assert not (tmp_path / "CLAUDE.md").exists()
