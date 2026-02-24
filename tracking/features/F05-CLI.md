# F05-CLI: CLI Polish & UX

## Doel
Foundry's CLI interface afwerken: `--project` global flag, duidelijke help tekst,
rijke error messages, progress indicators, en een goede developer experience.
`--dry-run` voor ingest zit in F02; `--dry-run` voor generate zit in F03.

Foundry bedient twee begunstigden (D0014):
- **Operator**: ingest, feature specs schrijven, projecttaken tracken, audit trail
- **Klant**: ontvangt geconsolideerd leveringsdocument via `foundry build`

`foundry generate` = **operator review tool** (per feature, iteratief, intern).
`foundry build` = **klantlevering** (assembleert alle goedgekeurde features in één document).

Feature specs beschrijven projecttaken (PCB layout, firmware, assembly-procedure etc.).
De `delivery:` sectie in `foundry.yaml` bepaalt welke features in de klantlevering gaan.

## Global flag
`--project PATH` is beschikbaar op alle commands:
```bash
foundry --project /pad/naar/project ingest --source datasheet.pdf
foundry --project /pad/naar/project generate --topic "wiring"
```
Zonder `--project`: Foundry zoekt `.foundry.db` in de huidige directory.
Niet gevonden → hard fail met instructie `foundry init` te draaien.

## Work Items
- WI_0034: `foundry init` — interactieve wizard + project scaffold
  - **Eerste vraag: projecttype**
    ```
    Klantproject of intern project? [klant/intern]:
    ```
    - `klant` → volledige wizard (8 vragen):
      1. Project naam
      2. Klantbehoeftes / RFQ samenvatting (vrije tekst)
      3. Succesfactoren (klant perspectief)
      4. Operator doelen
      5. Omgeving / context (EMI, tools, platform)
      6. Vereiste capabilities → pre-populeert `tracking/work-items.md`
      7. Bekende kennistekorten → pre-populeert `tracking/sources.md`
      8. Git repository initialiseren? [Y/n]
    - `intern` → beperkte wizard (3 vragen):
      1. Project naam
      2. Korte omschrijving
      3. Git repository initialiseren? [Y/n]
  - **Scaffold aangemaakt** in de opgegeven directory (of huidige directory):
    - `.foundry.db` — lege database met schema
    - `foundry.yaml` — met wizard-keuzes (incl. `project:` sectie + lege `delivery:` sectie)
    - `features/` — lege directory (features komen NA ingest)
    - `tracking/` — interne projecttracking (niet voor klant, niet in delivery)
      - `tracking/project-context.md` — project charter (= project.brief, permanent in system prompt)
        Pre-populated met wizard-antwoorden. Bevat: klantbehoeftes, succesfactoren,
        operator doelen, omgeving, capabilities, kennistekorten.
        **Let op:** wordt verbatim in de system prompt geladen — schrijf geen instructies in dit bestand.
      - `tracking/sources.md` — te ingesteren bronnen per kennistekort (pre-populated)
        Tracking is human-only: Foundry parseert dit bestand niet.
      - `tracking/work-items.md` — capability-kandidaten als WI-kandidaten (pre-populated)
      - `tracking/build-plan.md` — delivery layout template (companion bij `delivery:` config)
  - **`.gitignore` update:** voegt `.foundry.db` en `foundry.yaml` toe als `.gitignore`
    aanwezig is — database bevat gevoelige ingested content
  - **Globale config** aangemaakt als nog niet aanwezig: `~/.foundry/config.yaml`
    - Aangemaakt met `mode=0o600` (alleen owner leesbaar)
    - Bevat model defaults, **NOOIT API keys** (API keys altijd via env vars)
  - **Als git=Y:** volledig git scaffold aangemaakt:
    - `git init` + eerste commit op `develop` branch (main pas bij eerste release)
    - `.forge/slice.yaml` — lege sprint, klaar om te vullen (zie F06)
    - `.forge/contracts/` — merge-strategy.yaml, commit-discipline.yaml, workitem-discipline.yaml
    - `.forge/hooks/pre-bash.sh` — roept `foundry governance bash-intercept` aan (fail-open)
    - `.claude/settings.json` — PreToolUse + SessionStart hooks
    - `CLAUDE.md` — project governance doc (projectnaam + doel ingevuld door wizard)
    - `.gitignore` uitgebreid: `.foundry.db`, `foundry.yaml`, `.forge/audit.jsonl`
