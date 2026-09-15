# KI Vann 1.0.0

Ny integrasjon som fordeler vannforbruket på dusj, toalett, håndvask, oppvask,
hvitevarer og utendørs — og lærer literprisen per hendelse av ditt eget forbruk.

## Modellen

Hendelser telles fra bevegelsessensorene: langt besøk på badet er dusj, kort er håndvask,
besøk på doen er spyling pluss håndvask, hvitevarer teller sykluser. Hver time gir en
likning `hendelser × literpris = målt forbruk`, og systemet løses med ikke-negativ minste
kvadraters metode — koordinatvis eksakt minimering, i ren Python uten avhengigheter.

Startgjetningene virker som prior og veier mindre etter hvert som datasettet vokser.
Grenser per kategori hindrer at én rar time drar dusjen til 5 liter eller 500.

Fordelingen skaleres så summen blir nøyaktig det måleren viste. Differansen havner i
«basis og udefinert», som dermed er et lekkasjevarsel: går det vann om natten uten at noen
er hjemme, vokser den.

## Hva modellen ikke kan

Håndvask skjer nesten alltid sammen med en dusj eller en dotur. De to er da matematisk
uskillelige — summen kan læres, fordelingen mellom dem ikke. Håndvask holdes derfor nær
startgjetningen med ekstra prior-vekt, og dotur tar opp resten. Har du korte badbesøk uten
dusj, blir begge identifiserbare og treffer bedre.

Testet mot syntetiske timer med kjente literpriser: dusj, oppvask og hvitevarer læres
innenfor 1–8 %, og modellen treffer målingene med et typisk avvik på under 5 % av en
vanlig time.

## Flere anlegg

Hvert anlegg er sin egen oppføring med egne sensorer og egen læring, så hytta kan settes
opp ved siden av huset. Samme måler kan ikke brukes to ganger.
