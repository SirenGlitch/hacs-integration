"""DataUpdateCoordinator for the Tewke integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pytewke import CannotConnect, TewkeClient

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TewkeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching data from a Tewke hub.

    A single coordinator instance is created per config entry. All platforms
    (light, sensor, …) share the same coordinator so that the hub is polled
    exactly once per interval and every entity is updated simultaneously.
    """

    def __init__(self, hass: HomeAssistant, client: TewkeClient) -> None:
        """Initialize the coordinator."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest state from the Tewke hub.

        Returns a mapping of ``device_id -> device_state_dict``.
        Raises ``UpdateFailed`` on communication errors so that HA can mark
        entities as unavailable and retry on the next poll.
        """
        try:
            devices = await self.client.async_get_devices()
            data: dict[str, Any] = {}
            for device in devices:
                state = await self.client.async_get_device_state(device.device_id)
                data[device.device_id] = {
                    "device": device,
                    "state": state,
                }
            return data
        except CannotConnect as err:
            raise UpdateFailed(f"Error communicating with Tewke hub: {err}") from err
