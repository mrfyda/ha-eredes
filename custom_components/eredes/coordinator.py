"""DataUpdateCoordinator for E-REDES integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_ACCESS_TOKEN, CONF_CPE, DEFAULT_SCAN_INTERVAL, DOMAIN
from .eredes_api import (
    ConsumptionData,
    ERedesAuthenticationError,
    ERedesClient,
    ERedesConnectionError,
    ERedesError,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .eredes_api.models import ConsumptionReading

_LOGGER = logging.getLogger(__name__)


@dataclass
class ERedesCoordinatorData:
    """Data class for coordinator data."""

    consumption: ConsumptionData | None
    today_kwh: float
    current_power_w: float
    last_reading: ConsumptionReading | None
    last_update: datetime


class ERedesCoordinator(DataUpdateCoordinator[ERedesCoordinatorData]):
    """Coordinator for fetching E-REDES data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.config_entry = entry
        self._cpe: str = entry.data[CONF_CPE]

        session = async_get_clientsession(hass)
        self._client = ERedesClient(session, str(entry.data[CONF_ACCESS_TOKEN]))

    @property
    def cpe(self) -> str:
        """Return the CPE code."""
        return self._cpe

    @property
    def client(self) -> ERedesClient:
        """Return the API client."""
        return self._client

    def update_access_token(self, access_token: str) -> None:
        """Update the access token in the client."""
        self._client.update_access_token(access_token)

    async def _async_update_data(self) -> ERedesCoordinatorData:
        """Fetch data from E-REDES."""
        try:
            # Fetch yesterday's data (E-REDES data is delayed ~24h)
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_start = today_start - timedelta(days=1)

            consumption = await self._client.get_consumption(
                self._cpe,
                yesterday_start,
                today_start,
            )

            # Sum yesterday's consumption
            today_kwh = consumption.total_kwh

            # Get the most recent reading for current power estimate
            last_reading = consumption.readings[-1] if consumption.readings else None

            # Convert 15-min energy to power (W)
            current_power_w = 0.0
            if last_reading:
                current_power_w = last_reading.value_kwh * 4 * 1000

            _LOGGER.debug(
                "Fetched %d readings, today: %.3f kWh, power: %.0f W",
                len(consumption.readings),
                today_kwh,
                current_power_w,
            )

            return ERedesCoordinatorData(
                consumption=consumption,
                today_kwh=today_kwh,
                current_power_w=current_power_w,
                last_reading=last_reading,
                last_update=now,
            )

        except ERedesAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Authentication failed - please update your access token"
            ) from err
        except ERedesConnectionError as err:
            raise UpdateFailed(f"Error communicating with E-REDES: {err}") from err
        except ERedesError as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
