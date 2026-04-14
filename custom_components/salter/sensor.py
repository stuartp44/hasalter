from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
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


class SalterBleCoordinator:
    def __init__(self, hass: HomeAssistant, address: str):
        self.hass = hass
        self._address = address
        self._client = None
        self._ble_device = None
        self._cancel_poll = None
        self._reconnect_task = None
        self._temp1: float | None = None
        self._temp2: float | None = None
        self._alarm_setpoint1: int | None = None
        self._alarm_setpoint2: int | None = None
        self._callbacks = []
        self._should_connect = True
        self._manual_disconnect = False

    def register_callback(self, callback):
        self._callbacks.append(callback)

    async def start(self):
        self._reconnect_task = asyncio.create_task(self._maintain_connection())

    async def stop(self):
        self._should_connect = False
        if self._cancel_poll:
            self._cancel_poll()
            self._cancel_poll = None
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        await self._disconnect()

    async def disconnect(self):
        """Stop keep-alive polling and disconnect gracefully."""
        self._manual_disconnect = True
        
        if self._cancel_poll:
            self._cancel_poll()
            self._cancel_poll = None
            _LOGGER.info("Stopped keep-alive polling, device will sleep")
        
        if self._client and self._client.is_connected:
            await self._client.disconnect()
            _LOGGER.info("Disconnected from %s", self._address)

    async def set_alarm_setpoint(self, probe_num: int, temperature: int):
        """Set the temperature alarm setpoint for a specific probe."""
        if not self._client or not self._client.is_connected:
            _LOGGER.warning("Cannot set alarm: not connected to %s", self._address)
            return False
        
        try:
            # Command format: 09 03 0A [alarm1_high] [alarm1_low] [alarm2_high] [alarm2_low]
            # Both alarm values must be sent together
            # Temperature is sent as 16-bit big-endian value (multiplied by 10)
            if probe_num == 1:
                temp1_value = temperature * 10
                temp2_value = (self._alarm_setpoint2 or 100) * 10
            else:
                temp1_value = (self._alarm_setpoint1 or 100) * 10
                temp2_value = temperature * 10
            
            cmd = bytes([0x09, 0x03, 0x0A, 
                        (temp1_value >> 8) & 0xFF, temp1_value & 0xFF,
                        (temp2_value >> 8) & 0xFF, temp2_value & 0xFF])
            _LOGGER.debug("Sending SET ALARM command to %s: %s", self._address, cmd.hex())
            await self._client.write_gatt_char(FFE1_UUID, cmd, response=False)
            _LOGGER.info("Set alarm setpoints for %s: Probe 1=%d°C, Probe 2=%d°C", 
                        self._address, temp1_value // 10, temp2_value // 10)
            
            if probe_num == 1:
                self._alarm_setpoint1 = temperature
            else:
                self._alarm_setpoint2 = temperature
            
            for callback in self._callbacks:
                callback()
            return True
        except BleakError as e:
            _LOGGER.error("Failed to set alarm setpoint: %s", e)
            return False

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the device."""
        return self._client is not None and self._client.is_connected

    async def _maintain_connection(self):
        while self._should_connect:
            if self._manual_disconnect:
                _LOGGER.debug("Manual disconnect active, waiting for device to be turned back on")
                await asyncio.sleep(5)
                continue
            
            try:
                await self._connect_and_listen()
            except Exception as e:
                if self._should_connect:
                    _LOGGER.debug("Connection to %s lost: %s, will retry in 10s", self._address, e)
                    await asyncio.sleep(10)

    async def _connect_and_listen(self):
        self._ble_device = async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if not self._ble_device:
            _LOGGER.debug("Device %s not found (may be sleeping or off)", self._address)
            await asyncio.sleep(30)
            return

        if self._manual_disconnect:
            _LOGGER.info("Device %s detected, clearing manual disconnect", self._address)
            self._manual_disconnect = False

        _LOGGER.info("Connecting to %s", self._address)
        
        self._client = await establish_connection(
            client_class=BleakClient,
            device=self._ble_device,
            name=self._address,
            disconnected_callback=self._on_disconnect,
        )
        
        _LOGGER.info("Connected to %s", self._address)
        
        for callback in self._callbacks:
            callback()

        await self._client.start_notify(FFE1_UUID, self._handle_notification)
        _LOGGER.debug("Enabled notifications on FFE1")

        await self._client.write_gatt_char(FFE1_UUID, INIT_CMD, response=False)
        _LOGGER.debug("Sent INIT command to %s: %s", self._address, INIT_CMD.hex())

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
        
        for callback in self._callbacks:
            callback()

    async def _disconnect(self):
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        
        for callback in self._callbacks:
            callback()
    
    async def _send_poll(self, _):
        if self._client and self._client.is_connected:
            try:
                await self._client.write_gatt_char(FFE1_UUID, POLL_CMD, response=False)
                _LOGGER.debug("Sent POLL command to %s: %s", self._address, POLL_CMD.hex())
            except BleakError as e:
                _LOGGER.warning("Failed to send poll: %s", e)

    def _handle_notification(self, _handle, data: bytearray):
        _LOGGER.debug(
            "Received notification from %s: length=%d, hex=%s, bytes=%s",
            self._address,
            len(data),
            data.hex(),
            list(data)
        )
        
        if len(data) < 7:
            _LOGGER.debug("Data too short (length %d)", len(data))
            return
        
        if data[0] != 0x08:
            _LOGGER.debug("Unexpected message header: 0x%02x", data[0])
            return
        
        # INIT response (0x09) - contains configuration data (alarm setpoint, etc)
        if data[2] == 0x09:
            if len(data) >= 8:
                # Alarm setpoints are 16-bit big-endian values at bytes 4-5 and 6-7, divided by 10
                raw_alarm1 = (data[4] << 8) | data[5]
                raw_alarm2 = (data[6] << 8) | data[7]
                self._alarm_setpoint1 = raw_alarm1 // 10
                self._alarm_setpoint2 = raw_alarm2 // 10
                _LOGGER.debug("Parsed alarm setpoints from %s: Probe 1=%d°C (raw=%d), Probe 2=%d°C (raw=%d)", 
                             self._address, self._alarm_setpoint1, raw_alarm1, self._alarm_setpoint2, raw_alarm2)
                for callback in self._callbacks:
                    callback()
            else:
                _LOGGER.debug("INIT response too short")
            return
        
        # Temperature data (0x06)
        if data[2] != 0x06:
            _LOGGER.debug("Unexpected message type: 0x%02x", data[2])
            return

        raw1 = (data[3] << 8) | data[4]
        raw2 = (data[5] << 8) | data[6]
        self._temp1 = raw1 / 10.0
        self._temp2 = raw2 / 10.0

        _LOGGER.debug(
            "Parsed temps from %s: raw1=%d (%.1f°C), raw2=%d (%.1f°C)",
            self._address,
            raw1,
            self._temp1,
            raw2,
            self._temp2
        )

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
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator._address)},
            "name": name,
            "manufacturer": "Salter",
            "model": "Cook",
            "connections": {(dr.CONNECTION_BLUETOOTH, coordinator._address)},
        }

    @property
    def native_value(self):
        if self._probe_num == 1:
            temp = self._coordinator._temp1
        else:
            temp = self._coordinator._temp2
        
        if temp is not None and -20 <= temp <= 250:
            return round(temp, 1)
        return None

    async def async_added_to_hass(self):
        self._coordinator.register_callback(self._handle_update)

    def _handle_update(self):
        self.async_write_ha_state()
