from __future__ import annotations

import logging

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .const import DOMAIN, CONF_ADDRESS, CONF_NAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


class SalterBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        
        # Log advertisement data to find firmware version
        _LOGGER.debug("Discovery info for %s: name=%s, local_name=%s, manufacturer_data=%s, service_data=%s",
                     discovery_info.address, discovery_info.name, 
                     getattr(discovery_info, 'local_name', None),
                     discovery_info.manufacturer_data,
                     getattr(discovery_info, 'service_data', {}))
        
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None
        discovery_info = self._discovery_info

        if user_input is not None:
            return self.async_create_entry(
                title=DEFAULT_NAME,
                data={
                    CONF_ADDRESS: discovery_info.address,
                    CONF_NAME: DEFAULT_NAME,
                },
            )

        self._set_confirm_only()
        placeholders = {
            "name": DEFAULT_NAME,
            "address": discovery_info.address,
        }
        self.context["title_placeholders"] = placeholders
        
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders,
        )

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                },
            )

        # Show discovered devices
        discovered = async_discovered_service_info(self.hass)
        salter_devices = [
            info for info in discovered
            if info.name and info.name.startswith("SALTER-BKT")
        ]

        if salter_devices:
            schema = vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {info.address: f"{info.name} ({info.address})" 
                         for info in salter_devices}
                    ),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            )

        return self.async_show_form(step_id="user", data_schema=schema)
