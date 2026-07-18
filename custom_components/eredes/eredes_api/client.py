"""E-REDES API client."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from http.cookies import SimpleCookie
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
        access_token: str,
    ) -> None:
        """Initialize the E-REDES client with an access token.

        Args:
            session: aiohttp ClientSession
            access_token: The pasted authentication value. Any of these
                shapes are accepted and treated identically:
                - a bare ``aat`` token value (``eyJ...``)
                - a prefixed pair (``aat=eyJ...``)
                - a full Cookie header
                  (``PHPSESSID=xxx; aat=xxx; SimpleSAML=xxx``)
        """
        self._session = session
        self._apply_access_token(access_token)

    def _apply_access_token(self, access_token: str) -> None:
        """Normalize the pasted value and derive the cookies, token and header."""
        self._cookies = self._normalize_cookies(access_token)
        self._aat_token = self._cookies.get("aat", "")
        self._cookie_header = self._build_cookie_header(self._cookies)

    def _normalize_cookies(self, access_token: str) -> dict[str, str]:
        """Normalize a pasted authentication value into a cookies dict.

        The input is trimmed and parsed as a Cookie header. A bare token value
        contains no ``key=value`` pair, so parsing yields no ``aat`` key; in
        that case the whole trimmed input is treated as the ``aat`` token.
        """
        stripped = access_token.strip()
        cookies = self._parse_cookies(stripped)
        if "aat" not in cookies:
            bare = stripped.rstrip(";").strip()
            if bare:
                cookies["aat"] = bare
        return cookies

    def _parse_cookies(self, cookie_string: str) -> dict[str, str]:
        """Parse a cookie string into a dictionary."""
        cookies: dict[str, str] = {}
        simple_cookie = SimpleCookie()
        simple_cookie.load(cookie_string)
        for key, morsel in simple_cookie.items():
            cookies[key] = morsel.value
        return cookies

    @staticmethod
    def _build_cookie_header(cookies: dict[str, str]) -> str:
        """Serialize a cookies dict into a Cookie request header."""
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def update_access_token(self, access_token: str) -> None:
        """Update the access token."""
        self._apply_access_token(access_token)

    async def validate_token(self, cpe: str) -> bool:
        """Validate the token by making a simple API call.

        Args:
            cpe: The CPE to use for validation (must be a real CPE for the user)

        Returns:
            True if the token is valid, False otherwise
        """
        try:
            end_date = datetime.now()
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            await self.get_consumption(cpe, start_date, end_date)
            return True
        except ERedesAuthenticationError:
            return False
        except ERedesError:
            # Other errors mean the token is valid but something else failed
            return True

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/consumptions/history",
            "User-Agent-Context": "WEB",
            "Show-Loader": "true",
            "Cookie": self._cookie_header,
        }
        # Also include Authorization-Request header if we have the aat token
        if self._aat_token:
            headers["Authorization-Request"] = self._aat_token
        return headers

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
                # Capture refreshed session cookie from response
                self._refresh_session_from_response(response)

                if response.status == 401:
                    raise ERedesAuthenticationError(
                        "Token expired - please update your token"
                    )

                if response.status == 403:
                    raise ERedesAuthenticationError("Access denied - invalid token")

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

    def _refresh_session_from_response(self, response: Any) -> None:
        """Update session cookie from API response Set-Cookie header."""
        set_cookie = response.headers.get("Set-Cookie", "")
        if "PHPSESSID=" in set_cookie:
            # Extract new PHPSESSID
            match = re.search(r"PHPSESSID=([^;]+)", set_cookie)
            if match:
                new_phpsessid = match.group(1)
                old_phpsessid = self._cookies.get("PHPSESSID", "")
                if new_phpsessid != old_phpsessid:
                    self._cookies["PHPSESSID"] = new_phpsessid
                    self._cookie_header = self._build_cookie_header(self._cookies)
                    _LOGGER.debug("Session refreshed with new PHPSESSID")

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
