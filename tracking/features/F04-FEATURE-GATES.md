# F04-FEATURE-GATES: Feature Gates & Approval

## Doel
Generatie koppelen aan door mensen goedgekeurde feature specs. De `features/` directory
wordt aangemaakt door `foundry init` als onderdeel van de project scaffold. Geen
goedgekeurde feature specs = generatie geblokkeerd. Human review als harde gate.

## Feature spec formaat (per-project)
Een feature spec beschrijft wat er gegenereerd moet worden en welke bronnen leidend zijn:

```markdown
# Wiring Guide

## Output definitie
Doelgroep: assembler. Secties: voeding, signalen, aarding.
Gewenste lengte: ~2000 woorden. Formaat: stap-voor-stap met code blocks voor pinnummers.

## Bronhierarchie
Primair: datasheet.pdf, official-wiring-manual.pdf
Supplementair: community-posts/
Conflicten: primaire bronnen winnen altijd van supplementaire bronnen.

## Approved
Goedgekeurd op 2026-03-15
```

Goedkeuring wordt geregistreerd door `## Approved` als exacte H2 heading toe te voegen
(zie WI_0033). Parser matcht op `^## Approved$` — exact, hoofdlettergevoelig,
geen trailing tekst toegestaan.

## Work Items
- WI_0030: Feature spec parser
  - Leest `*.md` bestanden uit de per-project `features/` directory
  - Detecteert goedkeuring: zoekt naar heading die exact `## Approved` is
    (`^## Approved$` — case-sensitive, geen trailing tekst)
  - Retourneert: spec naam (bestandsnaam zonder .md), inhoud, goedkeuringsstatus,
    goedkeuringsdatum (regel onder `## Approved`)
- WI_0031: Approval check — gate enforcement voor `foundry generate`
  - `features/` directory bestaat niet → hard fail met scaffold instructie
  - Geen `.md` bestanden in `features/` → hard fail
  - Geen goedgekeurde specs → hard fail met lijst van niet-goedgekeurde specs
  - Hard fail toont altijd een volledige checklist van wat ontbreekt (niet stap-voor-stap)
- WI_0032: `foundry features list` — overzicht van features + status
  - Toont per spec: naam, goedkeuringsstatus (✓/✗), datum indien goedgekeurd
- WI_0033: `foundry features approve <feature-name>` — goedkeuring registreren
  - `<feature-name>`: bestandsnaam zonder `.md` extensie (bijv. `wiring-guide`)
  - Voegt toe aan het einde van de spec file:
    ```markdown

    ## Approved
    Goedgekeurd op {datum}
    ```
  - Overschrijft niet als `## Approved` al aanwezig is — geeft melding

## Afhankelijkheden
- F03-RAG-GENERATE (generate command aanwezig om te gaten)

## Acceptatiecriteria
- [ ] Parser detecteert `## Approved` exact (^## Approved$ — geen false positives)
- [ ] `foundry generate` zonder `features/` directory geeft hard fail met volledige checklist
- [ ] `foundry generate` met ongoedgekeurde specs geeft hard fail met lijst
- [ ] `foundry features approve wiring-guide` voegt `## Approved` + datum toe aan
      `features/wiring-guide.md`
- [ ] Dubbele approval op al-goedgekeurde spec geeft melding, overschrijft niet
- [ ] `foundry features list` toont naam + goedkeuringsstatus per spec
