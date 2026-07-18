"""Diagnostics support for E-REDES integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import CONF_ACCESS_TOKEN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import ERedesConfigEntry

# async_redact_data matches keys exactly, so the actual config key must be
# listed. The legacy keys are kept so diagnostics from un-migrated entries
# are still redacted.
TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_ACCESS_TOKEN,
    "session_cookie",
    "aat_token",
    "aat",
    "session",
    "token",
    "nif",
    "nif_requester",
}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant,
    entry: ERedesConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    diagnostics_data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
    }

    if coordinator.data is not None:
        diagnostics_data["data"] = {
            "today_kwh": coordinator.data.today_kwh,
            "current_power_w": coordinator.data.current_power_w,
            "last_update": coordinator.data.last_update.isoformat(),
            "readings_count": (
                len(coordinator.data.consumption.readings)
                if coordinator.data.consumption
                else 0
            ),
        }

        if coordinator.data.last_reading:
            diagnostics_data["data"]["last_reading"] = {
                "timestamp": coordinator.data.last_reading.timestamp.isoformat(),
                "value_kwh": coordinator.data.last_reading.value_kwh,
            }

    return diagnostics_data
