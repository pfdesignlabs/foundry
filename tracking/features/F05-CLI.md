# F05-CLI: CLI Polish & UX

## Doel
Foundry's CLI interface afwerken: duidelijke help tekst, dry-run modus,
error handling, en een goede developer experience voor eindgebruikers.

## Work Items
- WI_0034: `foundry init` — project initialisatie met interactieve configuratie
- WI_0035: Dry-run modus voor ingest + generate (`--dry-run`)
- WI_0036: Rijke error messages met actionable feedback
- WI_0037: `foundry --version` en `foundry status` (project overzicht)
- WI_0038: Config file support (`foundry.yaml` per project)

## Afhankelijkheden
- F04-FEATURE-GATES (volledige pipeline aanwezig)

## Acceptatiecriteria
- [ ] `foundry --help` geeft duidelijke beschrijving van alle commands
- [ ] `foundry ingest --dry-run` toont wat er ingested zou worden zonder te schrijven
- [ ] `foundry generate --dry-run` toont context + prompt zonder LLM aan te roepen
- [ ] Foutmeldingen bevatten altijd: wat ging er mis, wat moet de gebruiker doen
- [ ] `foundry.yaml` configuratiebestand overschrijft defaults
