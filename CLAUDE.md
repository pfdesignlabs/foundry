# Foundry — Claude Code Control File

## What Foundry Is

Foundry is a **project-agnostic knowledge-to-document CLI tool**.

It ingests source material (Markdown, PDF, JSON, EPUB, plain text, git repos, URLs, audio),
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
| LLM / Embeddings | `litellm` (unified interface — `provider/model` format) |
| Default LLM | `openai/gpt-4o` |
| Default Embedding | `openai/text-embedding-3-small` |
| CLI | `typer` + `rich` |
| PDF parsing | `pypdf` |
| EPUB + HTML parsing | `beautifulsoup4` + `html2text` (GPL-3.0, intern gebruik — geen AGPL) |
| Audio transcriptie | `litellm.transcription()` → OpenAI Whisper |
| Testing | `pytest` |

---

## Repo Map

```
src/foundry/          # Engine — project-agnostic, no exceptions
  cli/                # CLI entry points
  db/                 # SQLite schema, sqlite-vec integration
  ingest/             # Chunkers per source type (PDF, MD, EPUB, JSON, txt, git, web, audio)
  rag/                # Retrieval + context assembly
  generate/           # LLM calls, prompt templates, output writers
  governance/         # foundry governance built-in (bash-intercept, audit, status)
  plan/               # foundry plan (LLM-assisted feature + WI generation)
tests/                # pytest, mirrors src/
tracking/
  features/           # F-*.md feature specs (F00–F07)
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
| 2 | Ingest | Chunkers (Markdown, PDF, JSON, EPUB, plain text, git, web, audio) |
| 3 | RAG + Generate | Retrieval, context assembly, token budget, LLM generation |
| 4 | Feature Gates | features/ parsing, approval check, gate enforcement |
| 5 | CLI Polish | foundry init/ingest/generate/build/features, project wizard |
| 6 | Project Governance | foundry wi/sprint/governance built-in, WI types, hardware lifecycle |
| 7 | LLM Planning | foundry plan, LLM-assisted feature + WI generation |

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
- **Always `yaml.safe_load()` — never `yaml.load()` without Loader (RCE vector).**
- **Never `shell=True` with user-supplied input — always `shell=False` + list args.**
- **Never store API keys in config files — keys via environment variables only.**
- **Always validate and confine file paths before opening (path traversal prevention).**

---

## Development Workflow

```bash
# First-time setup (run once per clone)
uv venv && source .venv/bin/activate
uv sync
git config core.hooksPath .forge/hooks/  # activate versioned git hooks

# Daily workflow
uv lock                             # pin transitive deps (commit uv.lock)
pytest                              # run tests (e2e excluded by default)
pytest -m e2e                       # run e2e tests (requires API keys)
ruff check src/                     # lint
mypy src/foundry/                   # type check
python .forge/governor.py status    # sprint status
```

**Sprint close (auto):** After `git pull` on develop following a PR merge, the
`post-merge` git hook automatically runs `python .forge/governor.py sprint-close`,
which archives the sprint record to `tracking/sprints/SP_XXX.md` and updates `tracking/STATUS.md`.

---

## Testing & Code Review Policy

**Test pyramid:**
```
tests/
  conftest.py           ← mock_litellm fixture, tmp_db fixture
  unit/
    db/                 ← test_repository.py, test_migrations.py
    ingest/             ← test_chunkers.py (parametrized), test_embedding_writer.py
    rag/                ← test_retriever.py, test_context_assembler.py
    cli/                ← test_commands.py (Typer CliRunner)
    test_config.py
    test_path_validation.py
  integration/          ← mocked LLM, real SQLite :memory:
    test_ingest_pipeline.py
    test_generate_pipeline.py
    test_deduplication.py
    test_recovery.py
  e2e/                  ← @pytest.mark.e2e, skipped unless FOUNDRY_RUN_E2E=1
    test_full_pipeline.py
```

**Testing rules:**
- All new code requires tests in `tests/` (mirrors `src/` structure)
- Unit tests: no real I/O, no real LLM calls — mock via `conftest.mock_litellm`
- Integration tests: mocked LiteLLM, real SQLite `:memory:` database
- E2E tests: `@pytest.mark.e2e` — require real API keys, skipped by default
- `pytest` (without `-m e2e`) must pass before any merge to `feat/*` or `develop`
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
