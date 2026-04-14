from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_NAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    
    async_add_entities([
        SalterAlarmSetpoint(coordinator, name),
    ])


class SalterAlarmSetpoint(NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 0
    _attr_native_max_value = 250
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator, name: str):
        self._coordinator = coordinator
        self._attr_name = f"{name} Alarm Temperature"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_alarm"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator._address)},
            "name": name,
            "manufacturer": "Salter",
            "model": "Cook",
            "connections": {(dr.CONNECTION_BLUETOOTH, coordinator._address)},
        }

    @property
    def native_value(self):
        return self._coordinator._alarm_setpoint

    async def async_set_native_value(self, value: float):
        """Set the alarm temperature."""
        await self._coordinator.set_alarm_setpoint(int(value))

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()
