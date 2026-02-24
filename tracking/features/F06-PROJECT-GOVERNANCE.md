# F06-PROJECT-GOVERNANCE: Project Governance Built-in

## Doel
Foundry scaffoldt zijn eigen governance-machinerie in nieuwe projecten via `foundry init --git`.
Projecten kunnen WIs, sprints en git operations beheren via Foundry CLI (`foundry wi`,
`foundry sprint`, `foundry governance`). Hardware lifecycle fasen (POC/EVT/DVT/PVT/MP)
zijn first-class concepten in slice.yaml. De governance handhaving werkt als Foundry
built-in — geen governor.py kopie per project (D0015).

## WI type systeem
Niet alle WIs zijn digitaal werk. Drie types in slice.yaml:

| Type | Beschrijving | `foundry wi start` | Bewijs |
|------|-------------|---------------------|--------|
| `digital` | Computer werk (code, docs, ontwerp, schematic) | Maakt git branch `wi/WI_XXXX-slug` | PR, bestandspad |
| `physical` | Echte-wereld actie (fabricage, levering, testen) | Geen branch, markeert in_progress | Foto, trackingnummer, testresultaat |
| `hybrid` | Digitale fase → fysieke fase (bijv. firmware + flashen) | Vraagt welke fase; branch als digital | Per fase |

```yaml
# .forge/slice.yaml voorbeeld (project slice)
slice:
  id: SP_003
  phase: EVT-1          # optioneel: POC | EVT-1 | EVT-2 | DVT-1 | DVT-2 | PVT | MP | intern
  name: "Engineering Validation Test 1"
  started: 2026-03-01
  target: 2026-03-28
  goal: >
    Eerste werkend prototype valideren: DMX512 protocol, WiFi, LED driver circuit.

workitems:
  - id: WI_0001
    title: "PCB schematic design"
    type: digital          # digital | physical | hybrid
    status: done
    branch: wi/WI_0001-schematic-design
    outcome: "KiCad schematic compleet, review klaar"
    evidence: ["output/schematic-v1.kicad_sch"]

  - id: WI_0002
    title: "PCB layout + Gerbers"
    type: digital
    status: in_progress
    branch: wi/WI_0002-pcb-layout

  - id: WI_0003
    title: "PCB bestellen bij PCBWay"
    type: physical
    status: pending
    depends_on: [WI_0002]

  - id: WI_0004
    title: "Prototype assembleren en testen"
    type: physical
    status: pending
    depends_on: [WI_0003]
    evidence: ""            # foto pad of testrapport — ingevuld bij done

  - id: WI_0005
    title: "Firmware + flashen"
    type: hybrid
    status: pending
    depends_on: [WI_0004]
```

## Hardware lifecycle fasen
Optioneel `phase` veld op sprint niveau. Geldige waarden:

| Fase | Beschrijving |
|------|-------------|
| `POC` | Proof of Concept — haalbaarheidsvalidatie |
| `EVT-1` | Engineering Validation Test 1 — eerste prototype |
| `EVT-2`, `EVT-x` | Verdere engineering iteraties |
| `DVT-1` | Design Validation Test 1 — design bevroren |
| `DVT-2`, `DVT-x` | Design iteraties na DVT |
| `PVT` | Production Validation Test |
| `MP` | Mass Production |
| `intern` | Intern project, geen klant, geen fase-structuur |

## Project scaffold (aangemaakt door foundry init met git=Y)
```
project/
  .foundry.db                          ← kennisbank
  foundry.yaml                         ← project config (project: + delivery: secties)
  features/                            ← feature specs per projecttaak
  tracking/
    project-context.md                 ← project charter (= project.brief)
    sources.md                         ← kennistekorten checklist (human-only)
    work-items.md                      ← WI-kandidaten per capability
    build-plan.md                      ← delivery layout template
  .forge/
    # GEEN governor.py — hooks roepen 'foundry governance' aan
    slice.yaml                         ← lege sprint, klaar om te vullen
    contracts/
      merge-strategy.yaml              ← branch naming + merge-hiërarchie
      commit-discipline.yaml           ← commit format [WI_XXXX] prefix
      workitem-discipline.yaml         ← WI/WIP limits
    hooks/
      pre-bash.sh                      ← fail-open hook (zie onder)
    audit.jsonl                        ← gitignored
  .claude/
    settings.json                      ← PreToolUse + SessionStart hooks
  CLAUDE.md                            ← project governance doc (wizard-ingevuld)
  .gitignore                           ← .foundry.db, foundry.yaml, .forge/audit.jsonl
```

