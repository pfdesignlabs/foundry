# F04-FEATURE-GATES: Feature Gates & Approval

## Doel
Generatie koppelen aan door mensen goedgekeurde feature specs. Geen features/ directory
of geen goedgekeurde features = generatie geblokkeerd. Human review als harde gate.

## Work Items
- WI_0030: Feature spec parser (leest F-*.md files, detecteert goedkeuring)
- WI_0031: Approval check — gate enforcement voor `foundry generate`
- WI_0032: `foundry features list` — overzicht van features + status
- WI_0033: `foundry features approve <feature-id>` — goedkeuring registreren

## Afhankelijkheden
- F03-RAG-GENERATE (generate command aanwezig om te gaten)

## Acceptatiecriteria
- [ ] `foundry generate` zonder features/ directory geeft duidelijke fout
- [ ] `foundry generate` met ongoedgekeurde features geeft duidelijke fout
- [ ] `foundry features approve F01` werkt en unlocks generatie
- [ ] `foundry features list` toont goedkeuringsstatus per feature
