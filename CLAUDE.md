# Foundry — Claude Code Control File

## What Foundry Is

Foundry is a **project-agnostic knowledge-to-document CLI tool**.

It ingests source material (Markdown, PDF, JSON, EPUB, plain text, git repos),
stores chunks + embeddings in a per-project SQLite database (sqlite-vec),
and generates structured Markdown documents via RAG + LLM.

**No claim extraction. No normalization pipeline. No PostgreSQL.**
RAG is the architecture. sqlite-vec is the vector store. Markdown is the output.

---

## Read First: Active Slice

**Always read `.forge/slice.yaml` before any action.**
Execute ONLY what is defined for the current sprint.

### Bootstrap (first session only)
If `.forge/slice.yaml` does not exist, this IS the bootstrap session.
Your first action is to create `.forge/slice.yaml` (WI_0006).
Do not execute any other work until the slice file exists.

---

## Architecture Non-Negotiables

Locked decisions. Deviations require an ADR in `tracking/decisions/`.

1. **Per-project SQLite** — one `.db` file per project, no shared state.
2. **sqlite-vec for vector search** — no Postgres, no Chroma, no Qdrant.
3. **Chunks + embeddings only** — no claim extraction, no ClaimRow tables.
4. **Project-agnostic engine** — no project-specific code in `src/foundry/`.
5. **Human-approved features as hard gate** — no `features/` = no generation.
6. **Datasheets first** — community content supplements, never overrides primary sources.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Packaging | `pyproject.toml` + `uv` |
| Vector DB | `sqlite-vec` |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | OpenAI `gpt-4o` |
| CLI | `typer` |
| PDF parsing | `pypdf` |
| EPUB parsing | `ebooklib` |
| Testing | `pytest` |

---

## Repo Map

```
src/foundry/          # Engine — project-agnostic, no exceptions
  cli/                # CLI entry points
  db/                 # SQLite schema, sqlite-vec integration
  ingest/             # Chunkers per source type
  rag/                # Retrieval + context assembly
  generate/           # LLM calls, prompt templates, output writers
tests/                # pytest, mirrors src/
tracking/
  features/           # F-*.md feature specs (F00–F05)
  decisions/          # DECISIONS.md — append-only ADR log
  STATUS.md           # Auto-generated sprint status (never edit manually)
.forge/               # Governance engine (governor + contracts + slice)
.claude/              # Claude Code hooks + skills
CLAUDE.md             # This file
```

---

## Branch Strategy

- `main` — stable releases only; merge via `release/*` PR
- `develop` — integration, always green; merge via `feat/*` PR
- `feat/slug` — feature branches (from develop); merge via PR to develop
- `wi/WI_XXXX-slug` — work item branches (from feat/*); merge via PR to feat/*
- `release/vX.Y.Z` — release branches (from develop); merge via PR to main

**Merge hierarchy:** `wi/* → feat/* → develop → main`

No force push. No direct commits to `main` or `develop`.

---

## Phase Structure

| Phase | Name | Scope |
|-------|------|-------|
| 0 | Scaffold | pyproject.toml, package skeleton, CLAUDE.md, governance |
| 1 | DB Layer | sqlite-vec schema, chunk + embedding tables |
| 2 | Ingest | Chunkers (Markdown, PDF, JSON, EPUB, plain text, git) |
| 3 | RAG + Generate | Retrieval, context assembly, LLM generation |
| 4 | Feature Gates | features/ parsing, approval check, gate enforcement |
| 5 | CLI Polish | foundry init/ingest/generate/features, dry-run |

Current phase and allowed outputs are always in `.forge/slice.yaml`.

---

## Session Discipline

1. Read `.forge/slice.yaml` first.
2. Work only within the defined sprint and allowed files.
3. Do not mix Planning, Execution, and Review in one session.
4. Max 5 files changed per session unless expanded in `.forge/slice.yaml`.

---

## Hard Rules

- No project-specific logic in `src/foundry/`.
- No claims table, normalization step, or multi-DB architecture.
- No new dependency without updating `pyproject.toml` + running `uv sync`.
- No commits without `[WI_XXXX]`, `[FEATURE_TRACKING]`, or `[DEV_GOVERNANCE]` prefix.
- No direct commits or merges to `main` or `develop`.
- If a required decision is missing: STOP and record in `tracking/decisions/DECISIONS.md`.

---

## Development Workflow

```bash
uv venv && source .venv/bin/activate
uv sync
pytest                              # run tests
ruff check src/                     # lint
mypy src/foundry/                   # type check
python .forge/governor.py status    # sprint status
```

---

## Testing & Code Review Policy

**Testing:**
- All new code requires tests in `tests/` (mirrors `src/` structure)
- `pytest` must pass before any merge to `feat/*` or `develop`
- Coverage target: ≥60% now, ≥80% from Phase 3 onward
- Bug fixes include a regression test

**Code review:**
- All PRs use `.github/PULL_REQUEST_TEMPLATE.md`
- Checklist: tests pass, ruff clean, no undocumented breaking changes
- WI evidence updated in `.forge/slice.yaml` before merging

**Static analysis:**
- `ruff check src/` — linting (enforced before merge)
- `mypy src/foundry/` — type checking (informational, not yet blocking)

---

## Governance

The `.forge/` directory contains runtime enforcement:
- `governor.py` — evaluates all git operations against contracts
- `contracts/` — YAML rules for commits, branches, merge strategy, work items
- `slice.yaml` — active sprint tracking (machine-readable source of truth)
- `audit.jsonl` — append-only event log (gitignored)

Claude Code hooks in `.claude/settings.json` invoke the governor automatically.
Violations of branch naming are **hard-blocked** (exit 2).
Direct pushes to `main` or `develop` are **hard-blocked**.
