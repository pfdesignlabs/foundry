# Foundry

> Turn scattered source material into structured, actionable documents.

Large projects accumulate knowledge across datasheets, guides, documentation, community threads, and git history. That knowledge exists somewhere — but finding it, synthesising it, and turning it into something usable takes time and produces inconsistent results.

Foundry ingests source material, embeds it into a per-project knowledge base, and generates output documents using retrieval-augmented generation. What gets generated — format, structure, depth — is defined by the project profile.

---

## How it works

```
Sources → Ingest → Knowledge base (SQLite + sqlite-vec) → Generate → Output
```

1. **Ingest** — chunk and embed source files:
   ```bash
   foundry ingest --source datasheet.pdf
   foundry ingest --source docs/
   foundry ingest --source https://github.com/user/repo
   ```
   Supported: Markdown, PDF, EPUB, JSON, plain text, git repos.

2. **Generate** — retrieve relevant context and generate output:
   ```bash
   foundry generate --topic "spindle wiring" --output docs/spindle-wiring.md
   ```

3. **Features** — approve feature specs as a gate before generation:
   ```bash
   foundry features list
   foundry features approve F01-DB
   ```

---

## Architecture

- **RAG, not extraction** — chunks + embeddings, no claim normalization pipeline
- **Per-project SQLite** — one `.db` file per project, no server, fully portable
- **sqlite-vec** — vector search as a SQLite virtual table extension
- **Human-approved features** — generation requires approved feature specs
- **Configurable output** — format and structure defined by project profile

See [CLAUDE.md](CLAUDE.md) for full architecture decisions and governance.

---

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/yourname/foundry
cd foundry
uv venv && source .venv/bin/activate
uv sync
foundry --help
```

---

## Development

```bash
pytest                              # run tests
ruff check src/                     # lint
mypy src/foundry/                   # type check
python .forge/governor.py status    # sprint status
```

Branch strategy: `wi/* → feat/* → develop → main`
See [tracking/STATUS.md](tracking/STATUS.md) for current sprint.
See [tracking/decisions/DECISIONS.md](tracking/decisions/DECISIONS.md) for architecture decisions.
