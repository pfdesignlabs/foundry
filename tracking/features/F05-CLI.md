# F05-CLI: CLI Polish & UX

## Doel
Foundry's CLI interface afwerken: `--project` global flag, duidelijke help tekst,
rijke error messages, progress indicators, en een goede developer experience.
`--dry-run` voor ingest zit in F02; `--dry-run` voor generate zit in F03.

Foundry bedient twee begunstigden (D0014):
- **Operator**: ingest, feature specs schrijven, projecttaken tracken, audit trail
- **Klant**: ontvangt geconsolideerd leveringsdocument via `foundry build`

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
  - Wizard stelt vragen: project naam, te activeren chunkers, embedding model (provider/model)
  - Scaffold aangemaakt in de opgegeven directory (of huidige directory bij geen argument):
    - `.foundry.db` — lege database met schema
    - `foundry.yaml` — met wizard-keuzes als startpunt (incl. lege `delivery:` sectie)
    - `features/` — lege directory (hier komen feature specs per projecttaak)
    - `tracking/` — interne projecttracking (niet voor klant, niet in delivery)
      - `tracking/sources.md` — template bronnenlijst (te ingesteren bronnen checklist)
      - `tracking/work-items.md` — template projecttakenlijst (hardware/software taken)
      - `tracking/build-plan.md` — template leveringsplan (companion bij `delivery:` config)
  - **`.gitignore` update:** voegt `.foundry.db` en `foundry.yaml` toe als `.gitignore`
    aanwezig is — database bevat gevoelige ingested content, config kan model names bevatten
  - Globale config aangemaakt als nog niet aanwezig: `~/.foundry/config.yaml`
    - Aangemaakt met `mode=0o600` (alleen owner leesbaar)
    - Bevat model defaults, **NOOIT API keys**
    - API keys altijd via environment variables
- WI_0035: Progress indicators via rich
  - Ingest: progress bar over chunks (Chunk N/N), aparte teller voor LLM calls
  - Generate: stap-indicator (Retrieving → Scoring → Checking conflicts → Assembling → Generating)
  - Gebruik: `rich.progress.Progress`
- WI_0036: Rijke error messages met actionable feedback
  - Elke foutmelding: wat ging er mis + exacte actie voor de gebruiker
  - Voorbeelden:
    - "No API key for 'openai'. Set: export OPENAI_API_KEY=sk-..."
    - "No approved feature specs. Run: foundry features approve <name>"
    - "Embedding model mismatch: database uses 'openai/text-embedding-3-small',
       config has 'openai/text-embedding-3-large'. Re-ingest or update config."
    - "No .foundry.db found. Run: foundry init"
- WI_0037: `foundry --version` en `foundry status`
  - `foundry --version`: versie uit pyproject.toml
  - `foundry status`: project overzicht
    - Database pad + bestandsgrootte
    - Aantal bronnen, chunks, vec tables (per model + dimensie)
    - Goedgekeurde features
    - Laatste ingest datum
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
- WI_0040: `foundry build` — geconsolideerd klantleveringsdocument samenstellen (D0014)
  - Leest `delivery:` sectie uit `foundry.yaml`
  - Per sectie: roept intern `generate` aan met bijbehorende `topic` + `feature` spec
  - Validatie vóór generatie: alle genoemde feature specs moeten goedgekeurd zijn
  - Assembleert outputs in gedefinieerde volgorde, optioneel met H1 header per sectie
  - Resultaat: één `.md` document als klant-deliverable
  - `--output PATH` overschrijft `delivery.output` uit config
  - `--dry-run`: toont sectie-volgorde + feature specs per sectie zonder generatie
  - Output overwrite bescherming (zelfde als `foundry generate`): vraagt bevestiging

## Configuratie (foundry.yaml — delivery sectie)
```yaml
delivery:
  output: "build-guide.md"          # standaard output pad voor foundry build
  sections:
    - feature: wiring-guide          # naam van goedgekeurde feature spec (zonder .md)
      topic: "DMX controller wiring and electrical connections"
      heading: "Wiring Guide"        # optionele H1 in samengesteld document
    - feature: firmware-architecture
      topic: "firmware structure and component interactions"
      heading: "Firmware Architecture"
    - feature: assembly-steps
      topic: "step-by-step assembly procedure"
      heading: "Assembly Procedure"
```

Sommige secties kunnen intern gegenereerde content bevatten (bijv. beslissingenlog) die
ook in de klantlevering terechtkomen — dit wordt per project bepaald via `delivery.sections`.

## Afhankelijkheden
- F04-FEATURE-GATES (volledige pipeline aanwezig)

## Acceptatiecriteria
- [ ] `--project PATH` global flag beschikbaar op alle commands
- [ ] Zonder `--project`: `.foundry.db` gezocht in huidige directory; niet gevonden → hard fail
- [ ] `foundry --help` geeft duidelijke beschrijving van alle commands
- [ ] `foundry init` wizard creeërt `.foundry.db` + `foundry.yaml` + `features/` in één keer
- [ ] `foundry init` voegt `.foundry.db` toe aan `.gitignore` als die aanwezig is
- [ ] `~/.foundry/config.yaml` aangemaakt met `mode=0o600` (owner-only)
- [ ] Globale config weigert API keys — bevat alleen model defaults
- [ ] Progress indicators actief bij ingest (chunks) en generate (stappen incl. conflict check)
- [ ] Foutmeldingen bevatten altijd: wat + actie
- [ ] `foundry status` toont bronnen, chunks, vec tables, goedgekeurde features, laatste ingest
- [ ] `foundry remove --source <pad>` verwijdert bron volledig met bevestiging
- [ ] Config prioriteit: CLI > env vars > per-project > globaal > defaults
- [ ] `yaml.safe_load()` voor alle config reads — nooit `yaml.load()`
- [ ] `foundry init` maakt `tracking/` aan met `sources.md`, `work-items.md`, `build-plan.md` templates
- [ ] `foundry init` voegt lege `delivery:` sectie toe aan gegenereerde `foundry.yaml`
- [ ] `foundry build` assembleert outputs van goedgekeurde feature specs in `delivery.sections` volgorde
- [ ] `foundry build` valideert dat alle genoemde feature specs goedgekeurd zijn vóór generatie
- [ ] `foundry build --dry-run` toont sectie-volgorde + feature specs zonder generatie
- [ ] `foundry build --output PATH` overschrijft `delivery.output` uit config
- [ ] `foundry build` heeft output overwrite bescherming (vraagt bevestiging; `--yes` slaat over)
