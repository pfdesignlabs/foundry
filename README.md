# Foundry

**Turn your source material into polished documents — powered by RAG and LLMs.**

Foundry is a project-agnostic command-line tool that ingests source material
(PDFs, Markdown, websites, Git repos, audio recordings), stores everything as
searchable chunks in a local SQLite database, and generates structured Markdown
documents via Retrieval-Augmented Generation (RAG) and your LLM of choice.

**Two roles, one tool:**
- **Operator** — you, building the knowledge base and generating content
- **Recipient** — your client or team, receiving a polished delivery document

**Two commands, one distinction:**
- `foundry generate` — draft and review individual features (operator tool)
- `foundry build` — assemble the official delivery document (client-ready)

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- An API key for your LLM provider (default: OpenAI)

```bash
export OPENAI_API_KEY=sk-...
```

---

## Installation

### Via pip / uv (recommended)

```bash
uv pip install foundry-cli
# or
pip install foundry-cli
```

### Development install

```bash
git clone https://github.com/pfdesignlabs/foundry.git
cd foundry
uv venv && source .venv/bin/activate
uv sync
```

Verify:

```bash
foundry --version
```

---

## Quick Start (5 minutes)

```bash
# 1. Initialize a new project
foundry init ./my-project

# 2. Ingest source material
foundry ingest --source docs/spec.pdf
foundry ingest --source https://example.com/datasheet

# 3. Write a feature spec (features/my-feature.md) and approve it
foundry features approve my-feature

# 4. Generate a draft for review
foundry generate --topic "wiring and connections" --output drafts/wiring.md

# 5. Assemble the delivery document
foundry build
```

---

## Workflow

Foundry follows a **knowledge-first** approach: build the knowledge base first,
then write feature specs informed by what you know.

### Step 1 — Initialize

```bash
foundry init ./dmx-controller
```

The interactive wizard asks about your project (client needs, capabilities,
knowledge gaps, etc.) and scaffolds:

```
dmx-controller/
  .foundry.db              ← knowledge base (SQLite + sqlite-vec)
  foundry.yaml             ← project + delivery configuration
  features/                ← feature spec files (human-approved gate)
  tracking/
    project-context.md     ← project charter (loaded as system prompt brief)
    sources.md             ← pre-populated knowledge gap checklist
    work-items.md          ← capability candidates
    build-plan.md          ← delivery layout template
```

Optional git scaffold (answer `y` to "Initialize git repository?"):

```
  .forge/
    slice.yaml             ← sprint + work item tracker
    contracts/             ← branch naming, commit discipline rules
    hooks/pre-bash.sh      ← governance hook (fail-open)
  .claude/settings.json    ← Claude Code hook configuration
  CLAUDE.md                ← project governance guide
```

### Step 2 — Build the knowledge base

Ingest any combination of source types:

```bash
foundry ingest --source docs/client-brief.pdf
foundry ingest --source https://espressif.com/esp32-datasheet
foundry ingest --source meeting-recording.mp3
foundry ingest --source https://github.com/user/reference-firmware
foundry ingest --source docs/                  # directory (all supported files)
foundry ingest --source docs/ --recursive      # recurse into subdirectories
```

**Supported source types:**

| Type | Extensions / Patterns |
|------|-----------------------|
| Markdown | `.md`, `.markdown` |
| PDF | `.pdf` |
| EPUB | `.epub` |
| Plain text | `.txt`, `.rst`, `.log` |
| JSON | `.json`, `.jsonl` |
| Git repo | Local path with `.git/` or remote URL |
| Web page | `http://` or `https://` URLs |
| Audio | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.mp4`, `.webm` |

Each source is chunked, embedded, and summarized. The knowledge base grows
incrementally — ingest new sources at any time.

```bash
foundry status    # see what's in the knowledge base
```

### Step 3 — Write and approve feature specs

Create Markdown files in `features/` describing what each section of your
delivery document should cover:

```markdown
# Wiring Guide

## Purpose
Describe the complete wiring diagram for the DMX controller,
covering all connector pinouts and cable specifications.

## Scope
- 3-pin XLR connector pinout
- RS-485 termination resistor placement
- Power supply wiring (5V, 12V rails)
- ESP32 GPIO assignments

## Approved
2026-02-24
```

The `## Approved` heading is the gate. Generation is blocked until you add it:

```bash
foundry features approve wiring-guide     # appends ## Approved + date
foundry features list                     # show all specs + approval status
```

### Step 4 — Generate drafts for review

Use `foundry generate` to produce per-feature drafts that you can review and
iterate on. This is an **operator tool** — not for sending to clients directly.

```bash
foundry generate \
  --topic "DMX controller wiring and connections" \
  --feature wiring-guide \
  --output drafts/wiring-draft.md

# With multiple approved specs, --feature selects which one to use.
# With only one approved spec, it is selected automatically.
```

The pipeline per generate call:

