"""Tests for E-REDES historical statistics import."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.recorder.statistics import valid_statistic_id

from custom_components.eredes.eredes_api.models import ConsumptionReading
from custom_components.eredes.historical import (
    _aggregate_to_hourly_statistics,
    statistic_id,
)

CPE = "PT0002000012345678AB"


def _reading(hour: int, minute: int, value_wh: float) -> ConsumptionReading:
    """Build a naive-UTC 15-minute reading on 2026-01-01."""
    return ConsumptionReading(
        timestamp=datetime(2026, 1, 1, hour, minute),
        value_wh=value_wh,
    )


def test_statistic_id_is_valid_external_id() -> None:
    """The id must be a `source:object_id` external id (the import crash regression)."""
    stat_id = statistic_id(CPE)

    assert stat_id == "eredes:energy_345678ab"
    assert valid_statistic_id(stat_id)


def test_aggregate_buckets_by_utc_hour() -> None:
    """15-minute readings roll up into cumulative, top-of-hour UTC statistics."""
    readings = [
        _reading(0, 0, 250.0),
        _reading(0, 15, 250.0),
        _reading(0, 30, 250.0),
        _reading(0, 45, 250.0),  # hour 0 -> 1.0 kWh
        _reading(1, 0, 500.0),
        _reading(1, 30, 500.0),  # hour 1 -> 1.0 kWh
    ]

    stats = _aggregate_to_hourly_statistics(readings)

    assert [s["start"] for s in stats] == [
        datetime(2026, 1, 1, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 1, tzinfo=UTC),
    ]
    assert [s["state"] for s in stats] == [1.0, 1.0]
    assert [s["sum"] for s in stats] == [1.0, 2.0]  # cumulative


def test_aggregate_seeds_cumulative_sum() -> None:
    """A resume continues the running sum from the previous import."""
    readings = [_reading(0, 0, 1000.0), _reading(1, 0, 1000.0)]

    stats = _aggregate_to_hourly_statistics(readings, initial_sum=10.0)

    assert [s["sum"] for s in stats] == [11.0, 12.0]


def test_aggregate_skips_hours_at_or_before_cutoff() -> None:
    """Hours already imported (<= after) are dropped so they aren't re-counted."""
    readings = [_reading(0, 0, 1000.0), _reading(1, 0, 1000.0), _reading(2, 0, 1000.0)]
    after = datetime(2026, 1, 1, 1, tzinfo=UTC)

    stats = _aggregate_to_hourly_statistics(readings, initial_sum=5.0, after=after)

    # Only hour 2 survives; its sum continues from the seed.
    assert [s["start"] for s in stats] == [datetime(2026, 1, 1, 2, tzinfo=UTC)]
    assert stats[0]["sum"] == 6.0
