# Contributing to Foundry

Foundry is a knowledge-to-document CLI tool. This guide covers everything you
need to develop, test, and extend it.

---

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- An OpenAI API key (for e2e tests — unit and integration tests run without one)

### First-time setup

```bash
# Clone the repo
git clone https://github.com/pfdesignlabs/foundry.git
cd foundry

# Create virtual environment and install all dependencies
uv venv && source .venv/bin/activate
uv sync

# Activate versioned git hooks (run once per clone)
git config core.hooksPath .forge/hooks/
```

### Daily workflow

```bash
# Run all unit + integration tests (no API keys required)
pytest

# Run e2e tests (requires OPENAI_API_KEY)
pytest -m e2e

# Lint
ruff check src/

# Type check
mypy src/foundry/

# Lock transitive dependencies (commit uv.lock after changes)
uv lock
```

### API keys

For e2e tests only — never put keys in config files:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...   # optional, for Anthropic models
```

---

## Architecture

Foundry is split into focused modules. All code lives under `src/foundry/`.

### `db/` — Database layer

- **`connection.py`** — `Database` class: opens SQLite, loads the sqlite-vec extension
- **`schema.py`** — `initialize(conn)`: creates tables (`sources`, `chunks`,
  `chunks_fts`, `source_summaries`) and applies forward-only migrations
- **`vectors.py`** — `ensure_vec_table(conn, slug, dimensions)`: creates a per-model
  vec table on demand; `model_to_slug()` maps provider/model → table name
- **`repository.py`** — `Repository` class: all CRUD for sources, chunks, FTS5
  search, vec embeddings, and summaries. Single interface — no raw SQL elsewhere
- **`models.py`** — `Source` and `Chunk` dataclasses (plain Python, no ORM)

**Key decision:** Vec table keys are SQLite rowids (D0013). The rowid of a chunk
row is identical to the rowid used in its vec table, eliminating any UUID lookup.

### `ingest/` — Source ingestion pipeline

Each source type has its own chunker class:

| Class | Module | Handles |
|-------|--------|---------|
| `MarkdownChunker` | `markdown.py` | Heading-aware Markdown split |
| `PdfChunker` | `pdf.py` | PDF text extraction (pypdf) |
| `EpubChunker` | `epub.py` | EPUB chapter extraction (bs4 + html2text) |
| `JsonChunker` | `json_chunker.py` | JSON objects and arrays |
| `PlainTextChunker` | `plaintext.py` | Fixed-window with overlap |
| `GitChunker` | `git_chunker.py` | Git commits (local + remote clone) |
| `WebChunker` | `web.py` | URL fetch → plain text (SSRF-guarded) |
| `AudioChunker` | `audio.py` | Audio transcription via Whisper |

All chunkers inherit from `BaseChunker` (`base.py`) and implement `chunk(source_id, content, path) -> list[Chunk]`.

**Embedding** is handled by `EmbeddingWriter` (`embedding_writer.py`):
- Generates a context prefix per chunk (via LLM) for improved retrieval
- Calls `litellm.embedding()` and writes to the per-model vec table
- Checks API key and warns if an expensive model is configured

**Summarization** is handled by `DocumentSummarizer` (`summarizer.py`):
- Called once per source after all chunks are embedded
- Stores a plain-text summary in the `source_summaries` table

### `rag/` — Retrieval and context assembly

- **`retriever.py`** — `retrieve(query, repo, config) -> list[ScoredChunk]`
  - BM25 via SQLite FTS5 (`search_fts`)
  - Dense via sqlite-vec (`search_vec`)
  - HyDE: generates a hypothetical answer with a cheap model, embeds that
  - Fuses both ranked lists with Reciprocal Rank Fusion (`k=60`)

- **`assembler.py`** — `assemble(query, candidates, config) -> AssembledContext`
  - Batch relevance scoring (0-10, single LLM call for all candidates)
  - Conflict detection between top chunks (single LLM call)
  - Token budget enforcement (ordered by relevance score)

- **`llm_client.py`** — Thin wrappers around LiteLLM:
  - `complete()` — chat completion with retry/backoff
  - `embed()` — embedding with retry/backoff
  - `validate_api_key()` — checks env var before generation
  - `count_tokens()` / `get_context_window()` — provider-aware token counting

### `generate/` — Prompt templates and output

- **`templates.py`** — `build_prompt(query, chunks, config, feature_spec, source_summaries) -> PromptComponents`
  - Builds system prompt with sections: project brief → feature spec → source summaries → `<context>` chunk block
  - Token budget warning when total approaches model context window
  - Untrusted-data instruction inside `<context>` tags (prompt injection mitigation)

- **`writer.py`** — Output utilities:
  - `add_attribution(content, chunks)` — appends `[^N]: source, chunk N` footnotes
  - `validate_output_path(output)` — confines relative paths to CWD (path traversal prevention)
  - `check_overwrite(path, yes)` — interactive overwrite prompt
  - `write_output(path, content)` — atomic temp→rename write

### `gates/` — Feature approval gate

- **`parser.py`** — `load_all_specs(features_dir) -> list[FeatureSpec]`
  - Reads all `.md` files from `features/`
  - Detects the exact heading `## Approved` (case-sensitive, no trailing text)
  - Generation is blocked unless at least one approved spec exists

### `cli/` — Typer command entry points

Each command is a separate module:

| Command | Module | Description |
|---------|--------|-------------|
| `foundry init` | `init.py` | Interactive wizard + project scaffold |
| `foundry ingest` | `ingest.py` | Source ingestion pipeline |
| `foundry generate` | `generate.py` | Operator review tool (per-feature draft) |
| `foundry build` | `build.py` | Client delivery document assembly |
| `foundry status` | `status.py` | Project overview and delivery readiness |
| `foundry remove` | `remove.py` | Source lifecycle management |
| `foundry features` | `features.py` | Feature spec list + approve |
| CLI entry | `main.py` | Typer app registration |
| Error messages | `errors.py` | Rich error + warning string builders |

### `config.py` — Configuration

Three-layer merge: `~/.foundry/config.yaml` → `foundry.yaml` → env vars.
CLI flags must be applied by the caller after `load_config()`.

Config key sections: `project:`, `embedding:`, `generation:`, `retrieval:`,
`chunkers:`, `delivery:`, `plan:`.

---

## Test Pyramid

```
tests/
  conftest.py           ← shared fixtures (tmp_db, mock_litellm)
  unit/
    db/                 ← repository, migrations, vec tables
    ingest/             ← chunkers (parametrized), embedding_writer
    rag/                ← retriever, context_assembler
    cli/                ← all CLI commands via Typer CliRunner
    test_config.py      ← config loading, merging, validation
    test_path_validation.py
  integration/          ← mocked LLM + real SQLite :memory:
    test_ingest_pipeline.py
    test_generate_pipeline.py
    test_deduplication.py
    test_recovery.py
  e2e/                  ← @pytest.mark.e2e, real API keys, skipped by default
    test_full_pipeline.py
```

**Rules:**
- Unit tests: no real I/O, no real LLM calls. Mock LiteLLM via `unittest.mock.patch`
- Integration tests: real SQLite `:memory:` database, mocked LLM
- E2E tests: require `FOUNDRY_RUN_E2E=1` and real API keys; skipped by default
- `pytest` (no flags) must pass before any PR merge
- Coverage target: ≥80% for Phase 3+ modules

### Running tests

```bash
pytest                  # unit + integration (fast, no API keys)
pytest -m e2e           # e2e only (requires API keys)
pytest tests/unit/cli/  # specific directory
pytest -k "test_init"   # keyword filter
```

---

## Branch and Commit Conventions

### Branch naming

```
wi/WI_XXXX-short-slug     work item branches (from feat/*)
feat/slug                  feature branches (from develop)
release/vX.Y.Z             release branches (from develop → main)
```

### Commit message format

```
[WI_XXXX] type(scope): short description

Longer explanation if needed.

Co-Authored-By: ...
```

Prefix options: `[WI_XXXX]`, `[FEATURE_TRACKING]`, `[DEV_GOVERNANCE]`

### Merge hierarchy

```
wi/* → feat/* → develop → main (via release/*)
```

No direct commits to `main` or `develop`. All merges via PR.

### Pull requests

PRs use `.github/PULL_REQUEST_TEMPLATE.md`. Checklist before merge:
- [ ] `pytest` passes (all unit + integration tests)
- [ ] `ruff check src/` is clean
- [ ] New code has tests
- [ ] `uv.lock` updated if dependencies changed

---

## Hard Rules

These are non-negotiable and enforced by code review:

| Rule | Reason |
|------|--------|
| Always `yaml.safe_load()` — never `yaml.load()` without Loader | Prevents RCE via arbitrary object construction |
| Always `shell=False` with list args for subprocess | Prevents command injection |
| Never store API keys in config files | Keys belong in env vars only |
| Always validate and confine file paths before `open()` | Prevents path traversal |
| No project-specific code in `src/foundry/` | Engine must be project-agnostic |
| No new dependency without updating `pyproject.toml` + `uv sync` | Keeps lockfile clean |

---

## How to Add a New Chunker

1. Create `src/foundry/ingest/myformat.py`

```python
from foundry.ingest.base import BaseChunker
from foundry.db.models import Chunk


class MyFormatChunker(BaseChunker):
    """Chunker for MyFormat files."""

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        # Split content into text segments
        segments = self._split_fixed_window(content)  # or custom logic
        return self._make_chunks(source_id, segments)
```

2. Register the MIME/extension mapping in `src/foundry/cli/ingest.py` inside `_detect_type()`.

3. Add tests in `tests/unit/ingest/test_myformat_chunker.py` (parametrized, no I/O).

4. Add the dependency to `pyproject.toml` if needed and run `uv sync && uv lock`.

---

## How to Add a New CLI Command

1. Create `src/foundry/cli/mycommand.py` with a Typer function:

```python
from typing import Annotated
import typer

def mycommand_cmd(
    arg: Annotated[str, typer.Option("--arg", help="Description.")],
) -> None:
    """Short command description shown in --help."""
    ...
```

2. Register it in `src/foundry/cli/main.py`:

```python
from foundry.cli.mycommand import mycommand_cmd
app.command("mycommand")(mycommand_cmd)
```

3. Add tests in `tests/unit/cli/test_mycommand.py` using `typer.testing.CliRunner`.

4. Update `README.md` CLI reference section.

---

## Governance

The `.forge/` directory contains runtime enforcement (for the Foundry repo itself):

- `governor.py` — evaluates git operations against contracts
- `contracts/` — YAML rules for commits, branches, merge strategy, work items
- `slice.yaml` — active sprint tracking (machine-readable source of truth)
- `audit.jsonl` — append-only event log (gitignored)

Claude Code hooks in `.claude/settings.json` invoke the governor automatically.
Branch naming violations are hard-blocked. Direct pushes to `main`/`develop` are hard-blocked.