### pre-bash.sh (fail-open hook)
```bash
#!/bin/sh
# Roept foundry governance aan als Foundry in PATH is.
# Fail-open als Foundry niet geïnstalleerd is (project werkt ook zonder).
command -v foundry >/dev/null 2>&1 && exec foundry governance bash-intercept
exit 0
```

### Git initialisatie volgorde
```bash
git init
git checkout -b develop              # integratiebranch (altijd aanwezig)
git add .
git commit -m "[DEV_GOVERNANCE] scaffold: foundry init voor <project-naam>"
```
`main` wordt aangemaakt bij eerste release (niet bij init).

## Work Items
- WI_0041: `foundry wi` subcommands
  - `foundry wi list` — leest `.forge/slice.yaml`, toont WIs met type + status
    - Groepeert per fase als `phase` aanwezig in slice
    - Type-icoon: 💻 digital, 🔧 physical, 🔀 hybrid
  - `foundry wi start WI_XXXX` — WI starten:
    - Vraagt slug (gevalideerd: `^[a-z0-9-]{1,50}$`)
    - `digital`: maakt branch `wi/WI_XXXX-{slug}` via `shell=False`:
      `subprocess.run(["git", "checkout", "-b", f"wi/{wi_id}-{slug}"], shell=False)`
    - `physical`: markeert status `in_progress` in slice.yaml — geen branch
    - `hybrid`: vraagt "Digitale fase of fysieke fase?" → gedraagt zich als digital of physical
    - Git repo vinden: `git rev-parse --show-toplevel` — hard fail als niet in git repo
    - Branch bestaat al → duidelijke melding + actie
    - WI al in_progress → melding (kan toch starten met `--force`)
  - `foundry wi done WI_XXXX` — WI afronden:
    - `digital`: vraagt outcome (vrijte tekst) + evidence (bestandspad of URL)
    - `physical`: vraagt outcome + evidence (foto pad, trackingnummer, testresultaat)
    - Schrijft outcome + evidence naar slice.yaml via `yaml.safe_dump()`
    - Markeert status `done` in slice.yaml
  - **Slug validatie:** alleen `^[a-z0-9-]{1,50}$` toegestaan — geeft duidelijke error bij afwijking
  - **Altijd `shell=False`** — nooit `shell=True` met user-supplied input
- WI_0042: `foundry sprint` subcommands
  - `foundry sprint create` — nieuwe sprint aanmaken:
    ```
    Sprint naam? → EVT-1 Sprint
    Project fase? [POC/EVT-1/EVT-2/DVT-1/DVT-2/PVT/MP/intern/geen] → EVT-1
    Target datum? (YYYY-MM-DD) → 2026-03-28
    Sprint doel? (optioneel, Enter om over te slaan) →
    ```
    Schrijft nieuwe sprint naar `.forge/slice.yaml` via `yaml.safe_dump()`.
    Commentaar in slice.yaml wordt niet bewaard (bewuste keuze, `yaml.safe_dump()` limiet).
  - `foundry sprint status` — huidige sprint voortgang:
    ```
    Sprint SP_003 | Phase: EVT-1 | target 2026-03-28
    Progress: 4/9 WIs done
      💻 digital: 2/5 done
      🔧 physical: 0/3 done (2 pending, 0 in progress)
      🔀 hybrid: 2/1 done (1 in progress)
    Open items:
      ⏳ WI_0002 [digital] PCB layout + Gerbers (in progress)
      ○ WI_0003 [physical] PCB bestellen bij PCBWay (pending, depends on WI_0002)
    ```
