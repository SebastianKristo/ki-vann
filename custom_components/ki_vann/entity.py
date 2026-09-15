"""Felles base: alle sensorene hører til ett anlegg."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAVN
from .coordinator import SIGNAL, VannMotor


class VannEntitet(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, motor: VannMotor, nokkel: str, navn: str) -> None:
        self.motor = motor
        self._attr_unique_id = f"{motor.entry.entry_id}_{nokkel}"
        self._attr_name = navn
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, motor.entry.entry_id)},
            name=motor.entry.title or NAVN,
            manufacturer="KI",
            model="Vannfordeling",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL, self.async_write_ha_state))
