# F08-DOCS: Documentatie & Release Readiness

## Doel
Volledige gebruikers- en ontwikkelaarsdocumentatie schrijven vóór de eerste
release naar `main`. Dekt: uitgebreide README, developer guide, CLI help tekst,
en docstrings audit. Na F08 is Foundry klaar voor een officiële v0.1.0 release.

## Work Items
- WI_0045: `README.md` — uitgebreide gebruikersdocumentatie
  - Structuur (best practices):
    1. **Titel + tagline** — één zin wat Foundry doet
    2. **Badges** — build status (CI), Python version, license
    3. **Wat is Foundry?** — 3-5 regels, de twee begunstigden (operator + klant),
       generate vs build onderscheid
    4. **Vereisten** — Python 3.11+, uv, API key (OPENAI_API_KEY)
    5. **Installatie** — `pip install foundry-cli` of `uv pip install foundry-cli`
       + dev install via `uv sync`
    6. **Quick start (5 minuten)** — minimale workflow:
       `foundry init` → `foundry ingest` → `foundry features approve` →
       `foundry generate` → `foundry build`
    7. **Uitgebreide workflow** — klantproject walkthrough met echte voorbeelden:
       - Project init (wizard klantproject / intern project)
       - Kennisbank opbouwen (PDF, URL, audio, git repo)
       - Feature specs schrijven en goedkeuren
       - Per feature reviewen (generate)
       - Klantlevering assembleren (build)
       - Bronnen verwijderen / bijwerken
    8. **CLI referentie** — alle commands met beschrijving + voorbeelden:
       - `foundry init`
       - `foundry ingest`
       - `foundry generate`
       - `foundry features list` / `approve`
       - `foundry status`
       - `foundry remove`
       - `foundry build`
       - `foundry --version`
       - Globale flag: `--project PATH`
    9. **Configuratie referentie** — foundry.yaml + `~/.foundry/config.yaml`:
       - `project:` sectie (name, brief, brief_max_tokens)
       - `embedding:` sectie (model)
       - `generation:` sectie (model, max_source_summaries)
       - `retrieval:` sectie (top_k, rrf_k, relevance_threshold, token_budget)
       - `chunkers:` sectie (per type, chunk_size, overlap)
       - `delivery:` sectie (output, sections met type generated/file/physical)
       - `plan:` sectie (model, max_summaries)
       Config prioriteit tabel: CLI > env vars > per-project > globaal > defaults
   10. **Architectuuroverzicht** (kort, voor nieuwsgierige operators):
       - Per-project SQLite + sqlite-vec
       - Chunker pipeline (types)
       - RAG pipeline (HyDE, BM25, dense, RRF, scoring)
       - Feature gate (## Approved)
   11. **Licentie** — MIT of intern (afhankelijk van keuze)
  - Taal: Engels (internationale leesbaarheid)
  - Codeblokken voor alle commando's + config voorbeelden
  - Geen internal-only details (geen sprint nummers, geen .forge/ referenties)

- WI_0046: `CONTRIBUTING.md` — developer guide
  - Secties:
    1. **Development setup** — `uv venv && source .venv/bin/activate && uv sync`,
       git hooks setup (`git config core.hooksPath .forge/hooks/`),
       API keys voor e2e tests
    2. **Architectuuroverzicht (uitgebreid)** — alle modules beschreven:
       - `src/foundry/db/` — schema, migrations, repository pattern, sqlite-vec
       - `src/foundry/ingest/` — chunker base class + alle chunker types
       - `src/foundry/rag/` — retriever (hybrid BM25+dense, RRF), context assembler
       - `src/foundry/generate/` — LLM client, prompt templates, output writer
       - `src/foundry/gates/` — feature spec parser, approval check
       - `src/foundry/cli/` — typer entry points per command
       - `src/foundry/governance/` — bash-intercept, audit log (F06)
       - `src/foundry/plan/` — foundry plan planner (F07)
    3. **Test piramide** — unit (no I/O, mock LLM), integration (real SQLite :memory:),
       e2e (`@pytest.mark.e2e`, vereist API keys, skipped by default)
       Commando's: `pytest`, `pytest -m e2e`, coverage target
    4. **Branch en commit conventies** — branch strategie (wi/* → feat/* → develop → main),
       commit prefix ([WI_XXXX]), PR template
    5. **Hard rules samenvatting** — yaml.safe_load, shell=False, no API keys in config,
       path traversal preventie
    6. **Hoe voeg je een nieuwe chunker toe?** — stap-voor-stap met code-voorbeeld
    7. **Hoe voeg je een nieuwe CLI command toe?** — stap-voor-stap (typer + tests)
  - Taal: Engels

- WI_0047: Docstrings audit — alle publieke functies en klassen in `src/foundry/`
  - Elk publiek module, klasse, en functie heeft een docstring
  - Docstring stijl: Google style (Args:, Returns:, Raises:)
  - Scope: alleen public API (`_` prefix = private, geen docstring vereist)
  - Prioriteit: `db/`, `ingest/`, `rag/`, `generate/`, `gates/` (core modules)
  - CLI modules (typer commands): docstrings worden ook gebruikt als `--help` tekst
    → zie WI_0048

- WI_0048: CLI `--help` tekst audit
  - Alle typer commands en opties hebben complete, beschrijvende help tekst
  - Elke optie heeft: wat het doet + voorbeeld als dat niet triviaal is
  - `foundry --help` toont duidelijk onderscheid: generate (review) vs build (delivery)
  - Test: `foundry <command> --help` exit 0 + sleutelwoorden aanwezig
  - Gebruik `typer.Option(help="...")` en `typer.Argument(help="...")`
  - Geen truncated of placeholder help tekst meer

## Acceptatiecriteria
- [ ] `README.md` aanwezig in repo root, minimaal 400 regels
- [ ] README bevat: installatie, quick start, volledige CLI referentie, config referentie
- [ ] README bevat: generate vs build onderscheid expliciet uitgelegd
- [ ] README bevat geen intern projectjargon (sprint nummers, WI-IDs, .forge/ details)
- [ ] `CONTRIBUTING.md` aanwezig in repo root
- [ ] CONTRIBUTING bevat: dev setup, architectuur, testpyramide, branch strategie, hard rules
- [ ] Alle publieke functies en klassen in `src/foundry/` hebben docstrings
- [ ] `foundry --help` toont duidelijke tagline + command overzicht
- [ ] `foundry <command> --help` voor elk command: beschrijvend, geen placeholder tekst
- [ ] `foundry generate --help` vermeldt dat het een review tool is (niet voor klant)
- [ ] `foundry build --help` vermeldt dat het de klantlevering assembleert
- [ ] `pytest` (zonder e2e) blijft groen na alle doc/help wijzigingen

## Afhankelijkheden
- F05-CLI (alle CLI commands aanwezig — docstrings pas volledig schrijven als commands compleet zijn)

## Timing
Dit feature wordt uitgevoerd NA F05 en vóór de eerste `release/v0.1.0` branch.
F06 (Project Governance) en F07 (Planning) zijn v0.2.0+ features.
