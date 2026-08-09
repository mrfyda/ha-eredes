"""Tests for parsing the E-REDES ``edm/get`` consumption response.

Covers the load-curve extraction path: register selection, unit conversion,
timestamp parsing, and the deliberate absence of any data-quality filtering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.eredes.eredes_api.client import ERedesClient

START = datetime(2026, 1, 1)
END = datetime(2026, 1, 6)

# Sentinel distinguishing "key absent" from "key present and null".
ABSENT = object()


def _curve(
    timestamp: str = "2026-01-05T00:15:00Z",
    value: float | None = 0.05,
    unit: str = "kWh",
    status: Any = ABSENT,
) -> dict[str, Any]:
    """Build a single load-curve point."""
    curve: dict[str, Any] = {
        "loadCurveTimestamp": timestamp,
        "meterLoadCurve": value,
        "meterLoadCurveUnitMeasurement": unit,
    }
    if status is not ABSENT:
        curve["meterLoadCurveStatus"] = status
    return curve


def _response(
    curves: list[dict[str, Any]],
    register: str = "A+",
    *,
    success: bool = True,
) -> dict[str, Any]:
    """Wrap load curves in the envelope returned by ``edm/get``."""
    return {
        "Body": {
            "Success": success,
            "Result": {
                "utilitiesDevices": [
                    {"meterLoadCurves": [{"register": register, "loadCurves": curves}]}
                ]
            },
        }
    }


def _parse(response: dict[str, Any]) -> list[Any]:
    """Parse a response with a client that never touches the network."""
    client = ERedesClient(MagicMock(), "aat=mock.jwt.token")
    return client._parse_consumption_response("CPE", response, START, END).readings


# --- meterLoadCurveStatus is NOT a quality filter ----------------------------


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(ABSENT, id="field-absent"),
        pytest.param(None, id="explicit-null"),
        pytest.param("0", id="status-zero"),
        pytest.param("1", id="status-one"),
        pytest.param("2", id="status-two"),
    ],
)
def test_readings_are_kept_regardless_of_status(status: Any) -> None:
    """Every ``meterLoadCurveStatus`` value is real metered energy.

    Verified against the live API on 2026-08-09: summing **all** load-curve
    points reproduces the cumulative meter index to within its 1 kWh
    quantization, across five independent multi-week spans. Filtering on this
    flag discards real consumption — in one span every point carried status
    ``1`` and a filter would have dropped the entire period.
    """
    readings = _parse(_response([_curve(status=status)]))

    assert len(readings) == 1
    assert readings[0].value_kwh == pytest.approx(0.05)


def test_mixed_status_payload_keeps_every_reading() -> None:
    """A payload mixing statuses sums to the full metered total."""
    readings = _parse(
        _response(
            [
                _curve("2026-01-05T00:15:00Z", 0.05, status="0"),
                _curve("2026-01-05T00:30:00Z", 0.06, status="1"),
                _curve("2026-01-05T00:45:00Z", 0.07, status=ABSENT),
                _curve("2026-01-05T01:00:00Z", 0.08, status="2"),
            ]
        )
    )

    assert sum(r.value_kwh for r in readings) == pytest.approx(0.26)


# --- register selection ------------------------------------------------------


def test_only_active_import_register_is_read() -> None:
    """``A-`` (energy exported to the grid) is not consumption and is ignored."""
    assert _parse(_response([_curve()], register="A-")) == []


# --- units and values --------------------------------------------------------


@pytest.mark.parametrize(
    ("unit", "expected_kwh"),
    [
        pytest.param("kWh", 0.05, id="kwh-mixed-case"),
        pytest.param("kwh", 0.05, id="kwh-lower-case"),
        pytest.param("Wh", 0.00005, id="wh-passthrough"),
    ],
)
def test_unit_conversion(unit: str, expected_kwh: float) -> None:
    """kWh values are scaled to Wh internally; other units pass through as Wh."""
    readings = _parse(_response([_curve(value=0.05, unit=unit)]))

    assert readings[0].value_kwh == pytest.approx(expected_kwh)


def test_reading_without_value_is_skipped() -> None:
    """A null ``meterLoadCurve`` carries no measurement."""
    assert _parse(_response([_curve(value=None)])) == []


# --- timestamps --------------------------------------------------------------


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        pytest.param(
            "2026-01-05T00:15:00Z",
            datetime(2026, 1, 5, 0, 15, tzinfo=UTC),
            id="iso-with-z",
        ),
        pytest.param(
            "2026-01-05T00:15:00",
            datetime(2026, 1, 5, 0, 15, tzinfo=UTC),
            id="iso-without-z",
        ),
        pytest.param(
            "2026-01-05 00:15:00",
            datetime(2026, 1, 5, 0, 15, tzinfo=UTC),
            id="space-separated",
        ),
    ],
)
def test_timestamp_formats(timestamp: str, expected: datetime) -> None:
    """Each accepted wire format yields the same aware-UTC instant.

    January is WET (UTC+0), so the wall-clock reading and its UTC equivalent
    coincide — this pins the formats, not the offset.
    """
    readings = _parse(_response([_curve(timestamp=timestamp)]))

    assert readings[0].timestamp == expected


# --- the ``Z`` suffix is Lisbon local time, not UTC --------------------------


def test_summer_reading_is_shifted_back_an_hour() -> None:
    """August is WEST (UTC+1), so a 14:30 wall clock is 13:30 UTC.

    Taking the ``Z`` at face value is the bug this guards: it placed every
    reading between late March and late October an hour late.
    """
    readings = _parse(_response([_curve("2026-08-06T14:30:00Z", 0.05)]))

    assert readings[0].timestamp == datetime(2026, 8, 6, 13, 30, tzinfo=UTC)


def test_winter_reading_is_unchanged() -> None:
    """January is WET (UTC+0), so the wall clock already is UTC."""
    readings = _parse(_response([_curve("2026-01-05T14:30:00Z", 0.05)]))

    assert readings[0].timestamp == datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def test_spring_forward_gap_closes_in_utc() -> None:
    """2026-03-29: the missing local hour becomes contiguous in UTC.

    Shape taken from the live API, which returns 92 points that day with
    00:45 followed directly by 02:00.
    """
    readings = _parse(
        _response(
            [
                _curve("2026-03-29T00:45:00Z", 0.05),
                _curve("2026-03-29T02:00:00Z", 0.06),
            ]
        )
    )

    assert [r.timestamp for r in readings] == [
        datetime(2026, 3, 29, 0, 45, tzinfo=UTC),
        datetime(2026, 3, 29, 1, 0, tzinfo=UTC),
    ]


def test_fall_back_duplicates_resolve_to_distinct_instants() -> None:
    """2025-10-26: the repeated local hour maps to two different UTC hours.

    Shape taken from the live API, which returns 100 points that day with
    01:00/01:15/01:30/01:45 each appearing twice. Collapsing them would
    double-count an hour of consumption into a single bucket.
    """
    readings = _parse(
        _response(
            [
                _curve("2025-10-26T01:00:00Z", 0.05),  # WEST, UTC+1
                _curve("2025-10-26T01:30:00Z", 0.06),
                _curve("2025-10-26T01:00:00Z", 0.07),  # WET, UTC+0
                _curve("2025-10-26T01:30:00Z", 0.08),
            ]
        )
    )

    assert [(r.timestamp, r.value_kwh) for r in readings] == [
        (datetime(2025, 10, 26, 0, 0, tzinfo=UTC), pytest.approx(0.05)),
        (datetime(2025, 10, 26, 0, 30, tzinfo=UTC), pytest.approx(0.06)),
        (datetime(2025, 10, 26, 1, 0, tzinfo=UTC), pytest.approx(0.07)),
        (datetime(2025, 10, 26, 1, 30, tzinfo=UTC), pytest.approx(0.08)),
    ]
    assert len({r.timestamp for r in readings}) == 4


def test_unparseable_timestamp_is_skipped() -> None:
    """A reading whose timestamp can't be parsed is dropped, not crashed on."""
    assert _parse(_response([_curve(timestamp="05/01/2026 00:15")])) == []


def test_readings_are_sorted_by_timestamp() -> None:
    """Readings come back in chronological order regardless of wire order."""
    readings = _parse(
        _response(
            [
                _curve("2026-01-05T00:45:00Z", 0.07),
                _curve("2026-01-05T00:15:00Z", 0.05),
                _curve("2026-01-05T00:30:00Z", 0.06),
            ]
        )
    )

    assert [r.timestamp for r in readings] == [
        datetime(2026, 1, 5, 0, 15, tzinfo=UTC),
        datetime(2026, 1, 5, 0, 30, tzinfo=UTC),
        datetime(2026, 1, 5, 0, 45, tzinfo=UTC),
    ]


# --- envelope ----------------------------------------------------------------


def test_unsuccessful_response_yields_no_readings() -> None:
    """``Success: false`` is not parsed for data."""
    assert _parse(_response([_curve()], success=False)) == []


def test_empty_result_yields_no_readings() -> None:
    """A response with no devices parses to an empty series."""
    assert _parse({"Body": {"Success": True, "Result": {}}}) == []
