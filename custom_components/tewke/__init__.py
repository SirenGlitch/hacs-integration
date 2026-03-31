"""The Tewke integration."""
from __future__ import annotations

import logging

from pytewke import CannotConnect, TewkeClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, ENTRY_COORDINATOR
from .coordinator import TewkeCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tewke from a config entry.

    Creates a :class:`TewkeCoordinator`, performs the first data refresh, and
    then forwards setup to all platforms (light, sensor).
    """
    host: str = entry.data[CONF_HOST]
    api_key: str = entry.data.get(CONF_API_KEY, "")

    client = TewkeClient(host=host, api_key=api_key or None)

    try:
        await client.async_authenticate()
    except CannotConnect as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to Tewke hub at {host}"
        ) from err

    coordinator = TewkeCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        ENTRY_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Tewke config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
