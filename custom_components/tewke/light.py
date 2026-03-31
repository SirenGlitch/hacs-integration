"""Light platform for the Tewke integration.

Maps the Tewke Tap smart switch to a Home Assistant ``LightEntity``.
"""
from __future__ import annotations

import logging
from typing import Any

from pytewke import CannotConnect

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_TAP, DOMAIN, ENTRY_COORDINATOR
from .coordinator import TewkeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tewke light entities from a config entry."""
    coordinator: TewkeCoordinator = hass.data[DOMAIN][entry.entry_id][ENTRY_COORDINATOR]

    entities = [
        TewkeTapLight(coordinator, device_id)
        for device_id, entry_data in coordinator.data.items()
        if entry_data["device"].device_type == DEVICE_TYPE_TAP
    ]
    async_add_entities(entities)


class TewkeTapLight(CoordinatorEntity[TewkeCoordinator], LightEntity):
    """Representation of a Tewke Tap smart switch as a light entity.

    All state is fetched via the coordinator so individual entities never
    communicate with the hub directly.  Commands (turn_on / turn_off) are
    sent directly through the pytewke client and the coordinator is then
    asked to refresh so that the new state is reflected immediately.
    """

    _attr_has_entity_name = True
    _attr_name = None  # The entity name is the device name itself

    def __init__(self, coordinator: TewkeCoordinator, device_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        device = coordinator.data[device_id]["device"]
        self._attr_unique_id = f"{device_id}_light"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device.name,
            manufacturer="Tewke",
            model=device.model,
            sw_version=device.sw_version,
            connections={("mac", device.mac)} if device.mac else set(),
        )

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    @property
    def _device_state(self) -> dict[str, Any]:
        return self.coordinator.data[self._device_id]["state"]

    @property
    def is_on(self) -> bool | None:
        """Return True when the switch is on."""
        return self._device_state.get("is_on")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            await self.coordinator.client.async_set_light_state(self._device_id, True)
        except CannotConnect:
            _LOGGER.error("Error turning on Tewke Tap %s", self._device_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self.coordinator.client.async_set_light_state(self._device_id, False)
        except CannotConnect:
            _LOGGER.error("Error turning off Tewke Tap %s", self._device_id)
        await self.coordinator.async_request_refresh()
