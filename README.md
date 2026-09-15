# KI Vann

Hva går vannet til? Måleren sier hvor mange liter som gikk forrige time, men ikke hvorfor.
Denne integrasjonen fordeler timen på dusj, toalett, håndvask, oppvask, hvitevarer og
utendørs — og lærer literprisen per hendelse av forbruket ditt.

## Hvordan det virker

Med én måling per time kan ingenting skille dusj fra oppvask i sanntid. Det som *kan*
gjøres, er å lære hva hver hendelsestype koster, og deretter fordele den målte timen.

1. **Hendelser telles.** Bevegelsessensorene gjøres om til besøk: et langt besøk på badet
   er en dusj, et kort er håndvask, et besøk på doen er én spyling pluss håndvask.
   Hvitevarer teller sykluser.
2. **Literprisen læres.** Hver time gir en likning: `antall hendelser × ukjent literpris
   = målt forbruk`. Med noen hundre timer løses systemet med ikke-negativ minste
   kvadraters metode. Startgjetningene virker som prior, så kategorier du nesten aldri
   bruker holder seg fornuftige.
3. **Timen fordeles.** Estimatet skaleres så summen blir nøyaktig det måleren viste.
   Fordelingen stemmer dermed alltid med virkeligheten.

Det siste er poenget: modellen later ikke som den vet mer enn den gjør. Er hendelsene
langt fra å forklare det målte, vokser «basis og udefinert» — og det er signalet om at noe
bruker vann uten at en sensor ser det.

## Sensorer du trenger

**Påkrevd:** vannmåleren, kumulativ, i m³ eller liter.

**Gjør fordelingen god:** bevegelse eller nærvær på bad og toalett. Uten disse er det ikke
mye å fordele etter.

**Gjør den bedre:** bevegelse på kjøkken, vaskemaskin og oppvaskmaskin (på/av holder),
bryter eller ventil for utendørs vanning, og hvem som er hjemme.

**Best:** egen måler for utendørs vanning. Da måles den i stedet for å estimeres, og
resten av fordelingen blir renere.

## Entiteter

To sensorer per kategori — liter i dag og forrige time — pluss:

* **Modell** — «Samler data», «Lærer» eller «Innlært», med literprisene og typisk avvik
  som attributter.
* **Forklart av sensorene** — hvor stor andel av forrige time hendelsene forklarer. Lavt
  tall om natten uten at noen er hjemme er verdt å se på.
* **Største forbruker i dag.**

## Tjenester

`ki_vann.lær_na`, `ki_vann.nullstill_laering`, `ki_vann.glem_historikk` og
`ki_vann.sett_liter` — den siste for å overstyre en literpris du vet fra før.

## Hytta

Legg til en ny oppføring med hyttas egen måler og sensorer. Hvert anlegg lærer for seg,
som det skal: en hytte har et helt annet bruksmønster enn et hus.
