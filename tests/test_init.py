"""Tests for E-REDES config entry migration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eredes import async_migrate_entry
from custom_components.eredes.const import CONF_ACCESS_TOKEN, CONF_CPE, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CPE = "PT0002000012345678AB"
TOKEN = "eyJ.mock.jwt"


@pytest.mark.parametrize("legacy_key", ["session_cookie", "aat_token"])
async def test_migrate_v1_legacy_token_key(
    hass: HomeAssistant, legacy_key: str
) -> None:
    """A v1 entry's legacy token key is moved to access_token and bumped to v2."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={legacy_key: TOKEN, CONF_CPE: CPE},
        unique_id=CPE,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert entry.data[CONF_ACCESS_TOKEN] == TOKEN
    assert entry.data[CONF_CPE] == CPE
    assert legacy_key not in entry.data


async def test_migrate_v2_is_noop(hass: HomeAssistant) -> None:
    """A current (v2) entry is left untouched."""
    data = {CONF_ACCESS_TOKEN: TOKEN, CONF_CPE: CPE}
    entry = MockConfigEntry(domain=DOMAIN, version=2, data=data, unique_id=CPE)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert dict(entry.data) == data


async def test_migrate_from_future_version_fails(hass: HomeAssistant) -> None:
    """A downgrade from a future version is refused."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={CONF_ACCESS_TOKEN: TOKEN, CONF_CPE: CPE},
        unique_id=CPE,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is False
