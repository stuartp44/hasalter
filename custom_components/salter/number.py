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
        SalterAlarmSetpoint(coordinator, name, 1),
        SalterAlarmSetpoint(coordinator, name, 2),
    ])


class SalterAlarmSetpoint(NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 1
    _attr_native_max_value = 250
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator, name: str, probe_num: int):
        self._coordinator = coordinator
        self._probe_num = probe_num
        self._name = name
        probe_name = "Left Probe" if probe_num == 1 else "Right Probe"
        self._attr_name = f"{name} {probe_name} Alarm"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_alarm_{probe_num}"
    
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

    @property
    def native_value(self):
        if self._probe_num == 1:
            value = self._coordinator._alarm_setpoint1
        else:
            value = self._coordinator._alarm_setpoint2
        
        # Return None if alarm is cleared (value = 0)
        return value if value and value > 0 else None

    async def async_set_native_value(self, value: float):
        """Set the alarm temperature."""
        await self._coordinator.set_alarm_setpoint(self._probe_num, int(value))

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()
