# Sprint SP_001 — Scaffold, CLAUDE.md & DEV_GOVERNANCE

**Target:** 2026-03-01  
**Started:** 2026-02-23  
**Voortgang:** 7/10 work items done

**Doel:** Foundry's fundament opzetten: package structuur, declaratieve governance (CLAUDE.md), en runtime enforcement via het .forge/ governor systeem (contracten, hooks, slice tracking).

---

## ✅ WI_0001 — Scaffold: pyproject.toml, package skeleton, tracking/, DECISIONS.md

**Status:** done  
**Branch:** `wi/WI_0001-scaffold`

**Beschrijving:**  
pyproject.toml aanmaken met alle project dependencies (typer, openai, PyYAML, ebooklib, pypdf, sqlite-vec). Package skeleton opzetten onder src/foundry/. Tracking directory aanmaken met feature specs (F00-F05) en initial decisions log.

**Acceptatiecriteria:**

[x] pyproject.toml aanwezig met alle afhankelijkheden
[x] src/foundry/__init__.py aanwezig
[x] tracking/features/ bevat F00-F05.md feature specs
[x] tracking/decisions/DECISIONS.md bevat D0001 (RAG), D0002 (sqlite-vec), D0003 (branches)
[x] .gitignore bijgewerkt met .forge/audit.jsonl

**Evidence:**

- `pyproject.toml`
- `src/foundry/__init__.py`
- `tracking/features/F00-SCAFFOLD.md`
- `tracking/decisions/DECISIONS.md`

**Uitkomst:**  
Succesvol opgeleverd. Package structuur aangemaakt, alle 6 feature files beschreven, 3 architectuurbeslissingen gedocumenteerd (RAG, sqlite-vec, branch hierarchy).

---

## ✅ WI_0002 — CLAUDE.md met architectuur non-negotiables en fase structuur

**Status:** done  
**Branch:** `wi/WI_0002-claude-md`

**Beschrijving:**  
CLAUDE.md aanmaken in de repo root als declaratieve governance laag. Bevat: architectuur non-negotiables (6 locked decisions), tech stack, repo map, branch strategy, fase structuur, sessie discipline, hard rules, en bootstrap sectie.

**Acceptatiecriteria:**

