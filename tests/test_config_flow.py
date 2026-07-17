"""Tests for E-REDES config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eredes.const import CONF_CPE, DOMAIN
from custom_components.eredes.eredes_api import (
    ERedesAuthenticationError,
    ERedesConnectionError,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_form_user(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
) -> None:
    """Test we get the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_form_user_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
) -> None:
    """Test successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.eredes.config_flow.ERedesClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            mock_config_entry_data,
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"E-REDES ({mock_config_entry_data[CONF_CPE][-8:]})"
    assert result["data"] == mock_config_entry_data


async def test_form_user_invalid_auth(
    hass: HomeAssistant,
    mock_config_entry_data: dict,
) -> None:
    """Test invalid auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.eredes.config_flow.ERedesClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(
            side_effect=ERedesAuthenticationError("Invalid token")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            mock_config_entry_data,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_user_invalid_token_returns_false(
    hass: HomeAssistant,
    mock_config_entry_data: dict,
) -> None:
    """Test invalid token when validate_token returns False."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.eredes.config_flow.ERedesClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            mock_config_entry_data,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_user_cannot_connect(
    hass: HomeAssistant,
    mock_config_entry_data: dict,
) -> None:
    """Test connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.eredes.config_flow.ERedesClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(
            side_effect=ERedesConnectionError("Cannot connect")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            mock_config_entry_data,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_already_configured(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
) -> None:
    """Test we abort if already configured."""
    # Create an existing entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=mock_config_entry_data,
        unique_id=mock_config_entry_data[CONF_CPE],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.eredes.config_flow.ERedesClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            mock_config_entry_data,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