- WI_0035: Progress indicators via rich
  - Ingest: progress bar over chunks (Chunk N/N), aparte teller voor LLM calls
  - Generate: stap-indicator (Retrieving → Scoring → Checking conflicts → Assembling → Generating)
  - Gebruik: `rich.progress.Progress` + `rich.panel.Panel` per sectie
- WI_0036: Rijke error messages met actionable feedback
  - Elke foutmelding: wat ging er mis + exacte actie voor de gebruiker
  - Voorbeelden:
    - "No API key for 'openai'. Set: export OPENAI_API_KEY=sk-..."
    - "No approved feature specs. Run: foundry features approve <name>"
    - "Embedding model mismatch: database uses 'openai/text-embedding-3-small',
       config has 'openai/text-embedding-3-large'. Re-ingest or update config."
    - "No .foundry.db found. Run: foundry init"
    - "URL resolves to private address (SSRF protection). Use a public URL."
    - "Audio file exceeds 25MB limit. Split the file and ingest separately."
- WI_0037: `foundry --version` en `foundry status`
  - `foundry --version`: versie uit pyproject.toml
  - `foundry status`: project overzicht (rich formatting, `rich.panel.Panel` per sectie)
    ```
    Project: DMX Controller
    Database: ./dmx-controller/.foundry.db (12.4 MB)

    Knowledge Base:
      Sources: 8  |  Chunks: 1.247  |  Vec tables: 1 (openai/text-embedding-3-small, 1536 dim)
      Last ingest: 2026-02-24 14:32

    Features:
      ✓ wiring-guide (approved 2026-02-23)
      ✗ firmware-arch (not approved)

    Delivery readiness:
      wiring-guide   (generated) → ✓ Generated 2026-02-23
      firmware-arch  (generated) → ✗ Not generated yet
      pcb-files      (file)      → ✓ Present (2.3 MB)
      bom.xlsx       (file)      → ✗ File missing
      prototype      (physical)  → ⏳ WI_0004 in_progress

    [als .forge/ aanwezig]:
    Sprint: SP_001 | Phase: EVT-1 | 4/9 WIs done
    ```
    - `type: physical` readiness vereist `.forge/slice.yaml` — als afwezig: "(no git scaffold)"
- WI_0038: Config file support — globaal + per project
  - Globaal: `~/.foundry/config.yaml` (model defaults — **geen API keys**)
  - Per project: `foundry.yaml` naast `.foundry.db` (chunker settings, retrieval config)
  - Per project overschrijft globaal. Model format: `provider/model` (D0010)
  - Config prioriteit (hoog → laag):
    1. CLI flags
    2. Environment variables (`FOUNDRY_GENERATION_MODEL`, etc.)
    3. Per-project `foundry.yaml`
    4. Globaal `~/.foundry/config.yaml`
    5. Hardcoded defaults
  - `yaml.safe_load()` voor alle config reads — nooit `yaml.load()`
  - `project.brief` accepteert alleen lokale paden — geen URLs (SSRF preventie)
- WI_0039: `foundry remove` — source lifecycle management
  - `foundry remove --source datasheet-v1.pdf`
  - Verwijdert: alle chunks, embeddings (alle vec tables), source_summaries voor die bron
  - Toont wat verwijderd wordt + vraagt bevestiging:
    ```
    Remove source: datasheet-v1.pdf
      Chunks: 247  |  Vec entries: 247  |  Summary: yes
    Confirm removal? [y/N]:
    ```
  - `--yes` slaat bevestiging over
  - Bron niet gevonden → melding (geen fout)
  - **Na verwijdering:** informationele warning:
    "⚠ Existing draft outputs may reference this source. Consider regenerating affected features."
