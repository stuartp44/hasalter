from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    async_add_entities([
        SalterDisconnectButton(coordinator, name),
        SalterClearAlarmButton(coordinator, name, 1),
        SalterClearAlarmButton(coordinator, name, 2),
    ])


class SalterDisconnectButton(ButtonEntity):
    def __init__(self, coordinator, name: str):
        self._coordinator = coordinator
        self._name = name
        self._attr_name = f"{name} Disconnect"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_disconnect"
        self._attr_icon = "mdi:bluetooth-off"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator._address)},
            "name": self._name,
            "manufacturer": "Salter",
            "model": "Cook",
            "sw_version": self._coordinator._firmware_version,
            "hw_version": self._coordinator._hardware_version,
            "serial_number": self._coordinator._serial_number,
            "connections": {(dr.CONNECTION_BLUETOOTH, self._coordinator._address)},
        }

    async def async_press(self):
        _LOGGER.info("Disconnect button pressed")
        await self._coordinator.disconnect()


class SalterClearAlarmButton(ButtonEntity):
    def __init__(self, coordinator, name: str, probe_num: int):
        self._coordinator = coordinator
        self._probe_num = probe_num
        self._name = name
        probe_name = "Left Probe" if probe_num == 1 else "Right Probe"
        self._attr_name = f"{name} {probe_name} Clear Alarm"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_clear_alarm_{probe_num}"
        self._attr_icon = "mdi:alarm-off"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator._address)},
            "name": self._name,
            "manufacturer": "Salter",
            "model": "Cook",
            "sw_version": self._coordinator._firmware_version,
            "hw_version": self._coordinator._hardware_version,
            "serial_number": self._coordinator._serial_number,
            "connections": {(dr.CONNECTION_BLUETOOTH, self._coordinator._address)},
        }

    async def async_press(self):
        _LOGGER.info("Clear alarm button pressed for probe %d", self._probe_num)
        await self._coordinator.clear_alarm(self._probe_num)
