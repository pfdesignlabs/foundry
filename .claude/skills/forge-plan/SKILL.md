# /forge-plan — Work Item Status Updater

Laat de gebruiker interactief de status van work items in de actieve sprint bijwerken.

## Stappen

1. Lees `.forge/slice.yaml` om alle work items op te halen.

2. Toon een overzicht van alle work items met hun huidige status:
   ```
   WI_0001  ✅ done        Scaffold: pyproject.toml, package skeleton
   WI_0007  🔄 in_progress /forge-status + /forge-plan skills
   WI_0008  ⬜ planned     SessionStart + Stop hooks
   ...
   ```

3. Vraag de gebruiker welk work item bijgewerkt moet worden (voer ID in, bijv. `WI_0008`).

4. Vraag naar de nieuwe status. Geldige waarden:
   - `planned` — nog niet gestart
   - `in_progress` — actief in bewerking
   - `done` — afgerond
   - `blocked` — geblokkeerd (vraag dan ook naar reden)

5. **Alleen bij overgang naar `done`:**
   - Vraag om `outcome`: een korte beschrijving van wat er opgeleverd is.
   - Vraag om `evidence`: een of meer bestandspaden of URLs (komma-gescheiden).
     Splits deze op in een YAML-lijst.
   - Vraag ook of de branch gezet moet worden (als die nog `null` is).

6. **Bij alle andere transities** (inclusief terugzetten naar `planned` of `in_progress`):
   - Geen extra velden verplicht, maar vraag optioneel of de gebruiker een notitie wil toevoegen aan `outcome`.

7. Pas `.forge/slice.yaml` aan:
   - Werk `status` bij voor het gekozen work item.
   - Werk `branch` bij als die nog `null` was en de gebruiker een naam opgaf.
   - Werk `outcome` en `evidence` bij bij overgang naar `done`.
   - Herbereken `metrics.completed_this_slice`: tel alle work items met `status: done`.

8. Voer uit: `python .forge/governor.py status`
   Dit regenereert `tracking/STATUS.md`.

9. Bevestig de update aan de gebruiker:
   ```
   ✅ WI_0008 bijgewerkt naar: in_progress
   metrics.completed_this_slice: 6 → 6 (ongewijzigd)
   STATUS.md opnieuw gegenereerd.
   ```

## Regels

- Alle status-transities zijn toegestaan (ook terugzetten).
- Maximaal 2 items mogen tegelijk `in_progress` zijn (governor waarschuwt automatisch).
- Schrijf YAML met behoud van de bestaande structuur en volgorde.
- Voeg geen nieuwe velden toe aan work items buiten de bestaande structuur.
