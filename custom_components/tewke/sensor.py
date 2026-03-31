"""Sensor platform for the Tewke integration.

Maps Tewke environmental readings (CO₂, humidity, temperature) to Home
Assistant ``SensorEntity`` instances.  All entities share the same
:class:`~.coordinator.TewkeCoordinator` so the hub is polled only once.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_TYPE_SENSOR,
    DOMAIN,
    ENTRY_COORDINATOR,
    SENSOR_TYPE_CO2,
    SENSOR_TYPE_HUMIDITY,
    SENSOR_TYPE_TEMPERATURE,
)
from .coordinator import TewkeCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TewkeSensorEntityDescription(SensorEntityDescription):
    """Describes a Tewke sensor entity and how to extract its value."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda _: None


SENSOR_DESCRIPTIONS: tuple[TewkeSensorEntityDescription, ...] = (
    TewkeSensorEntityDescription(
        key=SENSOR_TYPE_CO2,
        translation_key=SENSOR_TYPE_CO2,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        value_fn=lambda state: state.get("co2"),
    ),
    TewkeSensorEntityDescription(
        key=SENSOR_TYPE_HUMIDITY,
        translation_key=SENSOR_TYPE_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda state: state.get("humidity"),
    ),
    TewkeSensorEntityDescription(
        key=SENSOR_TYPE_TEMPERATURE,
        translation_key=SENSOR_TYPE_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda state: state.get("temperature"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tewke sensor entities from a config entry."""
    coordinator: TewkeCoordinator = hass.data[DOMAIN][entry.entry_id][ENTRY_COORDINATOR]

    entities: list[TewkeSensor] = []
    for device_id, entry_data in coordinator.data.items():
        if entry_data["device"].device_type != DEVICE_TYPE_SENSOR:
            continue
        for description in SENSOR_DESCRIPTIONS:
            # Only add the sensor if the hub actually reports this measurement.
            if description.value_fn(entry_data["state"]) is not None:
                entities.append(TewkeSensor(coordinator, device_id, description))

    async_add_entities(entities)


class TewkeSensor(CoordinatorEntity[TewkeCoordinator], SensorEntity):
    """Representation of a single Tewke environmental sensor reading."""

    _attr_has_entity_name = True
    entity_description: TewkeSensorEntityDescription

    def __init__(
        self,
        coordinator: TewkeCoordinator,
        device_id: str,
        description: TewkeSensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self.entity_description = description

        device = coordinator.data[device_id]["device"]
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device.name,
            manufacturer="Tewke",
            model=device.model,
            sw_version=device.sw_version,
            connections={("mac", device.mac)} if device.mac else set(),
        )

    @property
    def native_value(self) -> Any:
        """Return the current sensor reading."""
        state: dict[str, Any] = self.coordinator.data[self._device_id]["state"]
        return self.entity_description.value_fn(state)
