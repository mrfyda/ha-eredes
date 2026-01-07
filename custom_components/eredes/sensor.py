"""Sensor platform for E-REDES integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ERedesCoordinator, ERedesCoordinatorData

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import ERedesConfigEntry


@dataclass(frozen=True, kw_only=True)
class ERedesSensorEntityDescription(SensorEntityDescription):
    """Describes E-REDES sensor entity."""

    value_fn: Callable[[ERedesCoordinatorData], float | None]


SENSOR_DESCRIPTIONS: tuple[ERedesSensorEntityDescription, ...] = (
    ERedesSensorEntityDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda data: data.total_kwh,
    ),
    ERedesSensorEntityDescription(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda data: data.today_kwh,
    ),
    ERedesSensorEntityDescription(
        key="energy_yesterday",
        translation_key="energy_yesterday",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda data: data.yesterday_kwh,
    ),
    ERedesSensorEntityDescription(
        key="power_current",
        translation_key="power_current",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: data.current_power_w,
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ERedesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up E-REDES sensor entities."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        ERedesSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class ERedesSensor(CoordinatorEntity[ERedesCoordinator], SensorEntity):
    """Representation of an E-REDES sensor."""

    entity_description: ERedesSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ERedesCoordinator,
        description: ERedesSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.cpe}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.cpe)},
            name=f"E-REDES Meter {coordinator.cpe[-8:]}",
            manufacturer="E-REDES",
            model="Smart Meter",
            configuration_url="https://balcaodigital.e-redes.pt",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None  # type: ignore[unreachable]
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return None  # type: ignore[unreachable]

        attrs: dict[str, Any] = {
            "cpe": self.coordinator.cpe,
            "last_update": self.coordinator.data.last_update.isoformat(),
        }

        if (
            self.entity_description.key == "power_current"
            and self.coordinator.data.last_reading
        ):
            attrs["reading_timestamp"] = (
                self.coordinator.data.last_reading.timestamp.isoformat()
            )

        return attrs
