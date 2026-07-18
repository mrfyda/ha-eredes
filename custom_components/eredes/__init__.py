"""The E-REDES integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .const import CONF_ACCESS_TOKEN, LEGACY_TOKEN_KEYS
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
    _LOGGER.debug("Setting up E-REDES integration")
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
        _async_import_historical_data(hass, entry, coordinator),
        name="eredes_historical_import",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ERedesConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current version.

    Version 1 stored the access token under a legacy key (``session_cookie``,
    or ``aat_token`` in the earliest builds). Version 2 stores it under
    ``access_token`` (see CONTEXT.md → Authentication).
    """
    if entry.version > 2:
        # Downgrade from a future version is not supported.
        return False

    if entry.version == 1:
        data = dict(entry.data)
        for legacy_key in LEGACY_TOKEN_KEYS:
            if legacy_key in data:
                data[CONF_ACCESS_TOKEN] = data.pop(legacy_key)
                break
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.debug("Migrated E-REDES config entry to version 2")

    return True


async def _async_import_historical_data(
    hass: HomeAssistant,
    _entry: ERedesConfigEntry,
    coordinator: ERedesCoordinator,
) -> None:
    """Import historical data in the background."""
    from .historical import async_import_historical_data  # noqa: PLC0415

    _LOGGER.debug("Starting historical data import for CPE %s", coordinator.cpe[-8:])
    try:
        await async_import_historical_data(hass, coordinator)
        _LOGGER.debug("Historical data import completed")
    except Exception:
        _LOGGER.exception("Failed to import historical data")
