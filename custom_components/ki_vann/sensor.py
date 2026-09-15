"""Sensorene: liter per kategori i dag og forrige time, pluss modellens status."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import CURRENCY_EURO  # noqa: F401  (ikke i bruk, men holder importen stabil)

from .const import (
    CONF_PRIS, DOMAIN, KATEGORI_IKON, KATEGORI_NAVN, KATEGORIER, START_LITER, STD,
)
from .entity import VannEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            legg_til: AddEntitiesCallback) -> None:
    m = hass.data[DOMAIN][entry.entry_id]
    ut: list[SensorEntity] = [Modell(m), Forklart(m), Storste(m), Totalt(m), Kostnad(m)]
    for k in KATEGORIER:
        ut.append(Kategori(m, k, "i_dag"))
        ut.append(Kategori(m, k, "timen"))
    legg_til(ut)


class Kategori(VannEntitet, SensorEntity):
    _attr_native_unit_of_measurement = "L"
    _attr_suggested_display_precision = 0

    def __init__(self, motor, kat: str, periode: str) -> None:
        etikett = KATEGORI_NAVN[kat]
        super().__init__(motor, f"{kat}_{periode}",
                         f"{etikett} {'i dag' if periode == 'i_dag' else 'forrige time'}")
        self.kat = kat
        self.periode = periode
        self._attr_icon = KATEGORI_IKON[kat]
        self._attr_state_class = (SensorStateClass.TOTAL_INCREASING if periode == "i_dag"
                                  else SensorStateClass.MEASUREMENT)

    @property
    def native_value(self):
        kilde = self.motor.i_dag if self.periode == "i_dag" else self.motor.timen
        v = kilde.get(self.kat)
        return None if v is None else round(v, 1)

    @property
    def extra_state_attributes(self) -> dict:
        d = {
            "liter_per_hendelse": self.motor.vekter.get(self.kat),
            "startgjetning": START_LITER.get(self.kat),
        }
        if self.periode == "i_dag":
            sum_dag = sum(self.motor.i_dag.values())
            d["andel_prosent"] = (round(self.motor.i_dag.get(self.kat, 0) / sum_dag * 100, 1)
                                  if sum_dag > 0 else None)
        else:
            d["hendelser_timen"] = self.motor.hendelser.get(self.kat)
        return d


class Totalt(VannEntitet, SensorEntity):
    """Alt vann i dag, summen av kategoriene."""

    _attr_native_unit_of_measurement = "L"
    _attr_suggested_display_precision = 0
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water"

    def __init__(self, motor) -> None:
        super().__init__(motor, "totalt", "Vann i dag")

    @property
    def native_value(self):
        return round(sum(self.motor.i_dag.values()), 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {"per_person": (round(sum(self.motor.i_dag.values())
                                     / max(1, self.motor.personer_hjemme()), 1))}


class Kostnad(VannEntitet, SensorEntity):
    """Hva vannet koster i dag, med prisen for vann og avløp samlet."""

    _attr_native_unit_of_measurement = "kr"
    _attr_suggested_display_precision = 1
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    def __init__(self, motor) -> None:
        super().__init__(motor, "kostnad", "Vannkostnad i dag")

    def _pris(self) -> float:
        return float(self.motor.cfg.get(CONF_PRIS, STD[CONF_PRIS]) or 0)

    @property
    def native_value(self):
        return round(sum(self.motor.i_dag.values()) / 1000.0 * self._pris(), 2)

    @property
    def extra_state_attributes(self) -> dict:
        p = self._pris()
        return {"kr_per_m3": p,
                **{KATEGORI_NAVN[k]: round(v / 1000.0 * p, 2)
                   for k, v in self.motor.i_dag.items() if v > 0}}


class Modell(VannEntitet, SensorEntity):
    """Statusen til læringen: hvor mye den har å gå på, og hvor godt den treffer."""

    _attr_icon = "mdi:brain"

    def __init__(self, motor) -> None:
        super().__init__(motor, "modell", "Modell")

    @property
    def native_value(self):
        n = self.motor.rader_i_vindu()
        if n < 24:
            return "Samler data"
        if n < 168:
            return "Lærer"
        return "Innlært"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "timer_i_vindu": self.motor.rader_i_vindu(),
            "avvik_liter_per_time": self.motor.avvik(),
            "sist_laert": self.motor.sist_laert,
            "personer_hjemme": self.motor.personer_hjemme(),
            **{f"liter_{k}": self.motor.vekter.get(k) for k in KATEGORIER},
        }


class Forklart(VannEntitet, SensorEntity):
    """Hvor stor andel av forrige time hendelsene faktisk forklarer."""

    _attr_native_unit_of_measurement = "%"
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:help-circle-outline"

    def __init__(self, motor) -> None:
        super().__init__(motor, "forklart", "Forklart av sensorene")

    @property
    def native_value(self):
        return self.motor.forklart()

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "malt_forrige_time": (None if self.motor.maalt_timen is None
                                  else round(self.motor.maalt_timen, 1)),
            "forklaring": "Under 100 % betyr at det gikk vann uten at noen sensor så "
                          "hvorfor. Skjer det om natten uten at noen er hjemme, er "
                          "lekkasje verdt å sjekke.",
        }


class Storste(VannEntitet, SensorEntity):
    """Hva vannet stort sett går til i dag — den enkleste nyttige sensoren."""

    _attr_icon = "mdi:water-percent"

    def __init__(self, motor) -> None:
        super().__init__(motor, "storste", "Største forbruker i dag")

    @property
    def native_value(self):
        d = {k: v for k, v in self.motor.i_dag.items() if v > 0}
        if not d:
            return None
        return KATEGORI_NAVN[max(d, key=d.get)]

    @property
    def extra_state_attributes(self) -> dict:
        sum_dag = sum(self.motor.i_dag.values())
        return {
            "totalt_liter_i_dag": round(sum_dag, 1),
            **{KATEGORI_NAVN[k]: round(v, 1) for k, v in self.motor.i_dag.items() if v > 0},
        }
