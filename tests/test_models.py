"""Tests for E-REDES API models."""

from datetime import datetime

from custom_components.eredes.eredes_api.models import (
    ConsumptionData,
    ConsumptionReading,
)


class TestConsumptionReading:
    """Tests for ConsumptionReading model."""

    def test_value_kwh(self) -> None:
        """Test conversion from Wh to kWh."""
        reading = ConsumptionReading(
            timestamp=datetime.now(),
            value_wh=1500.0,
        )
        assert reading.value_kwh == 1.5

    def test_value_kwh_zero(self) -> None:
        """Test zero value."""
        reading = ConsumptionReading(
            timestamp=datetime.now(),
            value_wh=0.0,
        )
        assert reading.value_kwh == 0.0


class TestConsumptionData:
    """Tests for ConsumptionData model."""

    def test_total_kwh(self) -> None:
        """Test total consumption calculation."""
        readings = [
            ConsumptionReading(
                timestamp=datetime(2024, 1, 1, i),
                value_wh=1000.0,
            )
            for i in range(4)
        ]
        data = ConsumptionData(
            cpe="PT0001234567890",
            readings=readings,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )
        assert data.total_kwh == 4.0

    def test_total_kwh_empty(self) -> None:
        """Test total with no readings."""
        data = ConsumptionData(
            cpe="PT0001234567890",
            readings=[],
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )
        assert data.total_kwh == 0.0

    def test_get_readings_for_date(self) -> None:
        """Test filtering readings by date."""
        target_date = datetime(2024, 1, 15)
        other_date = datetime(2024, 1, 16)

        readings = [
            ConsumptionReading(
                timestamp=target_date.replace(hour=10),
                value_wh=500.0,
            ),
            ConsumptionReading(
                timestamp=target_date.replace(hour=11),
                value_wh=600.0,
            ),
            ConsumptionReading(
                timestamp=other_date.replace(hour=10),
                value_wh=700.0,
            ),
        ]

        data = ConsumptionData(
            cpe="PT0001234567890",
            readings=readings,
            start_date=target_date,
            end_date=other_date,
        )

        filtered = data.get_readings_for_date(target_date)
        assert len(filtered) == 2
        assert all(r.timestamp.date() == target_date.date() for r in filtered)
