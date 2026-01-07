"""Historical data import for E-REDES integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance  # type: ignore[attr-defined]
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import ERedesCoordinator
    from .eredes_api.models import ConsumptionReading

_LOGGER = logging.getLogger(__name__)

# Maximum days to fetch in a single request (API limit)
MAX_DAYS_PER_REQUEST = 31

# Total days of history to import
TOTAL_HISTORY_DAYS = 730  # 2 years


async def async_import_historical_data(
    hass: HomeAssistant,
    coordinator: ERedesCoordinator,
) -> None:
    """Import historical energy data from E-REDES.

    This function fetches up to 2 years of historical consumption data
    and imports it into Home Assistant's long-term statistics.
    """
    statistic_id = f"{DOMAIN}:energy_{coordinator.cpe}"

    _LOGGER.info(
        "Starting historical data import for CPE %s",
        coordinator.cpe[-8:],
    )

    # Check if we already have statistics
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,
        {"sum"},
    )

    if last_stats and statistic_id in last_stats:
        # We already have data, find the last timestamp
        last_stat = last_stats[statistic_id][0]
        start_date = datetime.fromtimestamp(last_stat["start"])
        _LOGGER.info(
            "Found existing statistics, importing from %s",
            start_date.isoformat(),
        )
    else:
        # No existing data, import from 2 years ago
        start_date = datetime.now() - timedelta(days=TOTAL_HISTORY_DAYS)
        _LOGGER.info(
            "No existing statistics, importing from %s",
            start_date.isoformat(),
        )

    end_date = datetime.now()

    # Fetch data in chunks to avoid API timeouts
    all_readings: list[ConsumptionReading] = []
    current_start = start_date

    while current_start < end_date:
        current_end = min(
            current_start + timedelta(days=MAX_DAYS_PER_REQUEST),
            end_date,
        )

        try:
            _LOGGER.debug(
                "Fetching data from %s to %s",
                current_start.isoformat(),
                current_end.isoformat(),
            )
            consumption = await coordinator.client.get_consumption(
                coordinator.cpe,
                current_start,
                current_end,
            )
            all_readings.extend(consumption.readings)
        except Exception as ex:
            _LOGGER.warning(
                "Failed to fetch data for period %s - %s: %s",
                current_start.isoformat(),
                current_end.isoformat(),
                ex,
            )

        current_start = current_end

    if not all_readings:
        _LOGGER.warning("No historical data found to import")
        return

    # Sort readings by timestamp
    all_readings.sort(key=lambda r: r.timestamp)

    _LOGGER.info(
        "Fetched %d readings, aggregating to hourly statistics",
        len(all_readings),
    )

    # Aggregate to hourly statistics
    statistics = _aggregate_to_hourly_statistics(all_readings)

    if not statistics:
        _LOGGER.warning("No statistics generated from readings")
        return

    # Create metadata
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"E-REDES Energy ({coordinator.cpe[-8:]})",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_class="energy",
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    # Import statistics
    _LOGGER.info(
        "Importing %d hourly statistics",
        len(statistics),
    )

    async_add_external_statistics(hass, metadata, statistics)

    _LOGGER.info(
        "Historical data import complete for CPE %s",
        coordinator.cpe[-8:],
    )


def _aggregate_to_hourly_statistics(
    readings: list[ConsumptionReading],
) -> list[StatisticData]:
    """Aggregate 15-minute readings to hourly statistics."""
    if not readings:
        return []

    statistics: list[StatisticData] = []
    cumulative_sum = 0.0

    # Group readings by hour
    hourly_data: dict[datetime, float] = {}

    for reading in readings:
        # Round down to the start of the hour
        hour_start = reading.timestamp.replace(minute=0, second=0, microsecond=0)

        if hour_start not in hourly_data:
            hourly_data[hour_start] = 0.0

        hourly_data[hour_start] += reading.value_kwh

    # Convert to sorted list of statistics
    for hour_start in sorted(hourly_data.keys()):
        hour_kwh = hourly_data[hour_start]
        cumulative_sum += hour_kwh

        statistics.append(
            StatisticData(
                start=hour_start,
                state=hour_kwh,
                sum=cumulative_sum,
            )
        )

    return statistics
