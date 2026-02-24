#!/usr/bin/env python3
"""Foundry Development Governor — Contract enforcement engine."""

import json
import re
import subprocess
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from collections import defaultdict

FORGE_DIR = Path(".forge")
CONTRACTS_DIR = FORGE_DIR / "contracts"
SLICE_FILE = FORGE_DIR / "slice.yaml"
AUDIT_LOG = FORGE_DIR / "audit.jsonl"
STATUS_MD = Path("tracking") / "STATUS.md"


def _has_evidence(wi: dict) -> bool:
    """Physical WIs require outcome; code WIs require evidence files."""
    if wi.get("type") == "physical":
        return bool((wi.get("outcome") or "").strip())
    return bool(wi.get("evidence"))


COMMIT_PATTERN = re.compile(
    r"^\[(WI_\d{4}|FEATURE_TRACKING|DEV_GOVERNANCE)\]\s+"
    r"(feat|fix|refactor|test|docs|chore|ci)\(.+\):\s+.+"
)

BRANCH_PATTERN = re.compile(
    r"^(wi/WI_\d{4}-.+|feat/.+|release/v\d+\.\d+\.\d+|hotfix/.+|main|develop)$"
)

PROTECTED_BRANCHES = {"main", "develop"}


class Verdict(Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class Governor:
    def __init__(self):
        self.contracts = self._load_contracts()
        self.slice = self._load_slice()

    def _load_contracts(self) -> list[dict]:
        contracts = []
        if CONTRACTS_DIR.exists():
            for f in sorted(CONTRACTS_DIR.glob("*.yaml")):
                try:
                    contracts.append(yaml.safe_load(f.read_text()))
                except yaml.YAMLError as e:
                    print(f"Warning: could not load contract {f}: {e}", file=sys.stderr)
        return contracts

    def _load_slice(self) -> dict:
        if SLICE_FILE.exists():
            return yaml.safe_load(SLICE_FILE.read_text()) or {}
        return {}

    def check_commit_message(self, message: str) -> list[dict]:
        violations = []
        if not COMMIT_PATTERN.match(message.strip()):
            violations.append({
                "contract": "commit-discipline",
                "rule": "commit-references-workitem",
                "enforce": "warn",
                "message": (
                    f"Commit message voldoet niet aan format: "
                    f"[WI_XXXX] type(scope): description. Got: '{message[:60]}'"
                ),
            })
        return violations

    def check_branch_name(self, branch: str) -> list[dict]:
        violations = []
        if not BRANCH_PATTERN.match(branch):
            violations.append({
                "contract": "merge-strategy",
                "rule": "branch-naming",
                "enforce": "hard-block",
                "message": (
                    f"Branch naam '{branch}' voldoet niet aan naming convention. "
                    f"Gebruik: wi/WI_XXXX-slug, feat/slug, release/vX.Y.Z, of hotfix/slug"
                ),
            })
        return violations

    def check_work_in_slice(self, workitem_id: str) -> list[dict]:
        violations = []
        slice_data = self.slice.get("slice", {})
        # workitems are at root level of slice.yaml, not nested under slice:
        known_ids = [wi["id"] for wi in self.slice.get("workitems", [])]
        if workitem_id and workitem_id not in known_ids:
            violations.append({
                "contract": "workitem-discipline",
                "rule": "no-work-outside-slice",
                "enforce": "warn",
                "message": (
                    f"Workitem '{workitem_id}' niet gevonden in actieve slice "
                    f"'{slice_data.get('id', '?')}'"
                ),
            })
        return violations

    def check_active_limits(self) -> list[dict]:
        violations = []
        # workitems are at root level of slice.yaml
        active = [
            wi for wi in self.slice.get("workitems", [])
            if wi.get("status") == "in_progress"
        ]
        if len(active) > 2:
            violations.append({
                "contract": "workitem-discipline",
                "rule": "max-active-items",
                "enforce": "warn",
                "message": (
                    f"{len(active)} items actief (max 2): "
                    f"{[wi['id'] for wi in active]}"
                ),
            })
        return violations

    def slice_status(self) -> dict:
        slice_data = self.slice.get("slice", {})
        # workitems are at root level of slice.yaml
        workitems = self.slice.get("workitems", [])
        by_status: dict[str, list] = defaultdict(list)
        for wi in workitems:
            by_status[wi.get("status", "unknown")].append(wi["id"])
        missing_evidence = [
            wi["id"] for wi in workitems
            if wi.get("status") in ("in_progress", "done")
            and not _has_evidence(wi)
        ]
        target = slice_data.get("target")
        return {
            "slice_id": slice_data.get("id"),
            "slice_name": slice_data.get("name"),
            "target": str(target) if target is not None else None,
            "by_status": dict(by_status),
            "total": len(workitems),
            "completed": len(by_status.get("done", [])),
            "missing_evidence": missing_evidence,
            "warnings": self.check_active_limits(),
        }

    def write_status_md(self, status: dict):
        """Write comprehensive sprint STATUS.md with full WI history to tracking/."""
        icon = {"done": "✅", "in_progress": "🔄", "planned": "⬜", "blocked": "❌"}
        slice_data = self.slice.get("slice", {})
        workitems = self.slice.get("workitems", [])

        lines = [
            f"# Sprint {status['slice_id']} — {status['slice_name']}",
            "",
            f"**Target:** {status['target']}  ",
            f"**Started:** {slice_data.get('started', '?')}  ",
            f"**Voortgang:** {status['completed']}/{status['total']} work items done",
            "",
        ]

        goal = slice_data.get("goal", "").strip()
        if goal:
            lines += [f"**Doel:** {goal}", ""]

        if status["warnings"]:
            lines += ["## ⚠️ Waarschuwingen", ""]
            for w in status["warnings"]:
                lines.append(f"- {w['message']}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # Full WI history — one section per work item
        for wi in workitems:
            wi_id = wi["id"]
            wi_status = wi.get("status", "unknown")
            wi_type = wi.get("type", "code")
            # Physical WIs get 🔧 suffix on their status icon
            base_icon = icon.get(wi_status, "❓")
            wi_icon = f"{base_icon}🔧" if wi_type == "physical" else base_icon
            branch = wi.get("branch") or "—"
            type_label = " _(physical)_" if wi_type == "physical" else ""

            lines += [
                f"## {wi_icon} {wi_id} — {wi['title']}{type_label}",
                "",
                f"**Status:** {wi_status}  ",
                f"**Branch:** `{branch}`",
                "",
            ]

            desc = (wi.get("description") or "").strip()
            if desc:
                lines += ["**Beschrijving:**  ", desc, ""]

            criteria = wi.get("acceptance_criteria") or []
            if criteria:
                lines += ["**Acceptatiecriteria:**", ""]
                for c in criteria:
                    lines.append(f"{c}")
                lines.append("")

            evidence = wi.get("evidence") or []
            if evidence:
                ev_label = "**Evidence:**" if wi_type == "code" else "**Evidence / Bewijs:**"
                lines += [ev_label, ""]
                for e in evidence:
                    # URLs rendered as links, file paths as code, free text as plain
                    if str(e).startswith(("http://", "https://")):
                        lines.append(f"- [{e}]({e})")
                    elif any(str(e).startswith(p) for p in ("foto:", "meting:", "link:", "notitie:")):
                        lines.append(f"- {e}")
                    else:
                        lines.append(f"- `{e}`")
                lines.append("")

            outcome = (wi.get("outcome") or "").strip()
            if outcome:
                lines += ["**Uitkomst:**  ", outcome, ""]

            depends_on = wi.get("depends_on") or []
            if depends_on:
                lines += [f"**Afhankelijkheden:** {', '.join(depends_on)}", ""]

            lines.append("---")
            lines.append("")

        lines += [
            f"_Gegenereerd door governor op "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC_",
        ]
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        STATUS_MD.write_text("\n".join(lines) + "\n")

    def audit(self, event: str, details: dict, verdict: Verdict):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "event": event,
            "verdict": verdict.value,
            **details,
        }
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")

    @staticmethod
    def _extract_workitem(message: str) -> str | None:
        match = re.search(r"WI_\d{4}", message)
        return match.group(0) if match else None

    def evaluate(self, event: str, context: dict) -> dict:
        violations: list[dict] = []

        if event == "commit":
            violations += self.check_commit_message(context.get("message", ""))
            wi = self._extract_workitem(context.get("message", ""))
            if wi:
                violations += self.check_work_in_slice(wi)

        elif event == "branch-create":
            violations += self.check_branch_name(context.get("branch", ""))

        elif event == "session-start":
            try:
                status = self.slice_status()
                self.write_status_md(status)
                violations += self.check_active_limits()
                return {**status, "event": "session-start", "violations": violations}
            except Exception as e:
                violations.append({
                    "contract": "workitem-discipline",
                    "rule": "slice-unreadable",
                    "enforce": "hard-block",
                    "message": f"slice.yaml onleesbaar of corrupt: {e}",
                })

        elif event == "session-stop":
            status = self.slice_status()
            self.write_status_md(status)
            remaining = [
                wi["id"]
                for wi in self.slice.get("workitems", [])
                if wi.get("status") != "done"
            ]
            return {
                "event": "session-stop",
                "slice_id": status["slice_id"],
                "slice_name": status["slice_name"],
                "completed": status["completed"],
                "total": status["total"],
                "remaining": remaining,
                "missing_evidence": status["missing_evidence"],
            }

        elif event == "status":
            result = self.slice_status()
            self.write_status_md(result)
            return result

        elif event == "sprint-close":
            result = self.slice_status()
            self.write_status_md(result)
            sprint_id = result.get("slice_id") or "UNKNOWN"
            archive_dir = Path("tracking") / "sprints"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / f"{sprint_id}.md"
            import shutil
            shutil.copy2(STATUS_MD, archive_path)
            self.audit("sprint-close", {"sprint_id": sprint_id, "archive": str(archive_path)},
                       Verdict.ALLOW)
            return {"verdict": "allow", "sprint_id": sprint_id, "archived_to": str(archive_path)}

        has_block = any(v["enforce"] == "hard-block" for v in violations)
        has_warn = any(v["enforce"] == "warn" for v in violations)
        verdict = (
            Verdict.BLOCK if has_block
            else Verdict.WARN if has_warn
            else Verdict.ALLOW
        )
        self.audit(event, {"violations": violations, "context": context}, verdict)
        return {
            "verdict": verdict.value,
            "violations": violations,
            "violation_count": len(violations),
        }


def _handle_bash_intercept(gov: "Governor"):
    """Handle PreToolUse Bash hook — reads stdin, extracts command, enforces contracts."""
    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    command = (hook_input.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    violations: list[dict] = []

    # git push → BLOCK on protected branches
    if re.search(r"\bgit\s+push\b", command):
        for branch in PROTECTED_BRANCHES:
            if re.search(rf"\b{branch}\b", command):
                violations.append({
                    "contract": "merge-strategy",
                    "rule": "no-direct-push-protected",
                    "enforce": "hard-block",
                    "message": (
                        f"Directe push naar '{branch}' is geblokkeerd. "
                        f"Gebruik een PR via feat/* of release/* branch."
                    ),
                })
                break

    # git merge → enforce merge-source-discipline
    elif re.search(r"\bgit\s+merge\b", command):
        # Extract source branch: last non-flag argument
        merge_args = re.sub(r"^.*git\s+merge\s+", "", command).split()
        source_branch = None
        for arg in reversed(merge_args):
            if not arg.startswith("-"):
                source_branch = arg
                break

        # Get current branch via subprocess (fail-open on error)
        current_branch: str | None = None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            current_branch = result.stdout.strip() or None
        except Exception:
            pass

        if source_branch and current_branch:
            if current_branch == "develop":
                if not re.match(r"^(feat/.+|release/v\d+\.\d+\.\d+)$", source_branch):
                    violations.append({
                        "contract": "merge-strategy",
                        "rule": "merge-source-discipline",
                        "enforce": "hard-block",
                        "message": (
                            f"Merge naar 'develop' is alleen toegestaan vanuit feat/* of "
                            f"release/* branches. Bron: '{source_branch}'"
                        ),
                    })
            elif current_branch == "main":
                if not re.match(r"^release/v\d+\.\d+\.\d+$", source_branch):
                    violations.append({
                        "contract": "merge-strategy",
                        "rule": "merge-source-discipline",
                        "enforce": "hard-block",
                        "message": (
                            f"Merge naar 'main' is alleen toegestaan vanuit release/* branches. "
                            f"Bron: '{source_branch}'"
                        ),
                    })
            elif re.match(r"^feat/.+$", current_branch):
                if not re.match(r"^wi/WI_\d{4}-.+$", source_branch):
                    violations.append({
                        "contract": "merge-strategy",
                        "rule": "merge-source-discipline",
                        "enforce": "warn",
                        "message": (
                            f"Merge naar feat/* branch '{current_branch}' is aanbevolen "
                            f"vanuit wi/* branches. Bron: '{source_branch}'"
                        ),
                    })
        else:
            # Fallback: warn when protected branch mentioned in command
            for branch in PROTECTED_BRANCHES:
                if re.search(rf"\b{branch}\b", command):
                    violations.append({
                        "contract": "merge-strategy",
                        "rule": "no-direct-merge-protected",
                        "enforce": "warn",
                        "message": f"Directe merge in '{branch}' — overweeg een PR.",
                    })

    # git commit → check message format + slice membership + pytest on staged .py files
    elif re.search(r"\bgit\s+commit\b", command):
        msg_match = re.search(r'-m\s+["\']([^"\']+)["\']', command)
        if msg_match:
            msg = msg_match.group(1)
            violations += gov.check_commit_message(msg)
            wi = gov._extract_workitem(msg)
            if wi:
                violations += gov.check_work_in_slice(wi)

        # Run pytest if staged .py files — fail-open, 60s timeout
        try:
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, timeout=5,
            )
            has_py = any(f.endswith(".py") for f in staged.stdout.splitlines() if f)
            if has_py:
                pytest_run = subprocess.run(
                    ["python", "-m", "pytest", "--tb=short", "-q"],
                    capture_output=True, text=True, timeout=60,
                )
                if pytest_run.returncode != 0:
                    output = (pytest_run.stdout + pytest_run.stderr).strip()
                    violations.append({
                        "contract": "testing",
                        "rule": "pytest-on-commit",
                        "enforce": "warn",
                        "message": (
                            f"pytest gefaald (fail-open — commit gaat door):\n"
                            + "\n".join(output.splitlines()[-20:])
                        ),
                    })
        except Exception:
            pass  # fail-open: pytest errors blokkeren nooit een commit

    # git checkout -b / switch -c / branch → check branch naming
    elif re.search(r"\bgit\s+(checkout\s+-b|switch\s+-c|branch)\b", command):
        branch_match = re.search(
            r"(?:checkout\s+-b|switch\s+-c|branch)\s+(\S+)", command
        )
        if branch_match:
            violations += gov.check_branch_name(branch_match.group(1))

    if not violations:
        sys.exit(0)

    has_block = any(v["enforce"] == "hard-block" for v in violations)
    verdict = Verdict.BLOCK if has_block else Verdict.WARN
    gov.audit(
        "bash-intercept",
        {"command": command[:200], "violations": violations},
        verdict,
    )

    if verdict == Verdict.BLOCK:
        msgs = "\n".join(f"  ❌ {v['message']}" for v in violations if v["enforce"] == "hard-block")
        print(f"🚫 Governor BLOCK:\n{msgs}", file=sys.stderr)
        sys.exit(2)
    else:
        msgs = "\n".join(f"  ⚠️ {v['message']}" for v in violations)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"⚠️ Governor waarschuwingen:\n{msgs}",
            }
        }))
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: governor.py <event> [--context JSON]\n"
            "Events: commit, branch-create, session-start, status, sprint-close, bash-intercept",
            file=sys.stderr,
        )
        sys.exit(1)

    event = sys.argv[1]

    if event == "bash-intercept":
        gov = Governor()
        _handle_bash_intercept(gov)
        sys.exit(0)

    if event == "audit-summary":
        if not AUDIT_LOG.exists():
            print("Geen audit log gevonden.", file=sys.stderr)
            sys.exit(0)
        lines = AUDIT_LOG.read_text().splitlines()
        # Show last 20 entries
        recent = lines[-20:]
        entries = []
        for line in recent:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        icon = {Verdict.ALLOW.value: "✅", Verdict.WARN.value: "⚠️ ", Verdict.BLOCK.value: "❌"}
        print(f"Audit trail — laatste {len(entries)} events:\n")
        for e in entries:
            ts = e.get("timestamp", "?")[:16].replace("T", " ")
            verdict = e.get("verdict", "?")
            event_name = e.get("event", "?")
            marker = icon.get(verdict, "❓")
            violations = e.get("violations", [])
            msg = violations[0]["message"][:60] if violations else ""
            print(f"  {marker} {ts}  {event_name:<20} {verdict:<8}  {msg}")
        sys.exit(0)

    # Only --context arg is supported; stdin is reserved for bash-intercept
    context: dict = {}
    if "--context" in sys.argv:
        idx = sys.argv.index("--context")
        context = json.loads(sys.argv[idx + 1])

    gov = Governor()
    result = gov.evaluate(event, context)

    if event == "session-start":
        violations = result.get("violations", [])
        has_block = any(v["enforce"] == "hard-block" for v in violations)
        completed = result.get("completed", "?")
        total = result.get("total", "?")
        slice_id = result.get("slice_id", "?")
        slice_name = result.get("slice_name", "?")
        target = result.get("target", "?")
        missing = result.get("missing_evidence", [])

        banner_lines = [
            f"🔧 Foundry Governor — Sessie gestart",
            f"Sprint {slice_id}: {slice_name}",
            f"Voortgang: {completed}/{total} done | Target: {target}",
        ]
        if missing:
            banner_lines.append(f"⚠️  Missing evidence: {', '.join(missing)}")
        for v in violations:
            prefix = "❌" if v["enforce"] == "hard-block" else "⚠️ "
            banner_lines.append(f"{prefix} {v['message']}")

        print("\n".join(banner_lines), file=sys.stderr)

        # additionalContext for Claude
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(banner_lines),
            }
        }))

        if has_block:
            sys.exit(2)
        sys.exit(0)

    if event == "session-stop":
        completed = result.get("completed", "?")
        total = result.get("total", "?")
        slice_id = result.get("slice_id", "?")
        remaining = result.get("remaining", [])
        missing = result.get("missing_evidence", [])

        lines = [
            f"🏁 Foundry Governor — Sessie afgesloten",
            f"Sprint {slice_id}: {completed}/{total} done",
        ]
        if remaining:
            lines.append(f"Nog open: {', '.join(remaining)}")
        if missing:
            lines.append(f"⚠️  Missing evidence: {', '.join(missing)}")
        lines.append("STATUS.md bijgewerkt.")

        print("\n".join(lines), file=sys.stderr)
        sys.exit(0)

    print(json.dumps(result, indent=2))

    if result.get("verdict") == "block":
        sys.exit(2)
    sys.exit(0)