1. **Retrieve** — HyDE query expansion + BM25 + dense vector search, fused via RRF
2. **Score** — LLM relevance scoring (0-10) per chunk; below-threshold chunks filtered
3. **Conflict check** — LLM detects factual contradictions between chunks
4. **Assemble prompt** — project brief + feature spec + source summaries + chunks
5. **Generate** — LLM produces Markdown with footnote source attribution

```bash
foundry generate --dry-run    # preview retrieval + prompt without LLM call
```

### Step 5 — Assemble the delivery document

Configure sections in `foundry.yaml`:

```yaml
delivery:
  output: "dmx-controller-build-guide.md"
  sections:
    # Generated section — RAG + LLM
    - type: generated
      feature: wiring-guide
      topic: "DMX controller wiring and connections"
      heading: "Wiring Guide"

    # File section — checks if a deliverable exists on disk
    - type: file
      path: "output/dmx-controller.kicad_pcb"
      heading: "PCB Design Files"
      description: "KiCad PCB layout, schematic, and Gerber files."

    # Physical section — reads WI status from .forge/slice.yaml
    - type: physical
      heading: "Hardware Prototype"
      description: "Assembled and tested DMX controller prototype."
      tracking_wi: WI_0004
```

Then build:

```bash
foundry build                          # assembles delivery.md
foundry build --output report.md       # custom output path
foundry build --pdf                    # also export PDF (requires Pandoc)
foundry build --dry-run                # preview section plan, no LLM
foundry build --yes                    # skip confirmation prompts (CI/scripts)
```

**Section types in the delivery document:**

- `generated` — runs full RAG + LLM pipeline per approved feature spec
- `file` — checks whether a file exists on disk; shows path + size if present
- `physical` — reads WI status from `.forge/slice.yaml`; shows ✓ Delivered /
  ⏳ In Progress / ✗ Pending

### Source lifecycle

```bash
# Remove a source (with confirmation)
foundry remove --source docs/old-spec.pdf

# After removal: re-ingest an updated version
foundry ingest --source docs/new-spec.pdf
```

Removing a source deletes all its chunks and embeddings from the database.

---

## CLI Reference

### `foundry init [PROJECT_DIR]`

Initialize a new Foundry project with an interactive wizard.

```bash
foundry init                  # current directory
foundry init ./my-project     # specific directory
```

The wizard asks:
- Project type (client project or internal)
- Project name
- Client needs, success criteria, operator goals, environment
- Required capabilities (→ work item candidates)
- Knowledge gaps (→ pre-populated sources checklist)
- Initialize git repository? (→ optional governance scaffold)

---

### `foundry ingest`

Ingest one or more sources into the knowledge base.

```bash
foundry ingest --source docs/spec.pdf
foundry ingest --source docs/ --recursive
foundry ingest --source https://example.com/page --dry-run
```

| Option | Description |
|--------|-------------|
| `--source`, `-s` | Source path or URL (repeatable) |
| `--db` | Path to `.foundry.db` (default: `.foundry.db`) |
| `--dry-run` | Show what would be ingested without writing |
| `--yes`, `-y` | Skip cost confirmation prompts |
| `--recursive` | Recurse into subdirectories (max 10 levels) |
| `--exclude` | Glob pattern to exclude (repeatable) |

---

### `foundry generate`

**Operator review tool.** Generate a per-feature draft document via RAG + LLM.
Use this to draft and review content before running `foundry build`.
NOT for sending to clients — use `foundry build` for the official delivery document.

```bash
foundry generate --topic "wiring" --output drafts/wiring.md
foundry generate --topic "firmware" --feature firmware-arch --output drafts/fw.md
```

| Option | Description |
|--------|-------------|
| `--topic`, `-t` | Topic or question for retrieval (required) |
| `--output`, `-o` | Output file path for the draft (required) |
| `--feature`, `-f` | Feature spec name (auto-selected if only one approved) |
| `--db` | Path to `.foundry.db` |
| `--dry-run` | Show retrieved chunks and prompt without calling the LLM |
| `--yes`, `-y` | Skip overwrite and cost confirmation prompts |

---

### `foundry build`

**Client delivery tool.** Assembles the official delivery document from all
approved features, as configured in `foundry.yaml`.

```bash
foundry build
foundry build --output report.md --pdf --yes
foundry build --dry-run
```

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Override `delivery.output` from foundry.yaml |
| `--db` | Path to `.foundry.db` |
| `--dry-run` | Preview the delivery plan without LLM generation |
| `--yes`, `-y` | Skip overwrite confirmation prompts |
| `--pdf` | Also export a PDF via Pandoc (skipped gracefully if not found) |

---

### `foundry features`

Manage feature specs in the `features/` directory.

```bash
foundry features list              # show all specs + approval status
foundry features approve my-spec   # append ## Approved + date to spec file
```

---

### `foundry status`

Show a project overview: knowledge base contents, feature approval status,
and delivery readiness.

```bash
foundry status
foundry status --db ./path/to/.foundry.db
```

---

