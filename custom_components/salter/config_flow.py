from __future__ import annotations

import logging

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig
import voluptuous as vol

from .const import DOMAIN, CONF_ADDRESS, CONF_NAME, DEFAULT_NAME

def _looks_like_salter(service_info: BluetoothServiceInfoBleak) -> bool:
    name = (service_info.name or "").upper()
    if name.startswith("SALTER-BKT"):
        _LOGGER.debug(
            "Matched Salter device by name: %s (%s)",
            service_info.name,
            service_info.address,
        )
        return True

    mfd = service_info.manufacturer_data
    if not mfd:
        _LOGGER.debug(
            "No manufacturer data for %s (%s)",
            service_info.name,
            service_info.address,
        )
        return False

    addr = (service_info.address or "").replace(":", "").lower()

    for _cid, payload in mfd.items():
        if not payload or len(payload) < 16:
            _LOGGER.debug(
                "Manufacturer data too short for %s (%s): %s",
                service_info.name,
                service_info.address,
                payload,
            )
            continue

        if payload[0:3] != b"\x01\x01\x01":
            _LOGGER.debug(
                "Manufacturer data header mismatch for %s (%s): %s",
                service_info.name,
                service_info.address,
                payload,
            )
            continue

        if len(addr) == 12:
            rev_mac = bytes.fromhex("".join([addr[i:i+2] for i in range(10, -2, -2)]))
            if payload[4:10] != rev_mac:
                _LOGGER.debug(
                    "Manufacturer data MAC mismatch for %s (%s)",
                    service_info.name,
                    service_info.address,
                )
                continue

        return True

    return False


class SalterBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak):
        if not _looks_like_salter(discovery_info):
            _LOGGER.debug(
                "Bluetooth discovery ignored for %s (%s)",
                discovery_info.name,
                discovery_info.address,
            )
            return self.async_abort(reason="not_supported")

        address = discovery_info.address.upper()
        _LOGGER.debug(
            "Bluetooth discovery accepted for %s (%s)",
            discovery_info.name,
            address,
        )
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        name = discovery_info.name or DEFAULT_NAME
        self.context["title_placeholders"] = {"name": name}

        return await self.async_step_user(
            {"address": address, "name": name}
        )

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", DEFAULT_NAME),
                data={
                    CONF_ADDRESS: user_input[CONF_ADDRESS],
                    CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): TextSelector(TextSelectorConfig()),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): TextSelector(TextSelectorConfig()),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
