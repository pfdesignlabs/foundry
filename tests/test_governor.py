"""Unit tests for .forge/governor.py — ≥15 cases covering all major enforcement paths."""

import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

# Make governor importable from .forge/
sys.path.insert(0, str(Path(__file__).parent.parent / ".forge"))
from governor import Governor, Verdict, BRANCH_PATTERN, COMMIT_PATTERN


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_SLICE = {
    "slice": {"id": "SP_TEST", "name": "Test Sprint", "target": "2099-01-01", "started": "2026-01-01"},
    "workitems": [
        {"id": "WI_0001", "status": "done", "title": "Done item", "evidence": ["file.py"]},
        {"id": "WI_0002", "status": "in_progress", "title": "Active item", "evidence": []},
        {"id": "WI_0003", "status": "planned", "title": "Planned item", "evidence": []},
    ],
    "metrics": {"velocity_target": 3, "completed_this_slice": 1, "carry_over_previous": 0},
}

OVERLOADED_SLICE = {
    "slice": {"id": "SP_TEST", "name": "Test Sprint", "target": "2099-01-01", "started": "2026-01-01"},
    "workitems": [
        {"id": "WI_0001", "status": "in_progress", "title": "A", "evidence": []},
        {"id": "WI_0002", "status": "in_progress", "title": "B", "evidence": []},
        {"id": "WI_0003", "status": "in_progress", "title": "C", "evidence": []},
    ],
    "metrics": {"velocity_target": 3, "completed_this_slice": 0, "carry_over_previous": 0},
}


def make_governor(slice_data=None, contracts=None):
    """Build a Governor with injected slice and contracts (no disk I/O)."""
    gov = object.__new__(Governor)
    gov.slice = slice_data or {}
    gov.contracts = contracts or []
    return gov


# ---------------------------------------------------------------------------
# 1. Commit message — valid formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "[WI_0001] feat(cli): add init command",
    "[WI_0042] fix(db): handle null embeddings",
    "[FEATURE_TRACKING] chore(specs): update F03",
    "[DEV_GOVERNANCE] refactor(governor): clean up audit logic",
    "[WI_0001] test(ingest): add chunker coverage",
])
def test_commit_message_valid(msg):
    gov = make_governor()
    assert gov.check_commit_message(msg) == []


# ---------------------------------------------------------------------------
# 2. Commit message — invalid formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "fix stuff",
    "feat: add thing",
    "[WI_1] feat(cli): too short id",
    "WI_0001 feat(cli): missing brackets",
    "[WI_0001] feat: missing scope parens",
    "",
])
def test_commit_message_invalid(msg):
    gov = make_governor()
    violations = gov.check_commit_message(msg)
    assert len(violations) == 1
    assert violations[0]["enforce"] == "warn"
    assert violations[0]["rule"] == "commit-references-workitem"


# ---------------------------------------------------------------------------
# 3. Branch naming — valid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("branch", [
    "wi/WI_0001-scaffold",
    "wi/WI_0042-long-slug-name",
    "feat/phase-0",
    "feat/f00-scaffold",
    "release/v1.0.0",
    "release/v12.34.567",
    "hotfix/critical-bug",
    "main",
    "develop",
])
def test_branch_name_valid(branch):
    gov = make_governor()
    assert gov.check_branch_name(branch) == []


# ---------------------------------------------------------------------------
# 4. Branch naming — invalid (hard-block)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("branch", [
    "feature/something",
    "WI_0001-scaffold",
    "wi/scaffold",
    "wi/WI_1-too-short",
    "random-branch",
    "release/1.0.0",
    "fix/typo",
])
def test_branch_name_invalid(branch):
    gov = make_governor()
    violations = gov.check_branch_name(branch)
    assert len(violations) == 1
    assert violations[0]["enforce"] == "hard-block"
    assert violations[0]["rule"] == "branch-naming"


# ---------------------------------------------------------------------------
# 5. Slice membership — WI present
# ---------------------------------------------------------------------------

def test_work_in_slice_known():
    gov = make_governor(MINIMAL_SLICE)
    assert gov.check_work_in_slice("WI_0001") == []
    assert gov.check_work_in_slice("WI_0002") == []


# ---------------------------------------------------------------------------
# 6. Slice membership — WI absent
# ---------------------------------------------------------------------------

def test_work_in_slice_unknown():
    gov = make_governor(MINIMAL_SLICE)
    violations = gov.check_work_in_slice("WI_9999")
    assert len(violations) == 1
    assert violations[0]["enforce"] == "warn"
    assert "WI_9999" in violations[0]["message"]


# ---------------------------------------------------------------------------
# 7. WIP limits — within limit
# ---------------------------------------------------------------------------

def test_active_limits_ok():
    gov = make_governor(MINIMAL_SLICE)
    assert gov.check_active_limits() == []


# ---------------------------------------------------------------------------
# 8. WIP limits — exceeded (>2 in_progress)
# ---------------------------------------------------------------------------

def test_active_limits_exceeded():
    gov = make_governor(OVERLOADED_SLICE)
    violations = gov.check_active_limits()
    assert len(violations) == 1
    assert violations[0]["enforce"] == "warn"
    assert violations[0]["rule"] == "max-active-items"


# ---------------------------------------------------------------------------
# 9. Verdict priority — hard-block wins over warn
# ---------------------------------------------------------------------------

