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
```

Branch strategy: `wi/* → feat/* → develop → main`
See [tracking/STATUS.md](tracking/STATUS.md) for current sprint.
See [tracking/decisions/DECISIONS.md](tracking/decisions/DECISIONS.md) for architecture decisions.

---

## Governance

Foundry uses a runtime governance system via `.forge/governor.py`. All git operations inside Claude Code are automatically intercepted and validated.

### Automatic enforcement

| Action | Result |
|--------|--------|
| `git checkout -b random-name` | ❌ Hard-block — must match `wi/WI_XXXX-*`, `feat/*`, `release/vX.Y.Z`, `hotfix/*` |
| `git commit -m "fix stuff"` | ⚠️ Warn — message must be `[WI_XXXX] type(scope): description` |
| `git commit` with staged `.py` files | Runs `pytest` automatically — warns if tests fail, never blocks |
| `git push origin develop` | ❌ Hard-block — no direct push to protected branches |
| `git merge wi/...` on `develop` | ❌ Hard-block — `develop` only accepts `feat/*` or `release/*` |
| `git merge feat/...` on `develop` | ✅ Allow |
| `git merge feat/...` on `main` | ❌ Hard-block — `main` only accepts `release/*` |
| Session start | Prints sprint status banner + injects context into Claude |
| Session end | Prints session summary, regenerates `tracking/STATUS.md` |

### Governor commands

```bash
# Sprint status + regenerate tracking/STATUS.md
python .forge/governor.py status

# Last 20 audit events with verdict icons
python .forge/governor.py audit-summary

# Close sprint and archive STATUS.md to tracking/sprints/
python .forge/governor.py sprint-close
```

### Commit message format

```
[WI_0042] feat(cli): add init command
[WI_0042] fix(db): handle null embeddings
[FEATURE_TRACKING] chore(specs): update F03
[DEV_GOVERNANCE] refactor(governor): clean up audit logic
```

Pattern: `[WI_XXXX|FEATURE_TRACKING|DEV_GOVERNANCE] type(scope): description`

### Branch naming

```
wi/WI_0042-slug          # work item branch
feat/phase-1             # feature branch
release/v1.0.0           # release branch
hotfix/critical-fix      # hotfix branch
```

### Claude Code skills

Type these in a Claude Code session:

- `/forge-status` — interactive sprint dashboard (all WIs, criteria, warnings)
- `/forge-plan` — update a WI status, outcome and evidence interactively
