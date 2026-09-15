"""Oppsett: hvilke sensorer modellen trenger.

Bare vannmåleren er påkrevd. Alt annet gjør fordelingen bedre, men modellen fungerer
uten — den legger da mer i «basis og udefinert», som er det ærlige svaret.

Flere oppføringer er tillatt, så hytta kan settes opp ved siden av huset med sine egne
sensorer og sin egen læring.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BAD, CONF_DO, CONF_DUSJ_MIN, CONF_ENHET, CONF_HAGE, CONF_HAGE_LITER,
    CONF_KJOKKEN, CONF_LAERING, CONF_MAALER, CONF_OPPHOLD_GAP, CONF_OPPVASKMASKIN,
    CONF_PERSONER, CONF_TIME_SENSOR, CONF_VASKEMASKIN, CONF_VINDU_DAGER, DOMAIN, STD,
)

NAERVAER = ["binary_sensor", "input_boolean", "switch", "sensor"]


def _tall(min_: float, max_: float, steg: float, enhet: str):
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=min_, max=max_, step=steg, unit_of_measurement=enhet,
        mode=selector.NumberSelectorMode.BOX))


def _skjema(d: dict[str, Any]) -> vol.Schema:
    """Entitetsfeltene står uten `default`: en EntitySelector med tom streng avvises av
    cv.entity_id_or_uuid før steget kjører. Lagrede verdier legges inn som forslag."""
    return vol.Schema({
        vol.Required("navn", default=d.get("navn", "Hjemme")): str,

        # --- måleren
        vol.Required(CONF_MAALER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")),
        vol.Required(CONF_ENHET, default=d.get(CONF_ENHET, STD[CONF_ENHET])): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                selector.SelectOptionDict(value="m3", label="Kubikkmeter (m³)"),
                selector.SelectOptionDict(value="L", label="Liter")], mode="dropdown")),
        vol.Optional(CONF_TIME_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")),

        # --- soner
        vol.Optional(CONF_BAD): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=NAERVAER)),
        vol.Optional(CONF_DO): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=NAERVAER)),
        vol.Optional(CONF_KJOKKEN): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=NAERVAER)),

        # --- hvitevarer og utendørs
        vol.Optional(CONF_VASKEMASKIN): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=NAERVAER + ["binary_sensor"])),
        vol.Optional(CONF_OPPVASKMASKIN): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=NAERVAER + ["binary_sensor"])),
        vol.Optional(CONF_HAGE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "binary_sensor", "valve"])),
        vol.Optional(CONF_HAGE_LITER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")),

        # --- hvem som er hjemme
        vol.Optional(CONF_PERSONER): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["person", "device_tracker", "binary_sensor", "input_boolean"],
                multiple=True)),

        # --- innstillinger
        vol.Required(CONF_DUSJ_MIN, default=d.get(CONF_DUSJ_MIN, STD[CONF_DUSJ_MIN])): _tall(1, 20, 0.5, "min"),
        vol.Required(CONF_OPPHOLD_GAP, default=d.get(CONF_OPPHOLD_GAP, STD[CONF_OPPHOLD_GAP])): _tall(1, 15, 0.5, "min"),
        vol.Required(CONF_VINDU_DAGER, default=d.get(CONF_VINDU_DAGER, STD[CONF_VINDU_DAGER])): _tall(7, 180, 1, "dager"),
        vol.Required(CONF_LAERING, default=d.get(CONF_LAERING, STD[CONF_LAERING])): selector.BooleanSelector(),
    })


class KiVannFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        feil: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_MAALER):
                feil[CONF_MAALER] = "maaler_mangler"
            else:
                navn = user_input.pop("navn", "Hjemme")
                # Flere anlegg er tillatt – hytta ved siden av huset – men ikke samme
                # måler to ganger, for da ville de to lært av hverandres timer.
                await self.async_set_unique_id(user_input[CONF_MAALER])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=navn, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_skjema({}), user_input or {}),
            errors=feil)

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return KiVannOptions(entry)


class KiVannOptions(config_entries.OptionsFlow):
    def __init__(self, entry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            user_input.pop("navn", None)
            return self.async_create_entry(title="", data=user_input)
        d = {**self.entry.data, **self.entry.options, "navn": self.entry.title}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_skjema(d), d))
