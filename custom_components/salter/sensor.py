from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection

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
    
    coordinator = SalterBleCoordinator(hass, address, entry.entry_id)
    
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    async_add_entities([
        SalterBleTempSensor(coordinator, name, 1),
        SalterBleTempSensor(coordinator, name, 2),
    ], update_before_add=False)
    
    await coordinator.start()


class SalterBleCoordinator:
    def __init__(self, hass: HomeAssistant, address: str, entry_id: str):
        self.hass = hass
        self._address = address
        self._entry_id = entry_id
        self._client = None
        self._ble_device = None
        self._cancel_poll = None
        self._reconnect_task = None
        self._temp1: float | None = None
        self._temp2: float | None = None
        self._alarm_setpoint1: int | None = None
        self._alarm_setpoint2: int | None = None
        self._firmware_version: str | None = None
        self._serial_number: str | None = None
        self._hardware_version: str | None = None
        self._callbacks = []
        self._should_connect = True
        self._manual_disconnect = False
        self._powering_off = False

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
        """Set the temperature alarm setpoint for a specific probe.
        
        Protocol discovered from BLE log analysis:
        Command format: 09 08 02 03 YY YY ZZ ZZ (8 bytes - sets BOTH probes)
        
        Header: 09 08 02 03 (constant)
        Bytes 4-5: Probe 1 temperature × 10 (16-bit big-endian)
        Bytes 6-7: Probe 2 temperature × 10 (16-bit big-endian)
        
        Examples:
        - Probe1=65°C, Probe2=100°C: 09 08 02 03 02 8a 03 e8
        - Probe1=65°C, Probe2=60°C:  09 08 02 03 02 8a 02 58
        """
        if not self._client or not self._client.is_connected:
            _LOGGER.warning("Cannot set alarm: not connected to %s", self._address)
            return False
        
        try:
            # Update the requested probe's setpoint
            if probe_num == 1:
                temp1 = temperature
                temp2 = self._alarm_setpoint2 if self._alarm_setpoint2 else 100
            else:
                temp1 = self._alarm_setpoint1 if self._alarm_setpoint1 else 100
                temp2 = temperature
            
            # Encode both temperatures as 16-bit values (temp × 10)
            temp1_value = int(temp1 * 10)
            temp2_value = int(temp2 * 10)
            
            # Build 8-byte command
            # Header: 09 08 02 03
            # Probe 1: 16-bit big-endian
            # Probe 2: 16-bit big-endian
            cmd = bytes([
                0x09, 0x08, 0x02, 0x03,
                (temp1_value >> 8) & 0xFF, temp1_value & 0xFF,
                (temp2_value >> 8) & 0xFF, temp2_value & 0xFF
            ])
            
            _LOGGER.debug("Setting alarm setpoints: Probe 1=%d°C, Probe 2=%d°C", temp1, temp2)
            _LOGGER.debug("Command: %s", cmd.hex())
            
            await self._client.write_gatt_char(FFE1_UUID, cmd, response=False)
            
            _LOGGER.info("Set alarm setpoints for %s: Probe 1=%d°C, Probe 2=%d°C", 
                        self._address, temp1, temp2)
            
            # Update local state
            self._alarm_setpoint1 = temp1
            self._alarm_setpoint2 = temp2
            
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
            self._powering_off = False

        _LOGGER.info("Connecting to %s", self._address)
        
        self._client = await establish_connection(
            client_class=BleakClient,
            device=self._ble_device,
            name=self._address,
            disconnected_callback=self._on_disconnect,
        )
        
        _LOGGER.info("Connected to %s", self._address)
        
        # Read firmware version from Device Information Service (0x2A26)
        try:
            fw_bytes = await self._client.read_gatt_char("00002a26-0000-1000-8000-00805f9b34fb")
            self._firmware_version = fw_bytes.decode('utf-8', errors='ignore').strip()
            _LOGGER.debug("Read firmware version from %s: %s", self._address, self._firmware_version)
        except Exception as e:
            _LOGGER.debug("Could not read firmware version: %s", e)
            self._firmware_version = None
        
        # Read serial number from Device Information Service (0x2A25)
        try:
            sn_bytes = await self._client.read_gatt_char("00002a25-0000-1000-8000-00805f9b34fb")
            sn = sn_bytes.decode('utf-8', errors='ignore').strip()
            # Ignore placeholder value
            if sn and sn.lower() != "serial number":
                self._serial_number = sn
                _LOGGER.debug("Read serial number from %s: %s", self._address, self._serial_number)
            else:
                self._serial_number = None
        except Exception as e:
            _LOGGER.debug("Could not read serial number: %s", e)
            self._serial_number = None
        
        # Read hardware revision from Device Information Service (0x2A27)
        try:
            hw_bytes = await self._client.read_gatt_char("00002a27-0000-1000-8000-00805f9b34fb")
            self._hardware_version = hw_bytes.decode('utf-8', errors='ignore').strip()
            _LOGGER.debug("Read hardware version from %s: %s", self._address, self._hardware_version)
        except Exception as e:
            _LOGGER.debug("Could not read hardware version: %s", e)
            self._hardware_version = None
        
        # Update device registry with the read information
        if self._firmware_version or self._serial_number or self._hardware_version:
            device_registry = dr.async_get(self.hass)
            device_registry.async_get_or_create(
                config_entry_id=self._entry_id,
                identifiers={(DOMAIN, self._address)},
                manufacturer="Salter",
                model="Cook",
                sw_version=self._firmware_version,
                hw_version=self._hardware_version,
                serial_number=self._serial_number,
                connections={(dr.CONNECTION_BLUETOOTH, self._address)},
            )
        
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
        # Don't poll if device is powering off
        if self._powering_off:
            return
            
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
        
        # Power off notification (0xaf) - device is shutting down
        if data[2] == 0xaf:
            if not self._powering_off:  # Only process first power-off notification
                _LOGGER.info("Device %s is powering off (received shutdown notification)", self._address)
                self._powering_off = True
                self._manual_disconnect = True
                
                # Stop polling immediately
                if self._cancel_poll:
                    self._cancel_poll()
                    self._cancel_poll = None
                    _LOGGER.debug("Stopped keep-alive polling due to power off")
            # Disconnect will happen naturally when device shuts down
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
        self._name = name
        probe_name = "Left Probe" if probe_num == 1 else "Right Probe"
        self._attr_name = f"{name} {probe_name}"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_temp{probe_num}"
    
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
