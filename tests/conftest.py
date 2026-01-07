"""Fixtures for E-REDES tests."""

from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eredes.const import CONF_AAT_TOKEN, CONF_CPE
from custom_components.eredes.eredes_api.models import (
    ConsumptionData,
    ConsumptionReading,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""


@pytest.fixture(autouse=True)
def expected_lingering_threads() -> bool:
    """Allow lingering threads from aiohttp's safe shutdown loop."""
    return True


@pytest.fixture
def mock_config_entry_data() -> dict:
    """Return mock config entry data."""
    return {
        CONF_AAT_TOKEN: "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.mock_token",
        CONF_CPE: "PT0002000012345678AB",
    }


@pytest.fixture
def mock_consumption_data() -> ConsumptionData:
    """Return mock consumption data."""
    now = datetime.now()
    readings = [
        ConsumptionReading(
            timestamp=now.replace(hour=i, minute=0),
            value_wh=500.0,  # 0.5 kWh per 15-min interval
        )
        for i in range(24)
    ]
    return ConsumptionData(
        cpe="PT0002000012345678AB",
        readings=readings,
        start_date=now.replace(hour=0),
        end_date=now.replace(hour=23),
    )


@pytest.fixture
def mock_eredes_client(
    mock_consumption_data: ConsumptionData,
) -> Generator[MagicMock]:
    """Return a mocked E-REDES client."""
    with patch(
        "custom_components.eredes.eredes_api.ERedesClient",
        autospec=True,
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(return_value=True)
        mock_client.get_consumption = AsyncMock(return_value=mock_consumption_data)
        yield mock_client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.eredes.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup
