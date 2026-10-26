"""Constants for the E-REDES integration."""

from typing import Final

DOMAIN: Final = "eredes"

# Configuration keys
CONF_CPE: Final = "cpe"
CONF_ACCESS_TOKEN: Final = "access_token"

# Legacy config keys migrated to CONF_ACCESS_TOKEN (see async_migrate_entry)
LEGACY_TOKEN_KEYS: Final = ("session_cookie", "aat_token")

# API endpoints
BASE_URL: Final = "https://balcaodigital.e-redes.pt"
API_URL: Final = f"{BASE_URL}/ms/reading/data-usage/edm/get"

# Timing
DEFAULT_SCAN_INTERVAL: Final = 3600  # 1 hour in seconds

# API request types
REQUEST_TYPE_15MIN: Final = "3"  # 15-minute interval readings

# Sensor keys
SENSOR_ENERGY: Final = "energy"
SENSOR_POWER: Final = "power"

# Renewed tokens are checked locally (see config_flow._check_token_locally):
# the aat JWT must come from E-Redes' auth service and not expire within the
# margin below. E-Redes' data endpoint is too slow (60+ s) to validate with.
TOKEN_ISSUER: Final = "msauth-jwt"
TOKEN_EXPIRY_MARGIN_SECONDS: Final = 60