[x] CLAUDE.md aanwezig met alle 6 architectuur non-negotiables
[x] Bootstrap sectie aanwezig voor eerste sessie zonder slice.yaml
[x] Verwijzing naar .forge/slice.yaml als actieve slice bron
[x] Branch hierarchy gedocumenteerd (wi/* → feat/* → develop → main)
[x] Fase structuur (0-5) gedocumenteerd

**Evidence:**

- `CLAUDE.md`

**Uitkomst:**  
Succesvol opgeleverd. CLAUDE.md beschrijft volledig de governance structuur, architectuurkeuzes zijn als wet vastgelegd, bootstrap protocol aanwezig.

---

## ✅ WI_0003 — governor.py: bash-intercept, session-start, commit, branch-create, status

**Status:** done  
**Branch:** `wi/WI_0003-governor-core`

**Beschrijving:**  
Governor engine implementeren die runtime enforcement uitvoert. Events: bash-intercept (intercepteert git commands via Claude Code hook), session-start (controleert slice health bij sessie start), commit (valideert commit message format), branch-create (valideert branch naming — hard-block), status (genereert slice overzicht + STATUS.md).

**Acceptatiecriteria:**

[x] git push origin main → exit 2 (hard-block)
[x] git commit -m 'fix stuff' → verdict: warn
[x] git checkout -b random-name → verdict: block (exit 2)
[x] git checkout -b wi/WI_0001-slug → verdict: allow
[x] python .forge/governor.py status → JSON output zonder hangs
[x] STATUS.md wordt aangemaakt na status event

**Evidence:**

- `.forge/governor.py`

**Uitkomst:**  
Succesvol opgeleverd. Governor werkt correct voor alle events. Datetime deprecation warning gefixed (utcnow → now(timezone.utc)). bash-intercept leest geen stdin voor niet-intercept events (blokkeerprobleem opgelost).

---

## ✅ WI_0004 — Contracten: merge-strategy.yaml + commit-discipline.yaml

**Status:** done  
**Branch:** `wi/WI_0004-contracts`

**Beschrijving:**  
YAML contracten aanmaken die de governance regels declaratief vastleggen. merge-strategy.yaml: branch naming (hard-block), protected branch push/merge regels. commit-discipline.yaml: commit message format validatie (warn).

**Acceptatiecriteria:**

[x] merge-strategy.yaml aanwezig met branch-naming rule (hard-block)
[x] commit-discipline.yaml aanwezig met commit format rule (warn)
[x] Contracten worden geladen door governor._load_contracts()

**Evidence:**

- `.forge/contracts/merge-strategy.yaml`
- `.forge/contracts/commit-discipline.yaml`

**Uitkomst:**  
Succesvol opgeleverd. Twee contracten aangemaakt. Branch naming is hard-block, commit discipline is warn (informerend). Contracten zijn machine-readable YAML.

---

## ✅ WI_0005 — pre-bash.sh hook + .claude/settings.json

**Status:** done  
**Branch:** `wi/WI_0005-hooks`

**Beschrijving:**  
Claude Code hook opzetten die alle Bash tool-calls onderschept en doorstuur naar de governor. pre-bash.sh is één regel (exec python .forge/governor.py bash-intercept). settings.json registreert de hook voor PreToolUse + SessionStart events.

**Acceptatiecriteria:**

[x] pre-bash.sh is executable (chmod +x)
[x] echo '{"tool_input":{"command":"git push origin main"}}' | .forge/hooks/pre-bash.sh → exit 2
[x] .claude/settings.json bevat PreToolUse + SessionStart hooks
[x] settings.json is gecommit naar repo (governance geldt voor iedereen)

**Evidence:**

- `.forge/hooks/pre-bash.sh`
- `.claude/settings.json`

**Uitkomst:**  
Succesvol opgeleverd. Hook is één regel, geen bash JSON parsing, geen jq dependency. Governor doet alle zware verwerking. settings.json gecommit als onderdeel van repo governance.

---

## ✅ WI_0006 — slice.yaml (SP_001) + workitem-discipline.yaml contract

**Status:** done  
**Branch:** `wi/WI_0006-slice-tracker`

**Beschrijving:**  
.forge/slice.yaml aanmaken als machine-readable sprint tracker voor SP_001. Bevat alle 10 work items met status, branch, evidence, beschrijving en acceptatiecriteria. workitem-discipline.yaml contract aanmaken voor WIP limits en slice membership checks. STATUS.md generatie verrijkt met volledige WI history.

**Acceptatiecriteria:**

[x] .forge/slice.yaml aanwezig met alle 10 WIs voor SP_001
[x] python .forge/governor.py status toont 5/10 done
[x] tracking/STATUS.md bevat volledige WI beschrijvingen, criteria en uitkomsten
[x] workitem-discipline.yaml contract aanwezig

**Evidence:**

- `.forge/slice.yaml`
- `.forge/contracts/workitem-discipline.yaml`
- `tracking/STATUS.md`

**Uitkomst:**  
Succesvol opgeleverd. slice.yaml is de enige bron van waarheid voor sprint tracking. STATUS.md bevat nu volledige sprint history inclusief beschrijvingen, criteria, uitkomsten.

---

## ✅ WI_0007 — /forge-status + /forge-plan skills (forward planning)

**Status:** done  
**Branch:** `wi/WI_0007-forge-skills`

**Beschrijving:**  
Claude Code skills aanmaken als forward planning. /forge-status toont interactief dashboard vanuit slice.yaml. /forge-plan laat WI statussen updaten.

**Acceptatiecriteria:**

[x] .claude/skills/forge-status/SKILL.md aanwezig
[x] .claude/skills/forge-plan/SKILL.md aanwezig
[x] Skills werken wanneer Claude Code skills ondersteund worden

**Evidence:**

- `.claude/skills/forge-status/SKILL.md`
- `.claude/skills/forge-plan/SKILL.md`

**Uitkomst:**  
Succesvol opgeleverd. forge-status toont volledig sprint dashboard (header, tabel, WI details, waarschuwingen) na governor status run. forge-plan ondersteunt alle status-transities inclusief terugzetten, vraagt outcome + evidence bij done, herberekent completed_this_slice automatisch.

**Afhankelijkheden:** WI_0006

---

## ⬜ WI_0008 — SessionStart + Stop hooks

**Status:** planned  
**Branch:** `—`

**Beschrijving:**  
SessionStart hook geeft slice status bij sessie start (BLOCK bij corrupt slice.yaml, WARN voor rest). Stop hook toont sprint samenvatting aan einde van sessie.

**Acceptatiecriteria:**

[ ] SessionStart hook geeft sprint status bij sessie start
[ ] Corrupt slice.yaml → exit 2 (sessie geblokkeerd)
[ ] Stop hook genereert session summary

**Afhankelijkheden:** WI_0005, WI_0006

---

## ⬜ WI_0009 — Testing contract + pre-commit test check

**Status:** planned  
**Branch:** `—`

**Beschrijving:**  
testing.yaml contract aanmaken. pre-bash.sh uitbreiden: bij git commit met gewijzigde .py bestanden → run pytest --tb=short -q → WARN als falend (fail-open, 60s timeout).

**Acceptatiecriteria:**

[ ] .forge/contracts/testing.yaml aanwezig
[ ] git commit met staged .py bestanden triggert pytest run
[ ] Falende tests geven WARN (niet BLOCK) — fail-open

---

## ⬜ WI_0010 — Governor unit tests + audit-summary command

**Status:** planned  
**Branch:** `—`

**Beschrijving:**  
pytest unit tests voor governor.py (minimaal 15 cases): commit validatie, branch naming, slice membership, WIP limits, verdict prioriteit, graceful handling van ontbrekende contracten/slice. Audit-summary subcommand toevoegen.

**Acceptatiecriteria:**

[ ] tests/test_governor.py aanwezig met ≥15 test cases
[ ] pytest slaagt groen
[ ] python .forge/governor.py audit-summary toont recent audit trail

---

_Gegenereerd door governor op 2026-02-23 16:57 UTC_
