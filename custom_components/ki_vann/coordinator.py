"""Modellen bak KI Vann.

Med én måling per time kan ingenting skille dusj fra oppvask i sanntid. Det som *kan*
gjøres, er å lære hvor mange liter hver hendelsestype koster, og deretter fordele den
faktisk målte timen etter det.

Slik gjøres det:

1. **Hendelser telles.** Bevegelses- og nærværssensorene gjøres om til opphold: en
   sammenhengende periode med bevegelse, der et opphold i inntil `opphold_gap` minutter
   ikke avslutter det. Et langt opphold på badet er en dusj, et kort er håndvask, et
   opphold på doen er ett toalettbesøk pluss håndvask. Hvitevarer teller sykluser.

2. **Literprisen læres.** For hver time har vi et sett hendelsestall og et målt forbruk.
   Det gir et overbestemt likningssystem `A·w ≈ y` som løses med ikke-negativ minste
   kvadraters metode — projisert gradientnedstigning, som er noen få linjer og ikke
   trenger numpy. Startgjetningene virker som prior, så kategorier du nesten ikke bruker
   holder seg på et fornuftig tall i stedet for å bli dratt i grøfta av én rar time.

3. **Timen fordeles.** Estimatet per kategori er `w · hendelser`, og hele settet skaleres
   så summen blir nøyaktig det måleren viste. Da stemmer fordelingen alltid med
   virkeligheten, og feilen havner der den hører — i differansen, som legges på «basis og
   udefinert».

Det siste er viktig: modellen later ikke som den vet mer enn den gjør. Er summen av
hendelser langt fra det målte, vokser «basis og udefinert», og det er signalet om at noe
bruker vann uten at en sensor ser det.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BAD, CONF_DO, CONF_DUSJ_MIN, CONF_ENHET, CONF_HAGE, CONF_HAGE_LITER,
    CONF_KJOKKEN, CONF_LAERING, CONF_MAALER, CONF_OPPHOLD_GAP, CONF_OPPVASKMASKIN,
    CONF_PERSONER, CONF_TIME_SENSOR, CONF_VASKEMASKIN, CONF_VINDU_DAGER, DOMAIN,
    GRENSER, KATEGORIER, LAER_HVER_MIN, MAKS_RADER, PRIOR_EKSTRA, PRIOR_VEKT,
    START_LITER, STD,
)

_LOGGER = logging.getLogger(__name__)
SIGNAL = f"{DOMAIN}_oppdatert"

PAA = ("on", "home", "true", "detected", "open", "cleaning", "running", "active")

# Hvilke hendelser hver sone gir. Håndvask følger både dusj og toalettbesøk.
SONER = {
    CONF_BAD: "bad",
    CONF_DO: "do",
    CONF_KJOKKEN: "kjokken",
}


def nnls(A: list[list[float]], y: list[float], start: list[float],
         prior: list[float], prior_vekt: float | list[float],
         grenser: list[tuple[float, float]], runder: int = 60) -> list[float]:
    """Ikke-negativ minste kvadraters metode med prior, i ren Python.

    Minimerer `Σ(A·w − y)² + prior_vekt · Σ(w − prior)²` med hver `w` innenfor sine
    grenser.

    Løses med koordinatvis eksakt minimering: for én vekt av gangen regnes det nøyaktige
    minimumet ut mens de andre holdes fast, og resultatet klemmes innenfor grensene.
    Det er monotont — hver runde kan bare gjøre feilen mindre — og har ingen skrittlengde
    å bomme på. Første forsøk brukte gradientnedstigning, og der ble skrittet for langt
    når datasettet vokste: vektene oscillerte og endte på grenseverdiene sine.
    """
    n = len(start)
    if not A or n == 0:
        return list(start)
    w = list(start)
    m = len(A)

    vekt = prior_vekt if isinstance(prior_vekt, list) else [prior_vekt] * n
    # kolonnenes kvadratsummer trengs i hver runde, og endrer seg ikke
    kvad = [sum(A[i][j] * A[i][j] for i in range(m)) for j in range(n)]
    # gjeldende residual r = A·w − y
    r = [sum(A[i][j] * w[j] for j in range(n)) - y[i] for i in range(m)]

    for _ in range(runder):
        flyttet = 0.0
        for j in range(n):
            nevner = kvad[j] + vekt[j]
            if nevner <= 0:
                continue
            teller = sum(A[i][j] * r[i] for i in range(m)) + vekt[j] * (w[j] - prior[j])
            delta = -teller / nevner
            lo, hi = grenser[j]
            ny_verdi = min(hi, max(lo, w[j] + delta))
            delta = ny_verdi - w[j]
            if delta == 0.0:
                continue
            for i in range(m):
                if A[i][j]:
                    r[i] += A[i][j] * delta
            w[j] = ny_verdi
            flyttet = max(flyttet, abs(delta))
        if flyttet < 1e-4:
            break
    return w


class Opphold:
    """Et sammenhengende nærvær i én sone."""

    def __init__(self, start: datetime) -> None:
        self.start = start
        self.sist = start

    def minutter(self, til: datetime | None = None) -> float:
        return ((til or self.sist) - self.start).total_seconds() / 60.0


class VannMotor:
    """Teller hendelser, lærer literprisene og fordeler den målte timen."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self._av: list[Any] = []
        self._lager = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")

        self.vekter: dict[str, float] = dict(START_LITER)
        self.rader: list[dict[str, Any]] = []      # {time: iso, h: {kat: antall}, liter: x}
        self.timen: dict[str, float] = {k: 0.0 for k in KATEGORIER}
        self.i_dag: dict[str, float] = {k: 0.0 for k in KATEGORIER}
        self.dagens_dato: str = ""
        self.hendelser: dict[str, float] = {k: 0.0 for k in KATEGORIER}
        self.maalt_timen: float | None = None
        self.treff: float | None = None            # forklart andel, 0–1
        self.sist_laert: str | None = None

        self._opphold: dict[str, Opphold] = {}
        self._hvitevare_paa: dict[str, bool] = {}
        self._time_start_maaler: float | None = None
        self._time_start_hage: float | None = None

    # ------------------------------------------------------------------ oppsett
    @property
    def cfg(self) -> dict[str, Any]:
        return {**STD, **self.entry.data, **self.entry.options}

    async def start(self) -> None:
        lagret = await self._lager.async_load() or {}
        self.vekter = {**START_LITER, **(lagret.get("vekter") or {})}
        self.rader = lagret.get("rader") or []
        self.i_dag = {**{k: 0.0 for k in KATEGORIER}, **(lagret.get("i_dag") or {})}
        self.dagens_dato = lagret.get("dato") or dt_util.now().strftime("%Y-%m-%d")
        self.sist_laert = lagret.get("sist_laert")

        c = self.cfg
        fulgt = [c.get(x) for x in (CONF_BAD, CONF_DO, CONF_KJOKKEN,
                                    CONF_VASKEMASKIN, CONF_OPPVASKMASKIN, CONF_HAGE)]
        fulgt = [x for x in fulgt if x]
        if fulgt:
            self._av.append(async_track_state_change_event(self.hass, fulgt, self._endret))
        # sjekk opphold og klokke hvert minutt
        self._av.append(async_track_time_interval(self.hass, self._tikk, timedelta(minutes=1)))
        # timeskifte: les av måleren og fordel timen som gikk
        self._av.append(async_track_time_change(self.hass, self._timeskifte, minute=0, second=5))
        self._time_start_maaler = self._maaler_liter()
        self._time_start_hage = self._tall(c.get(CONF_HAGE_LITER))

    async def stopp(self) -> None:
        for av in self._av:
            av()
        self._av.clear()
        await self._lagre()

    async def _lagre(self) -> None:
        await self._lager.async_save({
            "vekter": self.vekter, "rader": self.rader[-MAKS_RADER:],
            "i_dag": self.i_dag, "dato": self.dagens_dato, "sist_laert": self.sist_laert,
        })

    def _varsle(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL)

    # -------------------------------------------------------------------- lesing
    def _tall(self, eid: str | None) -> float | None:
        st = self.hass.states.get(eid) if eid else None
        if not st or st.state in ("unknown", "unavailable", ""):
            return None
        try:
            return float(st.state)
        except ValueError:
            return None

    def _paa(self, eid: str | None) -> bool:
        st = self.hass.states.get(eid) if eid else None
        return bool(st and str(st.state).lower() in PAA)

    def _maaler_liter(self) -> float | None:
        """Måleren i liter, uansett om den står i m³ eller L."""
        c = self.cfg
        v = self._tall(c.get(CONF_MAALER))
        if v is None:
            return None
        return v * 1000.0 if c.get(CONF_ENHET, "m3") == "m3" else v

    def personer_hjemme(self) -> int:
        c = self.cfg
        return sum(1 for e in (c.get(CONF_PERSONER) or []) if self._paa(e))

    # ----------------------------------------------------------------- hendelser
    @callback
    def _endret(self, hendelse) -> None:
        self._les_soner(dt_util.now())
        self._les_hvitevarer()
        self._varsle()

    async def _tikk(self, _naa=None) -> None:
        naa = dt_util.now()
        self._les_soner(naa)
        self._les_hvitevarer()
        self._dagskifte(naa)
        if self.cfg.get(CONF_LAERING, True) and self._skal_laere(naa):
            self.laer()
            self.sist_laert = naa.isoformat()
            await self._lagre()
        self._varsle()

    def _skal_laere(self, naa: datetime) -> bool:
        if not self.sist_laert:
            return len(self.rader) >= 24
        try:
            sist = dt_util.parse_datetime(self.sist_laert)
        except (TypeError, ValueError):
            return True
        return sist is None or (naa - sist) >= timedelta(minutes=LAER_HVER_MIN)

    def _les_soner(self, naa: datetime) -> None:
        """Gjør nærvær om til opphold, og opphold om til hendelser når de avsluttes."""
        c = self.cfg
        gap = timedelta(minutes=float(c.get(CONF_OPPHOLD_GAP, 3)))
        dusj_min = float(c.get(CONF_DUSJ_MIN, 4))

        for nokkel, sone in SONER.items():
            eid = c.get(nokkel)
            if not eid:
                continue
            aktiv = self._paa(eid)
            o = self._opphold.get(sone)
            if aktiv:
                if o is None:
                    self._opphold[sone] = Opphold(naa)
                else:
                    o.sist = naa
                continue
            if o is None:
                continue
            if naa - o.sist < gap:
                continue          # kort pause – oppholdet er ikke over
            varighet = o.minutter()
            del self._opphold[sone]
            if sone == "bad":
                if varighet >= dusj_min:
                    self.hendelser["dusj"] += 1
                    self.hendelser["handvask"] += 1
                else:
                    self.hendelser["handvask"] += 1
            elif sone == "do":
                self.hendelser["do"] += 1
                self.hendelser["handvask"] += 1
            elif sone == "kjokken" and varighet >= 3:
                self.hendelser["oppvask_hand"] += 1

    def _les_hvitevarer(self) -> None:
        """Én syklus telles når maskinen går fra i gang til ferdig."""
        c = self.cfg
        for nokkel, kat in ((CONF_VASKEMASKIN, "vaskemaskin"),
                            (CONF_OPPVASKMASKIN, "oppvaskmaskin"),
                            (CONF_HAGE, "hage")):
            eid = c.get(nokkel)
            if not eid:
                continue
            naa = self._paa(eid)
            foer = self._hvitevare_paa.get(nokkel)
            if foer is None:
                self._hvitevare_paa[nokkel] = naa
                continue
            if foer and not naa:
                self.hendelser[kat] += 1
            self._hvitevare_paa[nokkel] = naa

    # -------------------------------------------------------------- timeskifte
    async def _timeskifte(self, _naa=None) -> None:
        """Les av måleren, fordel timen som gikk, og legg raden i historikken."""
        naa = dt_util.now()
        forrige = (naa - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        maalt = self._maalt_forrige_time()
        hendelser = {k: self.hendelser.get(k, 0.0) for k in KATEGORIER}
        hendelser["basis"] = 1.0                      # basis er per time, alltid med

        if maalt is not None:
            self.timen = self._fordel(hendelser, maalt)
            for k, v in self.timen.items():
                self.i_dag[k] = self.i_dag.get(k, 0.0) + v
            self.maalt_timen = maalt
            # Timer uten hendelser og uten forbruk lærer oss ingenting – de utvanner
            # bare datasettet. Vi lagrer timer med forbruk, eller med hendelser.
            if maalt > 0.05 or sum(v for k, v in hendelser.items() if k != "basis") > 0:
                self.rader.append({"time": forrige.isoformat(),
                                   "h": {k: v for k, v in hendelser.items() if v},
                                   "liter": maalt})
                self.rader = self.rader[-MAKS_RADER:]

        self.hendelser = {k: 0.0 for k in KATEGORIER}
        self._time_start_maaler = self._maaler_liter()
        self._time_start_hage = self._tall(self.cfg.get(CONF_HAGE_LITER))
        self._dagskifte(naa)
        await self._lagre()
        self._varsle()

    def _maalt_forrige_time(self) -> float | None:
        c = self.cfg
        if c.get(CONF_TIME_SENSOR):
            return self._tall(c.get(CONF_TIME_SENSOR))
        naa = self._maaler_liter()
        if naa is None or self._time_start_maaler is None:
            return None
        diff = naa - self._time_start_maaler
        return diff if diff >= 0 else None            # måleren nullstilt eller byttet

    def _dagskifte(self, naa: datetime) -> None:
        dato = naa.strftime("%Y-%m-%d")
        if dato != self.dagens_dato:
            self.dagens_dato = dato
            self.i_dag = {k: 0.0 for k in KATEGORIER}

    # -------------------------------------------------------------- fordelingen
    def _fordel(self, hendelser: dict[str, float], maalt: float) -> dict[str, float]:
        """Fordel `maalt` liter på kategoriene, skalert til å summere presist.

        Har vi en egen måler for utendørs, tas de literne ut først og fordeles ikke —
        de er målt, ikke estimert.
        """
        ut = {k: 0.0 for k in KATEGORIER}
        rest = maalt

        hage_maalt = None
        eid = self.cfg.get(CONF_HAGE_LITER)
        if eid and self._time_start_hage is not None:
            naa = self._tall(eid)
            if naa is not None and naa >= self._time_start_hage:
                hage_maalt = naa - self._time_start_hage
        if hage_maalt:
            ut["hage"] = min(hage_maalt, rest)
            rest -= ut["hage"]
            hendelser = {**hendelser, "hage": 0.0}

        anslag = {k: self.vekter.get(k, 0.0) * hendelser.get(k, 0.0) for k in KATEGORIER}
        sum_anslag = sum(anslag.values())

        if rest <= 0:
            self.treff = 1.0 if maalt <= 0 else (sum_anslag / maalt if maalt else None)
            return ut
        if sum_anslag <= 0:
            ut["basis"] += rest
            self.treff = 0.0
            return ut

        # Oppover begrenser vi til fem ganger anslaget – resten havner i «basis», som
        # er signalet om at noe brukte vann uten at en sensor så det. Nedover finnes
        # ingen grense: måleren har rett, og anslo hendelsene mer enn det som faktisk
        # rant, må de skaleres ned så summen stemmer. En nedre klemme her gjorde at
        # fordelingen kunne bli større enn det målte.
        skala = min(5.0, rest / sum_anslag)
        for k in KATEGORIER:
            ut[k] += anslag[k] * skala
        brukt = sum(v for k, v in ut.items() if k != "hage" or not hage_maalt)
        ut["basis"] += max(0.0, rest - brukt)
        self.treff = min(1.0, sum_anslag / rest)
        return ut

    # ---------------------------------------------------------------- læringen
    def laer(self) -> None:
        """Tren literprisene på historikken innenfor vinduet."""
        c = self.cfg
        dager = int(c.get(CONF_VINDU_DAGER, 60))
        grense = dt_util.now() - timedelta(days=dager)
        kat = [k for k in KATEGORIER if k != "hage" or not c.get(CONF_HAGE_LITER)]

        A: list[list[float]] = []
        y: list[float] = []
        for r in self.rader:
            t = dt_util.parse_datetime(r.get("time") or "")
            if t is None or t < grense:
                continue
            h = r.get("h") or {}
            rad = [float(h.get(k, 0.0)) for k in kat]
            if not any(rad):
                continue
            A.append(rad)
            y.append(float(r.get("liter") or 0.0))

        if len(A) < 24:
            return          # for lite å lære av; prioren gjelder

        start = [self.vekter.get(k, START_LITER[k]) for k in kat]
        prior = [START_LITER[k] for k in kat]
        grenser = [GRENSER[k] for k in kat]
        # prioren veies som om den var `PRIOR_VEKT` timer, så den blir mindre viktig
        # etter hvert som datasettet vokser
        basisvekt = PRIOR_VEKT * max(1.0, len(A) / 200.0)
        vekt = [basisvekt * PRIOR_EKSTRA.get(k, 1.0) for k in kat]
        ny = nnls(A, y, start, prior, vekt, grenser)
        for k, v in zip(kat, ny):
            self.vekter[k] = round(v, 2)

    # ------------------------------------------------------------------ ut til HA
    def forklart(self) -> float | None:
        """Hvor stor andel av det målte som hendelsene forklarer, i prosent."""
        return None if self.treff is None else round(self.treff * 100, 1)

    def rader_i_vindu(self) -> int:
        dager = int(self.cfg.get(CONF_VINDU_DAGER, 60))
        grense = dt_util.now() - timedelta(days=dager)
        n = 0
        for r in self.rader:
            t = dt_util.parse_datetime(r.get("time") or "")
            if t is not None and t >= grense:
                n += 1
        return n

    def avvik(self) -> float | None:
        """Typisk avvik mellom modell og måler, i liter per time (RMSE)."""
        c = self.cfg
        kat = [k for k in KATEGORIER if k != "hage" or not c.get(CONF_HAGE_LITER)]
        dager = int(c.get(CONF_VINDU_DAGER, 60))
        grense = dt_util.now() - timedelta(days=dager)
        sum2, n = 0.0, 0
        for r in self.rader:
            t = dt_util.parse_datetime(r.get("time") or "")
            if t is None or t < grense:
                continue
            h = r.get("h") or {}
            anslag = sum(self.vekter.get(k, 0.0) * float(h.get(k, 0.0)) for k in kat)
            sum2 += (anslag - float(r.get("liter") or 0.0)) ** 2
            n += 1
        return round((sum2 / n) ** 0.5, 1) if n else None

    async def nullstill_laering(self) -> None:
        self.vekter = dict(START_LITER)
        self.sist_laert = None
        await self._lagre()
        self._varsle()

    async def glem_historikk(self) -> None:
        self.rader = []
        self.sist_laert = None
        await self._lagre()
        self._varsle()

    async def sett_liter(self, kategori: str, liter: float) -> None:
        """Overstyr en literpris manuelt – nyttig når du vet tallet fra før."""
        if kategori not in KATEGORIER:
            raise ValueError(f"Ukjent kategori: {kategori}")
        lo, hi = GRENSER[kategori]
        self.vekter[kategori] = min(hi, max(lo, float(liter)))
        await self._lagre()
        self._varsle()
