from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak import BleakError
from bleak.backends.device import BLEDevice

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
)
from homeassistant.components.bluetooth.api import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, CONF_ADDRESS, CONF_NAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

FFE1_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
INIT_CMD = bytes([0x09, 0x03, 0x09])
POLL_CMD = bytes([0x09, 0x03, 0x06])
POLL_INTERVAL = timedelta(seconds=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    address = entry.data[CONF_ADDRESS].upper()
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    
    coordinator = SalterBleCoordinator(hass, address)
    
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    async_add_entities([
        SalterBleTempSensor(coordinator, name, 1),
        SalterBleTempSensor(coordinator, name, 2),
    ], update_before_add=False)
    
    await coordinator.start()
    return True


class SalterBleCoordinator:
    def __init__(self, hass: HomeAssistant, address: str):
        self.hass = hass
        self._address = address
        self._client = None
        self._ble_device: BLEDevice | None = None
        self._cancel_poll = None
        self._reconnect_task = None
        self._temp1: float | None = None
        self._temp2: float | None = None
        self._callbacks = []

    def register_callback(self, callback):
        self._callbacks.append(callback)

    async def start(self):
        self._reconnect_task = asyncio.create_task(self._maintain_connection())

    async def stop(self):
        if self._cancel_poll:
            self._cancel_poll()
            self._cancel_poll = None
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        await self._disconnect()

    async def _maintain_connection(self):
        while True:
            try:
                await self._connect_and_listen()
            except Exception as e:
                _LOGGER.warning("Connection to %s lost: %s, reconnecting in 10s", self._address, e)
                await asyncio.sleep(10)

    async def _connect_and_listen(self):
        self._ble_device = async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if not self._ble_device:
            _LOGGER.error("Device %s not found", self._address)
            await asyncio.sleep(30)
            return

        _LOGGER.info("Connecting to %s", self._address)
        
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            self._ble_device,
            self._address,
            self._on_disconnect,
        )
        
        _LOGGER.info("Connected to %s", self._address)

        await self._client.start_notify(FFE1_UUID, self._handle_notification)
        _LOGGER.debug("Enabled notifications on FFE1")

        await self._client.write_gatt_char(FFE1_UUID, INIT_CMD, response=False)
        _LOGGER.debug("Sent INIT command")

        self._cancel_poll = async_track_time_interval(
            self.hass,
            self._send_poll,
            POLL_INTERVAL,
        )

        while self._client and self._client.is_connected:
            await asyncio.sleep(1)

    def _on_disconnect(self, client):
        _LOGGER.debug("Disconnected from %s", self._address)
        if self._cancel_poll:
            self._cancel_poll()
            self._cancel_poll = None

    async def _disconnect(self):
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    async def _send_poll(self, _):
        if self._client and self._client.is_connected:
            try:
                await self._client.write_gatt_char(FFE1_UUID, POLL_CMD, response=False)
                _LOGGER.debug("Sent POLL command")
            except BleakError as e:
                _LOGGER.warning("Failed to send poll: %s", e)

    def _handle_notification(self, _handle, data: bytearray):
        if len(data) < 7:
            return
        if data[0] != 0x08 or data[2] != 0x06:
            _LOGGER.debug("Unexpected notification format: %s", data.hex())
            return

        raw1 = (data[3] << 8) | data[4]
        raw2 = (data[5] << 8) | data[6]
        self._temp1 = raw1 / 10.0
        self._temp2 = raw2 / 10.0

        _LOGGER.debug("Received temps: %.1f°C, %.1f°C", self._temp1, self._temp2)

        for callback in self._callbacks:
            callback()


class SalterBleTempSensor(SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"
    _attr_should_poll = False

    def __init__(self, coordinator: SalterBleCoordinator, name: str, probe_num: int):
        self._coordinator = coordinator
        self._probe_num = probe_num
        self._attr_name = f"{name} Probe {probe_num}"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_temp{probe_num}"

    @property
    def native_value(self):
        if self._probe_num == 1:
            temp = self._coordinator._temp1
        else:
            temp = self._coordinator._temp2
        
        if temp is not None and -50 <= temp <= 100:
            return round(temp, 1)
        return None

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()
