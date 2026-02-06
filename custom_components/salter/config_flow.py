from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig
import voluptuous as vol

from .const import DOMAIN, CONF_ADDRESS, CONF_NAME, DEFAULT_NAME

def _looks_like_salter(service_info: BluetoothServiceInfoBleak) -> bool:
    mfd = service_info.manufacturer_data
    if not mfd:
        return False

    addr = (service_info.address or "").replace(":", "").lower()

    for _cid, payload in mfd.items():
        if not payload or len(payload) < 16:
            continue

        if payload[0:3] != b"\x01\x01\x01":
            continue

        if len(addr) == 12:
            rev_mac = bytes.fromhex("".join([addr[i:i+2] for i in range(10, -2, -2)]))
            if payload[4:10] != rev_mac:
                continue

        return True

    return False


class SalterBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak):
        if not _looks_like_salter(discovery_info):
            return self.async_abort(reason="not_supported")

        address = discovery_info.address.upper()
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
