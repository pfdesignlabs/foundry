# /forge-status — Sprint Dashboard

Toon een volledig sprint dashboard voor de actieve Foundry sprint.

## Stappen

1. Lees `.forge/slice.yaml` om de sprint data op te halen.

2. Voer uit: `python .forge/governor.py status`
   Dit genereert een vers `tracking/STATUS.md` en retourneert JSON met `completed`, `total`, `by_status`, `missing_evidence` en `warnings`.

3. Presenteer het dashboard in de volgende volgorde:

### Header
```
Sprint <id> — <name>
Gestart: <started>  |  Target: <target>
Voortgang: <completed>/<total> work items done
Doel: <goal>
```

### Voortgangstabel
Toon een tabel met alle work items:

| Status | ID | Titel | Branch |
|--------|----|-------|--------|

Gebruik status-iconen: ✅ done · 🔄 in_progress · ⬜ planned · ❌ blocked

### WI Details (alleen voor in_progress en blocked items)
Voor elk actief of geblokkeerd work item, toon:
- Beschrijving
- Acceptatiecriteria (met checkbox staat)
- Afhankelijkheden (indien aanwezig)

### Waarschuwingen
Als `warnings` of `missing_evidence` niet leeg zijn, toon deze expliciet.

### Footer
```
STATUS.md bijgewerkt op <timestamp>
Volgende stap: gebruik /forge-plan om WI statussen bij te werken.
```
