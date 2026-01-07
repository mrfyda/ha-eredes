"""Data models for the E-REDES API."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConsumptionReading:
    """A single consumption reading from E-REDES."""

    timestamp: datetime
    value_wh: float  # Energy in Wh for this interval

    @property
    def value_kwh(self) -> float:
        """Get value in kWh."""
        return self.value_wh / 1000


@dataclass
class ConsumptionData:
    """Consumption data from E-REDES."""

    cpe: str
    readings: list[ConsumptionReading]
    start_date: datetime
    end_date: datetime

    @property
    def total_kwh(self) -> float:
        """Get total consumption in kWh."""
        return sum(r.value_kwh for r in self.readings)

    def get_readings_for_date(self, date: datetime) -> list[ConsumptionReading]:
        """Get readings for a specific date."""
        return [
            r
            for r in self.readings
            if r.timestamp.date() == date.date()
        ]
