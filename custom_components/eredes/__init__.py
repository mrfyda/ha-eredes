"""The E-REDES integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .coordinator import ERedesCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .eredes_api import ERedesClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class ERedesData:
    """Runtime data for E-REDES integration."""

    coordinator: ERedesCoordinator
    client: ERedesClient


type ERedesConfigEntry = ConfigEntry[ERedesData]


async def async_setup_entry(hass: HomeAssistant, entry: ERedesConfigEntry) -> bool:
    """Set up E-REDES from a config entry."""
    coordinator = ERedesCoordinator(hass, entry)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store runtime data
    entry.runtime_data = ERedesData(
        coordinator=coordinator,
        client=coordinator.client,
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Schedule historical data import (runs in background)
    hass.async_create_task(
        _async_import_historical_data(hass, entry, coordinator)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ERedesConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_import_historical_data(
    hass: HomeAssistant,
    _entry: ERedesConfigEntry,
    coordinator: ERedesCoordinator,
) -> None:
    """Import historical data in the background."""
    from .historical import async_import_historical_data  # noqa: PLC0415

    try:
        await async_import_historical_data(hass, coordinator)
    except Exception:
        _LOGGER.exception("Failed to import historical data")
