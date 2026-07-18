"""Historical data import for E-REDES integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
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
TOTAL_HISTORY_DAYS = 365  # 1 year

# When resuming, start the fetch a couple of days before the last stored hour
# so the window comfortably covers it despite any timezone skew. Aggregation
# then drops everything up to and including that hour, so nothing is re-counted.
REFETCH_BUFFER_DAYS = 2


def statistic_id(cpe: str) -> str:
    """Return the external long-term-statistics id for a CPE's energy history.

    External statistics must be ``<source>:<object_id>`` (colon-separated), not
    an entity id — see CONTEXT.md and docs/adr/0002.
    """
    return f"{DOMAIN}:energy_{cpe[-8:].lower()}"


async def async_import_historical_data(
    hass: HomeAssistant,
    coordinator: ERedesCoordinator,
) -> None:
    """Import historical energy data from E-REDES.

    This function fetches up to 1 year of historical consumption data
    and imports it into Home Assistant's long-term statistics.
    """
    stat_id = statistic_id(coordinator.cpe)
    _LOGGER.debug("Historical import starting for %s", stat_id)

    # Resume from the last imported hour when we already have statistics;
    # otherwise import the full history window.
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        stat_id,
        True,
        {"sum"},
    )

    full_start = datetime.now() - timedelta(days=TOTAL_HISTORY_DAYS)
    initial_sum = 0.0
    after: datetime | None = None
    if last_stats and stat_id in last_stats:
        last_row = last_stats[stat_id][0]
        # get_last_statistics returns start as a UTC epoch; read it back in UTC
        # so it lines up with the UTC hour buckets we store.
        after = datetime.fromtimestamp(last_row["start"], tz=UTC)
        initial_sum = last_row.get("sum") or 0.0
        # Fetch from a couple of days before the cutoff (window safety against
        # timezone skew); _aggregate_to_hourly_statistics drops anything up to
        # and including `after`, so already-counted hours are never re-added.
        start_date = max(
            full_start, after.replace(tzinfo=None) - timedelta(days=REFETCH_BUFFER_DAYS)
        )
        _LOGGER.debug("Resuming historical import after %s", after.isoformat())
    else:
        start_date = full_start
        _LOGGER.debug("Importing full history window from %s", start_date.isoformat())

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
                "Fetching %s to %s",
                current_start.isoformat(),
                current_end.isoformat(),
            )
            consumption = await coordinator.client.get_consumption(
                coordinator.cpe,
                current_start,
                current_end,
            )
            _LOGGER.debug("Got %d readings", len(consumption.readings))
            all_readings.extend(consumption.readings)
        except Exception as ex:
            _LOGGER.error(
                "Failed to fetch history %s - %s: %s",
                current_start.isoformat(),
                current_end.isoformat(),
                ex,
            )

        current_start = current_end

    if not all_readings:
        _LOGGER.debug("No historical data found to import")
        return

    # Sort readings by timestamp
    all_readings.sort(key=lambda r: r.timestamp)

    # Aggregate to hourly statistics, continuing the cumulative sum from the
    # last import and skipping hours already stored.
    statistics = _aggregate_to_hourly_statistics(all_readings, initial_sum, after)

    if not statistics:
        _LOGGER.debug("No statistics generated from %d readings", len(all_readings))
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"E-REDES Energy ({coordinator.cpe[-8:]})",
        source=DOMAIN,
        statistic_id=stat_id,
        unit_class=None,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    try:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.debug(
            "Imported %d hourly stats (%.3f kWh) for %s",
            len(statistics),
            statistics[-1]["sum"],
            stat_id,
        )
    except Exception:
        _LOGGER.exception("Failed to add external statistics for %s", stat_id)


def _aggregate_to_hourly_statistics(
    readings: list[ConsumptionReading],
    initial_sum: float = 0.0,
    after: datetime | None = None,
) -> list[StatisticData]:
    """Aggregate 15-minute readings to hourly statistics.

    Args:
        readings: 15-minute interval readings (timestamps are naive UTC).
        initial_sum: cumulative sum of previously imported hours; the returned
            stats continue from here so the series stays monotonic across runs.
        after: if set, hours at or before this instant are skipped (they were
            already imported). Must be timezone-aware UTC.
    """
    if not readings:
        _LOGGER.debug("No readings to aggregate")
        return []

    statistics: list[StatisticData] = []
    cumulative_sum = initial_sum

    # Group readings by hour
    hourly_data: dict[datetime, float] = {}

    for reading in readings:
        # Round down to the start of the hour and make timezone-aware (UTC)
        hour_start = reading.timestamp.replace(
            minute=0, second=0, microsecond=0, tzinfo=UTC
        )

        if after is not None and hour_start <= after:
            continue

        if hour_start not in hourly_data:
            hourly_data[hour_start] = 0.0

        hourly_data[hour_start] += reading.value_kwh

    _LOGGER.debug(
        "Aggregated %d readings into %d hourly buckets",
        len(readings),
        len(hourly_data),
    )

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

    _LOGGER.debug(
        "Created %d statistics, final cumulative sum: %.3f kWh",
        len(statistics),
        cumulative_sum,
    )

    return statistics
