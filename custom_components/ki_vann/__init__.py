"""KI Vann – hva går vannet til?"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, KATEGORIER
from .coordinator import VannMotor

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    motor = VannMotor(hass, entry)
    await motor.start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = motor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_oppdatert))
    _tjenester(hass)
    return True


async def _oppdatert(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await hass.data[DOMAIN].pop(entry.entry_id).stopp()
        if not hass.data[DOMAIN]:
            for t in ("lær_na", "nullstill_laering", "glem_historikk", "sett_liter"):
                hass.services.async_remove(DOMAIN, t)
    return ok


def _tjenester(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "lær_na"):
        return

    def motorer(kall: ServiceCall):
        alle = list(hass.data.get(DOMAIN, {}).values())
        navn = kall.data.get("anlegg")
        if not navn:
            return alle
        return [m for m in alle if navn.lower() in str(m.entry.title or "").lower()]

    async def laer(kall: ServiceCall) -> None:
        """Tren modellen med én gang i stedet for å vente på neste time."""
        for m in motorer(kall):
            m.laer()
            m.sist_laert = None
            await m._lagre()
            m._varsle()

    async def nullstill(kall: ServiceCall) -> None:
        """Sett literprisene tilbake til startgjetningene. Historikken beholdes."""
        for m in motorer(kall):
            await m.nullstill_laering()

    async def glem(kall: ServiceCall) -> None:
        """Kast all lært historikk. Brukes hvis noe har vært galt satt opp en stund."""
        for m in motorer(kall):
            await m.glem_historikk()

    async def sett(kall: ServiceCall) -> None:
        """Overstyr én literpris. Modellen lærer videre fra den verdien."""
        for m in motorer(kall):
            await m.sett_liter(kall.data["kategori"], kall.data["liter"])

    anlegg = {vol.Optional("anlegg"): str}
    hass.services.async_register(DOMAIN, "lær_na", laer, schema=vol.Schema(anlegg))
    hass.services.async_register(DOMAIN, "nullstill_laering", nullstill, schema=vol.Schema(anlegg))
    hass.services.async_register(DOMAIN, "glem_historikk", glem, schema=vol.Schema(anlegg))
    hass.services.async_register(DOMAIN, "sett_liter", sett, schema=vol.Schema({
        **anlegg,
        vol.Required("kategori"): vol.In(list(KATEGORIER)),
        vol.Required("liter"): vol.Coerce(float),
    }))
