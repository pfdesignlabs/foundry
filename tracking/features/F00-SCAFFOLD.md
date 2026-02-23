# F00-SCAFFOLD: Scaffold, Governance & DEV_GOVERNANCE

## Doel
Foundry's fundament opzetten: package structuur, dependency management, declaratieve
governance (CLAUDE.md), en runtime enforcement via het .forge/ governor systeem.

## Work Items
- WI_0001: pyproject.toml, package skeleton, tracking/, DECISIONS.md
- WI_0002: CLAUDE.md — architectuur non-negotiables, fase structuur, bootstrap sectie
- WI_0003: governor.py — bash-intercept, session-start, commit, branch-create, status events
- WI_0004: Contracten — merge-strategy.yaml, commit-discipline.yaml
- WI_0005: pre-bash.sh hook + .claude/settings.json
- WI_0006: .forge/slice.yaml (SP_001) + workitem-discipline.yaml

## Afhankelijkheden
Geen — dit is de basis voor alle andere features.

## Acceptatiecriteria
- [ ] `uv sync` slaagt zonder errors
- [ ] CLAUDE.md aanwezig met alle 6 architectuur non-negotiables
- [ ] `python .forge/governor.py status` geeft SP_001 overzicht
- [ ] `git push origin main` wordt geblokkeerd door pre-bash.sh hook (exit 2)
- [ ] Correcte commit op wi/* branch merged naar feat/f00-scaffold
- [ ] tracking/features/ bevat F00–F05, tracking/decisions/DECISIONS.md bevat D0001–D0003