- WI_0040: `foundry build` — geconsolideerd klantleveringsdocument samenstellen (D0014)
  - Leest `delivery:` sectie uit `foundry.yaml`
  - Ondersteunt drie section types:
    - **`type: generated`** (default als `type` weggelaten):
      - Roept intern `foundry generate` aan voor die feature
      - Vereist: goedgekeurde feature spec
    - **`type: file`** — bestand deliverable (CAD, Gerbers, BOM, etc.):
      - Controleert of bestand op `path:` bestaat
      - Bestand aanwezig → listing in delivery doc met bestandsgrootte
      - Bestand niet gevonden → ⚠ warning in delivery doc (niet hard fail)
      - WI-ID nooit zichtbaar voor klant — alleen `heading:` + `description:` + status
    - **`type: physical`** — fysieke deliverable (prototype, levering):
      - Leest WI status uit `.forge/slice.yaml` via `tracking_wi:`
      - `.forge/slice.yaml` niet aanwezig → warning in delivery doc: "(physical tracking not available)"
      - Status rendering: ✓ Delivered / ⏳ In Progress / ✗ Pending
      - WI-ID (bijv. WI_0004) NIET zichtbaar in delivery doc — alleen `heading:` + `description:` + status
  - Validatie vóór generatie: alle `type: generated` feature specs moeten goedgekeurd zijn
  - Assembleert outputs in gedefinieerde volgorde, met H1 header per sectie (via `heading:`)
  - **`show_attributions`** per sectie (optioneel, default true):
    - `true` → footnote bronattributie opgenomen in output
    - `false` → geen bronverwijzingen (voor klanten die dit niet willen)
  - Resultaat: één `.md` document als klant-deliverable
  - `--output PATH` overschrijft `delivery.output` uit config
  - `--pdf`: PDF conversie via Pandoc (`shutil.which("pandoc")`) — fail-open als niet aanwezig:
    "Pandoc not found. Install pandoc for PDF export. Markdown output saved."
  - `--dry-run`: toont sectie-volgorde + type + feature specs / bestanden / WI-status zonder generatie
  - `--yes`: slaat output overwrite bevestiging over
  - Output overwrite bescherming: vraagt bevestiging als output bestand al bestaat

## Configuratie (foundry.yaml)
```yaml
project:
  name: "DMX Controller"
  brief: "tracking/project-context.md"  # lokaal pad — GEEN URLs
  brief_max_tokens: 3000                # warn + truncate als te lang

delivery:
  output: "build-guide.md"             # standaard output pad voor foundry build

  sections:
    # Gegenereerde tekst (RAG + LLM)
    - type: generated                  # optioneel — generated is default
      feature: wiring-guide            # naam van goedgekeurde feature spec (zonder .md)
      topic: "DMX controller wiring and electrical connections"
      heading: "Wiring Guide"          # H1 in samengesteld document
      show_attributions: true          # footnote bronattributie (default: true)

    - type: generated
      feature: firmware-architecture
      topic: "firmware structure and component interactions"
      heading: "Firmware Architecture"

    # Bestand deliverable (niet gegenereerd — Foundry lijst het op)
    - type: file
      path: "output/dmx-controller.kicad_pcb"
      heading: "PCB Design Files"
      description: "KiCad PCB layout en schematic files inclusief Gerbers"

    - type: file
      path: "output/bom.xlsx"
      heading: "Bill of Materials"
      description: "Complete BOM met leverancier, referenties en prijzen"

    # Fysieke deliverable (status gesynced van WI)
    - type: physical
      heading: "Hardware Prototype"
      description: "Geassembleerd en getest DMX controller prototype"
      tracking_wi: WI_0004             # WI-ID nooit zichtbaar in delivery doc
```

