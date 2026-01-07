"""DataUpdateCoordinator for E-REDES integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_AAT_TOKEN, CONF_CPE, DEFAULT_SCAN_INTERVAL, DOMAIN
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
    total_kwh: float
    today_kwh: float
    yesterday_kwh: float
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
        self._client = ERedesClient(session, str(entry.data[CONF_AAT_TOKEN]))

    @property
    def cpe(self) -> str:
        """Return the CPE code."""
        return self._cpe

    @property
    def client(self) -> ERedesClient:
        """Return the API client."""
        return self._client

    def update_token(self, aat_token: str) -> None:
        """Update the AAT token in the client."""
        self._client.update_token(aat_token)

    async def _async_update_data(self) -> ERedesCoordinatorData:
        """Fetch data from E-REDES."""
        try:
            # Fetch last 48 hours of data to ensure we have today and yesterday
            end_date = datetime.now()
            start_date = end_date - timedelta(hours=48)

            consumption = await self._client.get_consumption(
                self._cpe,
                start_date,
                end_date,
            )

            # Calculate metrics
            now = datetime.now()
            today = now.date()
            yesterday = today - timedelta(days=1)

            today_readings = consumption.get_readings_for_date(now)
            yesterday_readings = consumption.get_readings_for_date(
                datetime.combine(yesterday, datetime.min.time())
            )

            today_kwh = sum(r.value_kwh for r in today_readings)
            yesterday_kwh = sum(r.value_kwh for r in yesterday_readings)

            # Get the most recent reading for current power estimate
            last_reading = consumption.readings[-1] if consumption.readings else None

            # Convert 15-min energy to power (W)
            # 15 minutes = 0.25 hours, so multiply by 4 to get hourly rate
            current_power_w = 0.0
            if last_reading:
                # Convert kWh in 15-min interval to average power in W
                current_power_w = last_reading.value_kwh * 4 * 1000

            # Calculate cumulative total
            # For TOTAL_INCREASING we need a monotonically increasing value
            # We use the sum of all readings as a proxy
            total_kwh = consumption.total_kwh

            return ERedesCoordinatorData(
                consumption=consumption,
                total_kwh=total_kwh,
                today_kwh=today_kwh,
                yesterday_kwh=yesterday_kwh,
                current_power_w=current_power_w,
                last_reading=last_reading,
                last_update=now,
            )

        except ERedesAuthenticationError as err:
            # Trigger reauth flow
            raise ConfigEntryAuthFailed(
                "Authentication failed - please update your token"
            ) from err
        except ERedesConnectionError as err:
            raise UpdateFailed(f"Error communicating with E-REDES: {err}") from err
        except ERedesError as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
