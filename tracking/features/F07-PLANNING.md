# F07-PLANNING: LLM-assisted Project Planning

## Doel
Foundry helpt de operator de kloof te overbruggen tussen de kennisbank (ingested bronnen)
en feature specs + WI-lijst. `foundry plan` leest het project charter en de auto-gegenereerde
bron-samenvattingen, analyseert welke capabilities features moeten worden en welke WIs
logisch zijn per capability, en schrijft draft feature specs + WI-kandidaten.

**Menselijke review is altijd vereist.** Draft features worden nooit automatisch goedgekeurd.
De `foundry features approve` gate blijft de enige manier om features klaar te maken
voor generatie.

## Workflow positie
```
foundry init
  → tracking/project-context.md (project charter)
  → tracking/sources.md (kennistekorten checklist)

foundry ingest (eerste kennisbank opbouwen)
  → source_summaries opgeslagen in DB

foundry plan                          ← dit is F07
  → leest project-context.md + source_summaries
  → LLM analyseert: capabilities → features, features → WIs
  → schrijft draft features/*.md (NIET goedgekeurd)
  → schrijft aanvulling tracking/work-items.md

operator reviewt + past aan (handmatig)

foundry features approve <feature>    ← gate blijft ongewijzigd
```

## Work Items
- WI_0044: `foundry plan` CLI command
  - **Vereiste:** minimaal één ingest-run met source_summaries in DB aanwezig.
    Geen ingest → hard fail: "No sources ingested yet. Run: foundry ingest --source <path>"
  - **Vereiste:** `project.brief` geconfigureerd in foundry.yaml (tracking/project-context.md)
    Niet geconfigureerd → hard fail: "No project.brief configured. Run: foundry init"
  - **Input:**
    1. `tracking/project-context.md` — verbatim project charter
    2. Source summaries uit DB — alle samenvattingen (max `plan.max_summaries`, default 20)
  - **LLM analyse prompt (system):**
    ```
    You are a project planning assistant. Based on the project context and knowledge base
    summaries, identify:
    1. Which capabilities need to be built (as feature documents)
    2. Which work items (tasks) are needed per capability
    3. Which knowledge gaps still exist (not covered by ingested sources)

    Output format: structured JSON with features[], work_items[], knowledge_gaps[]
    ```
  - **Output:**
    - Per geïdentificeerde feature: draft `features/{slug}.md` aangemaakt:
      ```markdown
      > ⚠ DRAFT — gegenereerd door foundry plan op {datum}.
      > Review volledig vóór `foundry features approve {feature}`.

      # {Feature Naam}

      ## Output definitie
      {LLM-gegenereerde beschrijving van verwachte output}

      ## Bronhierarchie
      {LLM-gesuggereerde primaire bronnen op basis van summaries}

      ## Vereiste capabilities
      {LLM-geïdentificeerde technische requirements}
      ```
    - Draft feature NOOIT met `## Approved` — dit is een harde regel
    - Bestaande `features/*.md` worden NIET overschreven — skip met melding
    - Aanvulling `tracking/work-items.md` met WI-kandidaten per feature:
      ```markdown
      ## WI-kandidaten (foundry plan output — {datum})

      ### {Feature Naam}
      - [ ] WI: {WI beschrijving} [type: digital]
      - [ ] WI: {WI beschrijving} [type: physical]
      ```
    - Kennistekorten die nog open staan: getoond na afloop:
      ```
      Knowledge gaps identified:
        - DMX512 timing specs (not in knowledge base)
        - ESP32 power consumption data (partial coverage)
      Consider: foundry ingest --source <url/file>
      ```
  - **`--dry-run`:** toont LLM analyse output (features + WIs + gaps) zonder bestanden te schrijven
  - **`--yes`:** slaat bevestiging over ("Write N draft features? [y/N]")
  - Config: `plan.model` (default `openai/gpt-4o`), `plan.max_summaries` (default 20)

## Configuratie (foundry.yaml)
```yaml
plan:
  model: openai/gpt-4o              # LLM voor planning analyse
  max_summaries: 20                 # max source summaries meegestuurd naar planner LLM
```

## Security noot
Draft features worden gegenereerd op basis van source_summaries. Als een ingested bron
(website, audio) prompt injection bevat, kan dit in de summaries en uiteindelijk in de
draft features terechtkomen. Mitigaties:
1. Disclaimer header in elke draft feature maakt de oorsprong expliciet
2. Draft features vereisen menselijke review vóór `foundry features approve`
3. De `## Approved` gate is de definitieve beveiligingslaag

## Afhankelijkheden
- F02-INGEST (minimaal één ingest-run vereist — source_summaries aanwezig)
- F05-CLI (project.brief geconfigureerd via foundry init wizard)

## Acceptatiecriteria
- [ ] `foundry plan` faalt hard als geen source_summaries in DB aanwezig
- [ ] `foundry plan` faalt hard als `project.brief` niet geconfigureerd
- [ ] `foundry plan` leest project-context.md + source summaries (max `plan.max_summaries`)
- [ ] Draft features aangemaakt in `features/` met disclaimer header
- [ ] Draft features bevatten NOOIT `## Approved` heading
- [ ] Bestaande `features/*.md` worden NIET overschreven — skip met melding
- [ ] `tracking/work-items.md` aangevuld met WI-kandidaten per feature
- [ ] Kennistekorten geïdentificeerd en getoond met ingest-suggestie
- [ ] `--dry-run` toont analyse zonder bestanden te schrijven
- [ ] `--yes` slaat bevestiging over
- [ ] `plan.model` en `plan.max_summaries` configureerbaar in foundry.yaml