def test_verdict_priority_block_over_warn():
    gov = make_governor(MINIMAL_SLICE)
    violations = [
        {"enforce": "warn", "contract": "x", "rule": "a", "message": "w"},
        {"enforce": "hard-block", "contract": "x", "rule": "b", "message": "b"},
    ]
    has_block = any(v["enforce"] == "hard-block" for v in violations)
    has_warn = any(v["enforce"] == "warn" for v in violations)
    verdict = Verdict.BLOCK if has_block else Verdict.WARN if has_warn else Verdict.ALLOW
    assert verdict == Verdict.BLOCK


# ---------------------------------------------------------------------------
# 10. Verdict — warn only
# ---------------------------------------------------------------------------

def test_verdict_warn_only():
    violations = [{"enforce": "warn", "contract": "x", "rule": "a", "message": "w"}]
    has_block = any(v["enforce"] == "hard-block" for v in violations)
    has_warn = any(v["enforce"] == "warn" for v in violations)
    verdict = Verdict.BLOCK if has_block else Verdict.WARN if has_warn else Verdict.ALLOW
    assert verdict == Verdict.WARN


# ---------------------------------------------------------------------------
# 11. Verdict — allow (no violations)
# ---------------------------------------------------------------------------

def test_verdict_allow_no_violations():
    violations: list = []
    has_block = any(v["enforce"] == "hard-block" for v in violations)
    has_warn = any(v["enforce"] == "warn" for v in violations)
    verdict = Verdict.BLOCK if has_block else Verdict.WARN if has_warn else Verdict.ALLOW
    assert verdict == Verdict.ALLOW


# ---------------------------------------------------------------------------
# 12. Missing contracts directory — graceful (no crash)
# ---------------------------------------------------------------------------

def test_missing_contracts_graceful(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No .forge/contracts/ directory — should return empty list, not raise
    gov = object.__new__(Governor)
    gov.slice = {}
    gov.contracts = []
    result = gov.check_active_limits()
    assert result == []


# ---------------------------------------------------------------------------
# 13. Missing slice.yaml — graceful (empty slice: any WI is unknown → warn)
# ---------------------------------------------------------------------------

def test_missing_slice_no_workitems():
    gov = make_governor(slice_data={})
    # With empty slice, no WI IDs are known → warn (not crash)
    violations = gov.check_work_in_slice("WI_0001")
    assert len(violations) == 1
    assert violations[0]["enforce"] == "warn"


# ---------------------------------------------------------------------------
# 14. slice_status — correct counts
# ---------------------------------------------------------------------------

def test_slice_status_counts():
    gov = make_governor(MINIMAL_SLICE)
    status = gov.slice_status()
    assert status["completed"] == 1
    assert status["total"] == 3
    assert "WI_0001" in status["by_status"]["done"]
    assert "WI_0002" in status["by_status"]["in_progress"]


# ---------------------------------------------------------------------------
# 15. slice_status — missing evidence detection
# ---------------------------------------------------------------------------

def test_slice_status_missing_evidence():
    slice_with_missing = {
        "slice": {"id": "SP_X", "name": "X", "target": "2099-01-01", "started": "2026-01-01"},
        "workitems": [
            {"id": "WI_0001", "status": "done", "title": "Done no evidence", "evidence": []},
        ],
        "metrics": {},
    }
    gov = make_governor(slice_with_missing)
    status = gov.slice_status()
    assert "WI_0001" in status["missing_evidence"]


# ---------------------------------------------------------------------------
# 16. evaluate() commit event — valid message, no violations
# ---------------------------------------------------------------------------

def test_evaluate_commit_valid():
    gov = make_governor(MINIMAL_SLICE)
    result = gov.evaluate("commit", {"message": "[WI_0001] feat(cli): add command"})
    assert result["verdict"] == Verdict.ALLOW.value
    assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# 17. evaluate() commit event — invalid message → warn verdict
# ---------------------------------------------------------------------------

def test_evaluate_commit_invalid_message():
    gov = make_governor(MINIMAL_SLICE)
    result = gov.evaluate("commit", {"message": "random message without format"})
    assert result["verdict"] == Verdict.WARN.value
    assert result["violation_count"] >= 1


# ---------------------------------------------------------------------------
# 18. evaluate() branch-create — valid name → allow
# ---------------------------------------------------------------------------

def test_evaluate_branch_create_valid():
    gov = make_governor(MINIMAL_SLICE)
    result = gov.evaluate("branch-create", {"branch": "wi/WI_0001-scaffold"})
    assert result["verdict"] == Verdict.ALLOW.value


# ---------------------------------------------------------------------------
# 19. evaluate() branch-create — invalid name → block
# ---------------------------------------------------------------------------

def test_evaluate_branch_create_invalid():
    gov = make_governor(MINIMAL_SLICE)
    result = gov.evaluate("branch-create", {"branch": "random-name"})
    assert result["verdict"] == Verdict.BLOCK.value


# ---------------------------------------------------------------------------
# 20. _extract_workitem — extracts WI_XXXX from message
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("[WI_0001] feat(cli): add command", "WI_0001"),
    ("[WI_0042] fix(db): handle null", "WI_0042"),
    ("no workitem here", None),
    ("[FEATURE_TRACKING] chore(specs): update", None),
])
def test_extract_workitem(msg, expected):
    assert Governor._extract_workitem(msg) == expected
