# KI Vann 1.0.2

## Utendørs vanning tok ikke imot brytere

Feltet tillot `switch`, `binary_sensor` og `valve`, men det holdt ikke i praksis. Lista er
utvidet til `switch`, `valve`, `binary_sensor`, `input_boolean`, `select` og
`input_select` — utendørs vanning styres på mange vis, og et relé bak en `input_boolean`
er like vanlig som en ventil.

Samtidig ryddet jeg bort en duplisert `binary_sensor` i domenelistene for vaskemaskin og
oppvaskmaskin.

## Vannprisen og to nye sensorer

Nytt felt: **pris for vann og avløp samlet**, i kr/m³. Standard 45, som er omtrent
landsgjennomsnittet — sjekk din egen kommunale faktura, tallet varierer mye.

* **Vann i dag** — summen av alle kategoriene, med liter per person som attributt.
* **Vannkostnad i dag** — kroner, med kostnad per kategori som attributter.

## Hvem som er hjemme

`switch`, `input_select` og `select` kan nå velges, ikke bare `person` og
`binary_sensor`. Posisjonsbrytere er ofte `switch`: på betyr her, av betyr borte.