### `foundry remove`

Remove a source and all its data (chunks, embeddings, summary) from the
knowledge base.

```bash
foundry remove --source docs/old-spec.pdf
foundry remove --source https://old-url.com --yes
```

| Option | Description |
|--------|-------------|
| `--source`, `-s` | Source path or URL to remove (required) |
| `--db` | Path to `.foundry.db` |
| `--yes`, `-y` | Skip confirmation prompt |

---

### `foundry --version` / `foundry version`

```bash
foundry --version
foundry version
```

---

## Configuration Reference

Foundry uses three configuration layers (applied in order):

```
~/.foundry/config.yaml     ← global defaults (model choices)
foundry.yaml               ← per-project config
environment variables      ← OPENAI_API_KEY, etc.
CLI flags                  ← highest priority
```

**Priority:** CLI flags > env vars > per-project > global > built-in defaults

### `foundry.yaml` — full reference

```yaml
project:
  name: "My Project"
  brief: "tracking/project-context.md"   # local path only — loaded as system prompt
  brief_max_tokens: 3000                  # warn if brief exceeds this limit

embedding:
  model: "openai/text-embedding-3-small"  # LiteLLM provider/model format

generation:
  model: "openai/gpt-4o"
  max_source_summaries: 10                # max summaries included in prompt

retrieval:
  top_k: 10                               # candidate chunks from each retrieval channel
  rrf_k: 60                               # Reciprocal Rank Fusion constant
  relevance_threshold: 4                  # chunks below this score (0-10) are discarded
  token_budget: 8192                      # max tokens for assembled context

chunkers:
  default:
    chunk_size: 512                       # approximate chunk size in tokens
    overlap: 0.10                         # fraction of overlap between chunks
  pdf:
    chunk_size: 400
    overlap: 0.20
  json:
    chunk_size: 300
    overlap: 0.0

delivery:
  output: "delivery.md"
  sections:
    - type: generated          # RAG + LLM
      feature: my-feature
      topic: "topic for retrieval"
      heading: "Section Heading"
      show_attributions: true  # footnote attribution (default: true)

    - type: file               # disk presence check
      path: "output/design.pdf"
      heading: "Design Files"
      description: "PCB design and Gerber files."

    - type: physical           # WI status from .forge/slice.yaml
      heading: "Hardware Prototype"
      description: "Assembled and tested prototype."
      tracking_wi: WI_0004

plan:
  model: "openai/gpt-4o"
  max_summaries: 20
```

### `~/.foundry/config.yaml` — global defaults

Only model selection — never API keys:

```yaml
embedding:
  model: openai/text-embedding-3-small

generation:
  model: openai/gpt-4o
```

### Supported LLM providers

Any provider supported by [LiteLLM](https://docs.litellm.ai/docs/providers)
in `provider/model` format:

```yaml
generation:
  model: "openai/gpt-4o"
  # model: "anthropic/claude-3-5-sonnet-20241022"
  # model: "openai/gpt-4o-mini"
  # model: "ollama/llama3"       # local, no API key required
```

---

## Architecture Overview

For operators who want to understand what's happening under the hood.

### Storage

Each project has its own `.foundry.db` — a standard SQLite database with the
[sqlite-vec](https://github.com/asg017/sqlite-vec) extension for vector search.
No external services, no shared state between projects.

**Tables:**
- `sources` — ingested source records (path, hash, model, timestamp)
- `chunks` — text chunks with FTS5 index for BM25 search
- `vec_<model-slug>` — one vector table per embedding model
- `source_summaries` — LLM-generated per-source summaries

### Ingestion pipeline

```
Source file/URL
  → Chunker (type-specific: PDF, MD, EPUB, JSON, txt, git, web, audio)
  → Context prefix (LLM: adds document context to each chunk)
  → Embedding (LiteLLM → sqlite-vec)
  → Document summary (LLM: stored in source_summaries)
  → Stored in .foundry.db
```

### RAG pipeline (per generate/build call)

```
Query
  → HyDE: LLM generates a short hypothetical answer → embed that
  → BM25 via SQLite FTS5 (raw query)

Dense results + BM25 results
  → Reciprocal Rank Fusion (k=60)
  → Top-K chunks
  → Relevance scoring (LLM, 0-10, threshold 4)
  → Conflict detection (LLM, warns if contradictions found)
  → Token budget enforcement

System prompt:
  [Project Context]     ← project.brief file
  [Feature Spec]        ← approved feature spec content
  [Source Summaries]    ← up to max_source_summaries summaries
  <context>
  [Retrieved Chunks]    ← assembled context
  </context>

LLM generation → Markdown with footnote source attribution
```

### Feature gate

No generation happens without an approved feature spec. The gate is a human
decision: opening `features/<name>.md` and adding `## Approved` (exact heading,
case-sensitive). `foundry features approve` does this for you.

---

## License

MIT — see `LICENSE` for details.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, architecture
details, test pyramid, and contribution guidelines.
