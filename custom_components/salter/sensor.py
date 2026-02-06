from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothCallbackMatcher, BluetoothServiceInfoBleak
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_ADDRESS, CONF_NAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

def _decode_temp(service_info: BluetoothServiceInfoBleak) -> float | None:
    mfd = service_info.manufacturer_data
    if not mfd:
        _LOGGER.debug(
            "No manufacturer data from %s (%s)",
            service_info.name,
            service_info.address,
        )
        return None

    for _cid, payload in mfd.items():
        if not payload or len(payload) < 16:
            _LOGGER.debug(
                "Manufacturer data too short from %s (%s): %s",
                service_info.name,
                service_info.address,
                payload,
            )
            continue

        if payload[0:3] != b"\x01\x01\x01":
            _LOGGER.debug(
                "Manufacturer data header mismatch from %s (%s): %s",
                service_info.name,
                service_info.address,
                payload,
            )
            continue

        raw = payload[13] | (payload[14] << 8)
        _LOGGER.debug(
            "Decoded temperature from %s (%s): raw=%s temp=%.1f",
            service_info.name,
            service_info.address,
            raw,
            raw / 10.0,
        )
        return raw / 10.0

    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    address = entry.data[CONF_ADDRESS].upper()
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([SalterBleTempSensor(hass, address, name)], update_before_add=False)


class SalterBleTempSensor(SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, address: str, name: str):
        self.hass = hass
        self._address = address
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{address.replace(':','')}_temp"
        self._temp = None
        self._unsub = None

    @property
    def native_value(self):
        return self._temp

    async def async_added_to_hass(self):
        matcher = BluetoothCallbackMatcher(address=self._address)

        def _cb(service_info: BluetoothServiceInfoBleak, change):
            _LOGGER.debug(
                "Advert received from %s (%s) rssi=%s",
                service_info.name,
                service_info.address,
                service_info.rssi,
            )
            temp = _decode_temp(service_info)
            if temp is None:
                _LOGGER.debug(
                    "No valid temperature decoded from %s (%s)",
                    service_info.name,
                    service_info.address,
                )
                return
            if temp < -50 or temp > 100:
                _LOGGER.debug(
                    "Discarding out-of-range temperature from %s (%s): %.1f",
                    service_info.name,
                    service_info.address,
                    temp,
                )
                return

            self._temp = round(temp, 1)
            self.async_write_ha_state()

        self._unsub = bluetooth.async_register_callback(
            self.hass,
            _cb,
            matcher,
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

        _LOGGER.info("Listening for Salter BLE adverts from %s", self._address)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()
            self._unsub = None
