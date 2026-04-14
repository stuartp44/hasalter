from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_NAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    
    async_add_entities([
        SalterDisconnectButton(coordinator, name),
    ])


class SalterDisconnectButton(ButtonEntity):
    def __init__(self, coordinator, name: str):
        self._coordinator = coordinator
        self._attr_name = f"{name} Disconnect"
        self._attr_unique_id = f"{DOMAIN}_{coordinator._address.replace(':','')}_disconnect"
        self._attr_icon = "mdi:bluetooth-off"

    async def async_press(self):
        _LOGGER.info("Disconnect button pressed")
        await self._coordinator.disconnect()
