"""Constants for the E-REDES integration."""

from typing import Final

DOMAIN: Final = "eredes"

# Configuration keys
CONF_CPE: Final = "cpe"
CONF_SESSION_COOKIE: Final = "session_cookie"

# Legacy key for migration
CONF_AAT_TOKEN: Final = "aat_token"

# API endpoints
BASE_URL: Final = "https://balcaodigital.e-redes.pt"
API_URL: Final = f"{BASE_URL}/ms/reading/data-usage/edm/get"

# Timing
DEFAULT_SCAN_INTERVAL: Final = 3600  # 1 hour in seconds
TOKEN_REFRESH_MARGIN: Final = 300  # Refresh token 5 minutes before expiry

# API request types
REQUEST_TYPE_15MIN: Final = "3"  # 15-minute interval readings

# Sensor keys
SENSOR_ENERGY: Final = "energy"
SENSOR_POWER: Final = "power"
