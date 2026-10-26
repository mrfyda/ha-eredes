"""Tests for E-REDES config flow."""

from __future__ import annotations

import base64
import json
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eredes.const import CONF_ACCESS_TOKEN, CONF_CPE, DOMAIN
from custom_components.eredes.eredes_api import (
    ERedesAuthenticationError,
    ERedesConnectionError,
)

if TYPE_CHECKING:
    from collections.abc import Generator

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


def _jwt(**claims: object) -> str:
    """Build an unsigned JWT with the given payload claims."""

    def b64(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{b64({'typ': 'JWT', 'alg': 'HS256'})}.{b64(claims)}.signature"


def _fresh_token(**overrides: object) -> str:
    claims = {"iss": "msauth-jwt", "exp": int(time.time()) + 3600}
    claims.update(overrides)
    return _jwt(**claims)


async def _add_entry(hass: HomeAssistant, data: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        unique_id=data[CONF_CPE],
        title=f"E-REDES ({data[CONF_CPE][-8:]})",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_check_token() -> Generator[AsyncMock]:
    """Patch the quick online token check (E-Redes accepts by default)."""
    with patch(
        "custom_components.eredes.config_flow.ERedesClient.check_token",
        new_callable=AsyncMock,
    ) as check:
        yield check


@pytest.fixture
def mock_validate_token() -> Generator[AsyncMock]:
    """Patch the slow full validation (used for new CPEs only)."""
    with patch(
        "custom_components.eredes.config_flow.ERedesClient.validate_token",
        new_callable=AsyncMock,
        return_value=True,
    ) as validate:
        yield validate


async def test_reauth_valid_token_uses_quick_check(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
    mock_check_token: AsyncMock,
    mock_validate_token: AsyncMock,
) -> None:
    """A renewed token is accepted after the quick check, not a data fetch."""
    entry = await _add_entry(hass, mock_config_entry_data)
    result = await entry.start_reauth_flow(hass)
    token = _fresh_token()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: token}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == token
    mock_check_token.assert_awaited_once_with(mock_config_entry_data[CONF_CPE])
    mock_validate_token.assert_not_awaited()


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="not_a_jwt"),
        pytest.param(_fresh_token(exp=int(time.time()) - 60), id="expired"),
        pytest.param(
            _fresh_token(exp=int(time.time()) + 30), id="expires_within_margin"
        ),
        pytest.param(_fresh_token(iss="someone-else"), id="wrong_issuer"),
        pytest.param(_jwt(iss="msauth-jwt"), id="no_expiry"),
    ],
)
async def test_reauth_rejects_unusable_token_without_network(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
    mock_check_token: AsyncMock,
    token: str,
) -> None:
    """Malformed, expired or foreign tokens are rejected before any request."""
    entry = await _add_entry(hass, mock_config_entry_data)
    result = await entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: token}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data == mock_config_entry_data
    mock_check_token.assert_not_awaited()


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (ERedesAuthenticationError("rejected"), "invalid_auth"),
        (ERedesConnectionError("unreachable"), "cannot_connect"),
    ],
)
async def test_reauth_quick_check_failures(
    hass: HomeAssistant,
    mock_config_entry_data: dict,
    mock_check_token: AsyncMock,
    side_effect: Exception,
    error: str,
) -> None:
    """A token E-Redes rejects, or an unreachable E-Redes, is reported."""
    mock_check_token.side_effect = side_effect
    entry = await _add_entry(hass, mock_config_entry_data)
    result = await entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: _fresh_token()}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert entry.data == mock_config_entry_data


async def test_reauth_accepts_cookie_header(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
    mock_check_token: AsyncMock,  # noqa: ARG001
) -> None:
    """The aat token is found inside a pasted Cookie header too."""
    entry = await _add_entry(hass, mock_config_entry_data)
    result = await entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ACCESS_TOKEN: f"PHPSESSID=abc; aat={_fresh_token()}; other=1"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reconfigure_same_cpe_uses_quick_check(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
    mock_check_token: AsyncMock,
    mock_validate_token: AsyncMock,
) -> None:
    """Renewing the token for the same CPE uses the quick check."""
    entry = await _add_entry(hass, mock_config_entry_data)
    result = await entry.start_reconfigure_flow(hass)
    token = _fresh_token()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ACCESS_TOKEN: token, CONF_CPE: mock_config_entry_data[CONF_CPE]},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == token
    mock_check_token.assert_awaited_once()
    mock_validate_token.assert_not_awaited()


async def test_reconfigure_new_cpe_validates_with_eredes(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,  # noqa: ARG001
    mock_config_entry_data: dict,
    mock_check_token: AsyncMock,
    mock_validate_token: AsyncMock,
) -> None:
    """A different CPE still gets the full check against E-Redes."""
    entry = await _add_entry(hass, mock_config_entry_data)
    result = await entry.start_reconfigure_flow(hass)
    new_cpe = "PT0002000087654321ZZ"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ACCESS_TOKEN: _fresh_token(), CONF_CPE: new_cpe},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CPE] == new_cpe
    mock_validate_token.assert_awaited_once_with(new_cpe)
    mock_check_token.assert_not_awaited()
