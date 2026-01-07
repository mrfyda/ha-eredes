"""E-REDES API client."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .exceptions import ERedesAuthenticationError, ERedesConnectionError, ERedesError
from .models import ConsumptionData, ConsumptionReading

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://balcaodigital.e-redes.pt"
API_URL = f"{BASE_URL}/ms/reading/data-usage/edm/get"


class ERedesClient:
    """Client for interacting with the E-REDES API."""

    def __init__(
        self,
        session: ClientSession,
        aat_token: str,
    ) -> None:
        """Initialize the E-REDES client with AAT token."""
        self._session = session
        self._aat_token = aat_token

    def update_token(self, aat_token: str) -> None:
        """Update the AAT token."""
        self._aat_token = aat_token

    async def validate_token(self) -> bool:
        """Validate the token by making a simple API call."""
        try:
            end_date = datetime.now()
            start_date = end_date.replace(hour=0, minute=0, second=0)
            await self.get_consumption("test", start_date, end_date)
            return True
        except ERedesAuthenticationError:
            return False
        except ERedesError:
            # Other errors mean the token is valid but something else failed
            return True

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/consumptions/history",
            "User-Agent-Context": "WEB",
            "Authorization-Request": self._aat_token,
            "Show-Loader": "true",
        }

    async def get_consumption(
        self,
        cpe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> ConsumptionData:
        """Fetch consumption data for the specified date range.

        Args:
            cpe: The CPE (meter) identifier
            start_date: Start of the date range
            end_date: End of the date range

        Returns:
            ConsumptionData with readings for the specified period

        Raises:
            ERedesAuthenticationError: If authentication fails
            ERedesConnectionError: If connection fails
            ERedesError: For other API errors
        """
        # Format dates for API
        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "cpe": cpe,
            "request_type": "3",  # 15-minute interval readings
            "start_date": start_str,
            "end_date": end_str,
            "wait": True,
            "formatted": False,
            "nif_requester": None,
            "serial_number": "",
            "nif": None,
        }

        try:
            async with self._session.post(
                API_URL,
                json=payload,
                headers=self._get_headers(),
            ) as response:
                if response.status == 401:
                    raise ERedesAuthenticationError(
                        "Token expired - please update your token"
                    )

                if response.status == 403:
                    raise ERedesAuthenticationError(
                        "Access denied - invalid token"
                    )

                if response.status != 200:
                    raise ERedesError(
                        f"API request failed with status {response.status}"
                    )

                data = await response.json()
                return self._parse_consumption_response(cpe, data, start_date, end_date)

        except ERedesError:
            raise
        except Exception as ex:
            _LOGGER.exception("Error fetching consumption data")
            raise ERedesConnectionError(f"Failed to fetch data: {ex}") from ex

    def _parse_consumption_response(
        self,
        cpe: str,
        data: dict[str, Any],
        start_date: datetime,
        end_date: datetime,
    ) -> ConsumptionData:
        """Parse the consumption API response.

        Response format:
        {
            "Body": {
                "Success": true,
                "Result": {
                    "utilitiesDevices": [{
                        "meterLoadCurves": [{
                            "register": "A+",
                            "loadCurves": [{
                                "loadCurveTimestamp": "2026-01-05T00:15:00Z",
                                "meterLoadCurve": 0.052,
                                "meterLoadCurveUnitMeasurement": "kwh"
                            }]
                        }]
                    }]
                }
            }
        }
        """
        readings: list[ConsumptionReading] = []

        try:
            body = data.get("Body", {})
            if not body.get("Success", False):
                _LOGGER.warning("API returned unsuccessful response")
                return ConsumptionData(
                    cpe=cpe, readings=[], start_date=start_date, end_date=end_date
                )

            result = body.get("Result", {})
            devices = result.get("utilitiesDevices", [])

            for device in devices:
                load_curves_groups = device.get("meterLoadCurves", [])
                for group in load_curves_groups:
                    # We want "A+" register (active energy import)
                    register = group.get("register", "")
                    if register != "A+":
                        continue

                    load_curves = group.get("loadCurves", [])
                    for curve in load_curves:
                        timestamp_str = curve.get("loadCurveTimestamp")
                        value = curve.get("meterLoadCurve")
                        unit = curve.get("meterLoadCurveUnitMeasurement", "").lower()

                        if timestamp_str and value is not None:
                            # Parse timestamp (ISO format with Z)
                            timestamp = self._parse_timestamp(timestamp_str)
                            if timestamp:
                                # Value is in kWh, convert to Wh for internal use
                                value_wh = (
                                    float(value) * 1000
                                    if unit == "kwh"
                                    else float(value)
                                )
                                readings.append(
                                    ConsumptionReading(
                                        timestamp=timestamp,
                                        value_wh=value_wh,
                                    )
                                )

        except (KeyError, TypeError, ValueError) as ex:
            _LOGGER.exception("Error parsing consumption response: %s", ex)

        # Sort readings by timestamp
        readings.sort(key=lambda r: r.timestamp)

        return ConsumptionData(
            cpe=cpe,
            readings=readings,
            start_date=start_date,
            end_date=end_date,
        )

    def _parse_timestamp(self, timestamp_str: str) -> datetime | None:
        """Parse timestamp from ISO format string."""
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        return None