Sommige secties kunnen intern gegenereerde content bevatten (bijv. beslissingenlog) die
ook in de klantlevering terechtkomen — dit wordt per project bepaald via `delivery.sections`.
`tracking/sources.md` is bewust niet machine-parsed — tracking is human-only.

## Afhankelijkheden
- F04-FEATURE-GATES (volledige pipeline aanwezig)

## Acceptatiecriteria
- [ ] `--project PATH` global flag beschikbaar op alle commands
- [ ] Zonder `--project`: `.foundry.db` gezocht in huidige directory; niet gevonden → hard fail
- [ ] `foundry --help` toont duidelijk onderscheid: generate (review) vs build (delivery)
- [ ] **Wizard eerste vraag:** "Klantproject of intern project?" → klant=8 vragen, intern=3 vragen
- [ ] `foundry init` maakt `tracking/project-context.md` aan (pre-populated met wizard-antwoorden)
- [ ] `tracking/sources.md` pre-populated met kennistekorten (klantproject wizard)
- [ ] `tracking/work-items.md` pre-populated met capabilities (klantproject wizard)
- [ ] `foundry init` voegt `.foundry.db` toe aan `.gitignore` als die aanwezig is
- [ ] `~/.foundry/config.yaml` aangemaakt met `mode=0o600` (owner-only)
- [ ] Globale config weigert API keys — bevat alleen model defaults
- [ ] `project.brief` accepteert alleen lokale paden — URL als waarde → hard fail bij config load
- [ ] Als git=Y: `git init` + `develop` branch + `.forge/` scaffold + `CLAUDE.md` + `.claude/settings.json`
- [ ] Als git=Y: `.gitignore` uitgebreid met `.foundry.db`, `foundry.yaml`, `.forge/audit.jsonl`
- [ ] Progress indicators actief bij ingest (chunks) en generate (stappen incl. conflict check)
- [ ] Foutmeldingen bevatten altijd: wat + actie
- [ ] `foundry status` toont bronnen, chunks, vec tables, goedgekeurde features, laatste ingest
- [ ] `foundry status` toont delivery readiness per sectie (generated/file/physical)
- [ ] `foundry status` toont fase-voortgang als `.forge/slice.yaml` aanwezig
- [ ] `foundry remove --source <pad>` verwijdert bron volledig met bevestiging
- [ ] `foundry remove` toont warning dat draft outputs verouderd kunnen zijn
- [ ] Config prioriteit: CLI > env vars > per-project > globaal > defaults
- [ ] `yaml.safe_load()` voor alle config reads — nooit `yaml.load()`
- [ ] `foundry init` voegt `project:` sectie toe aan `foundry.yaml` (brief + brief_max_tokens)
- [ ] `foundry init` voegt lege `delivery:` sectie toe aan `foundry.yaml`
- [ ] **`foundry build`:** `type: generated` assembleert via intern generate per feature
- [ ] **`foundry build`:** `type: file` controleert of bestand bestaat; niet gevonden → ⚠ warning in doc
- [ ] **`foundry build`:** `type: physical` leest WI status uit `.forge/slice.yaml`
- [ ] **`foundry build`:** `type: physical` zonder `.forge/slice.yaml` → graceful warning in delivery doc
- [ ] **`foundry build`:** WI-ID nooit zichtbaar in delivery doc (alleen heading + description + status-icoon)
- [ ] **`foundry build`:** `show_attributions: false` onderdrukt footnote bronattributie per sectie
- [ ] `foundry build` valideert dat alle `type: generated` specs goedgekeurd zijn vóór generatie
- [ ] `foundry build --dry-run` toont sectie-volgorde + type + status zonder generatie
- [ ] `foundry build --output PATH` overschrijft `delivery.output` uit config
- [ ] `foundry build --pdf` converteert via Pandoc; fail-open als Pandoc niet aanwezig
- [ ] `foundry build` heeft output overwrite bescherming; `--yes` slaat over
