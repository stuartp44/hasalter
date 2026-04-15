from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    async_add_entities([
        SalterConnectionSensor(coordinator, name),
        SalterAlarmSensor(coordinator, name, 1),
        SalterAlarmSensor(coordinator, name, 2),
    ])


class SalterConnectionSensor(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, name: str):
        self._coordinator = coordinator
        self._name = name
        self._attr_name = f"{name} Connection"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_connection"

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
    def is_on(self) -> bool:
        return self._coordinator.is_connected

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()


class SalterAlarmSensor(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator, name: str, probe_num: int):
        self._coordinator = coordinator
        self._probe_num = probe_num
        self._name = name
        probe_name = "Left Probe" if probe_num == 1 else "Right Probe"
        self._attr_name = f"{name} {probe_name} Alarm Active"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_alarm_active_{probe_num}"

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
    def is_on(self) -> bool:
        """Return True if temperature exceeds alarm threshold."""
        if self._probe_num == 1:
            temp = self._coordinator._temp1
            alarm = self._coordinator._alarm_setpoint1
        else:
            temp = self._coordinator._temp2
            alarm = self._coordinator._alarm_setpoint2

        # Alarm is active if setpoint > 0 and temperature >= setpoint
        if alarm and alarm > 0 and temp is not None:
            return temp >= alarm
        return False

    @property
    def available(self) -> bool:
        """Entity is always available, shows off when alarm not set."""
        return True

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()