- WI_0043: `foundry governance` built-in (bash-intercept, audit-summary, status)
  - **Geen DB dependency** — werkt ook zonder `.foundry.db`. Enkel `.forge/` vereist.
  - **`foundry governance bash-intercept`:**
    - Leest bash command via stdin als JSON: `{"tool_input": {"command": "git push origin main"}}`
    - Laadt contracten uit `.forge/contracts/` relatief aan git repo root
      (`git rev-parse --show-toplevel` → fallback naar CWD)
    - Past regels toe: branch naming (hard-block), merge-hiërarchie (hard-block),
      commit format (warn), protected push (hard-block)
    - **Audit log sanitisatie:** credentials uit git URLs verwijderd vóór logging:
      regex `https://[^@]+@` → `https://***@` (GIT_TOKEN bescherming)
    - Output JSON: `{"verdict": "allow"|"warn"|"block", "message": "..."}`
    - Bij ontbrekend `.forge/`: graceful exit 0 (fail-open)
  - **`foundry governance audit-summary`:**
    - Leest `.forge/audit.jsonl` (laatste 20 events)
    - Toont: timestamp, event type, verdict, message
  - **`foundry governance status`:**
    - Toont slice status (zelfde als `foundry sprint status` maar compacter)

## Configuratie (per project)
Alle governance config zit in `.forge/contracts/`:

```yaml
# .forge/contracts/merge-strategy.yaml
rules:
  - name: "branch-naming"
    severity: block
    description: "Branch namen moeten wi/WI_XXXX-slug, feat/slug, of release/vX.Y.Z zijn"

  - name: "merge-source-discipline"
    severity: block
    description: "develop accepteert alleen feat/* of release/*; main accepteert alleen release/*"
```

```yaml
# .forge/contracts/commit-discipline.yaml
rules:
  - name: "commit-format"
    severity: warn
    description: "Commit messages moeten beginnen met [WI_XXXX] of [DEV_GOVERNANCE]"
```

## Afhankelijkheden
- F05-CLI (foundry init wizard aanwezig)

## Acceptatiecriteria
- [ ] `foundry wi list` leest `.forge/slice.yaml`, toont WIs met type-icoon + status
- [ ] `foundry wi start WI_XXXX` — digital: maakt branch via `shell=False`
- [ ] `foundry wi start WI_XXXX` — physical: geen branch, markeert in_progress
- [ ] **Slug validatie:** `^[a-z0-9-]{1,50}$` — afwijking → duidelijke error met voorbeeld
- [ ] **Altijd `shell=False`** bij git operaties — nooit `shell=True` met user-supplied input
- [ ] `foundry wi done WI_XXXX` vraagt outcome + evidence; schrijft naar slice.yaml
- [ ] `foundry sprint create` wizard vraagt fase (POC/EVT-1/DVT/PVT/MP/intern/geen)
- [ ] `foundry sprint status` toont done/total per WI type (digital/physical/hybrid)
- [ ] **`foundry governance bash-intercept`:** werkt zonder `.foundry.db` (geen DB dependency)
- [ ] **`foundry governance bash-intercept`:** laadt contracten uit `.forge/contracts/` via git root
- [ ] **Audit log sanitisatie:** `https://token@github.com/` → `https://***@github.com/` in audit.jsonl
- [ ] **`foundry governance bash-intercept`:** geen `.forge/` → exit 0 (graceful fail-open)
- [ ] `pre-bash.sh` hook: fail-open als `foundry` niet in PATH (exit 0)
- [ ] `foundry init` met git=Y: `git init` + `develop` branch + slice.yaml + contracts/ + hooks/
- [ ] `foundry init` met git=Y: CLAUDE.md aangemaakt met projectnaam + doel
- [ ] **Hardware lifecycle:** `phase` veld in slice.yaml optioneel; geldige waarden gevalideerd
- [ ] `foundry sprint create` vraagt project fase; slaat op in slice.yaml
- [ ] `foundry status` toont fase-voortgang als `.forge/slice.yaml` aanwezig
- [ ] `type: physical` delivery section zonder `.forge/slice.yaml` → warning in delivery doc
- [ ] WI-ID (bijv. WI_0004) nooit zichtbaar in delivery document — alleen heading + description + status-icoon
