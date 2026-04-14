from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_NAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    
    async_add_entities([
        SalterConnectionSensor(coordinator, name),
    ])


class SalterConnectionSensor(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, name: str):
        self._coordinator = coordinator
        self._attr_name = f"{name} Connection"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_connection"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator._address)},
            "name": name,
            "manufacturer": "Salter",
            "model": "Cook",
            "connections": {(dr.CONNECTION_BLUETOOTH, coordinator._address)},
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.is_connected

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()
