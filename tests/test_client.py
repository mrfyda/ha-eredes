"""Tests for the E-REDES API client session-cookie normalization."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.eredes.eredes_api.client import ERedesClient

# A representative JWT-shaped token (base64url segments joined by dots).
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.abc-def_ghi"


def _make_client(session_cookie: str) -> ERedesClient:
    """Build a client with a stub session (the session is unused by headers)."""
    return ERedesClient(MagicMock(), session_cookie)


@pytest.mark.parametrize(
    "session_cookie",
    [
        pytest.param(TOKEN, id="bare-value"),
        pytest.param(f"aat={TOKEN}", id="prefixed"),
        pytest.param(f"  {TOKEN}  ", id="bare-with-whitespace"),
        pytest.param(f"aat={TOKEN};", id="prefixed-trailing-semicolon"),
        pytest.param(f"  aat={TOKEN} ; ", id="prefixed-whitespace-and-semicolon"),
    ],
)
def test_aat_token_normalized_from_various_shapes(session_cookie: str) -> None:
    """Bare, prefixed and whitespace/semicolon-padded inputs all yield the token."""
    client = _make_client(session_cookie)
    headers = client._get_headers()

    assert client._aat_token == TOKEN
    assert headers["Authorization-Request"] == TOKEN
    assert headers["Cookie"] == f"aat={TOKEN}"


def test_full_cookie_header_extracts_aat_and_forwards_all_cookies() -> None:
    """A full Cookie header keeps every cookie and extracts the aat token."""
    cookie = f"PHPSESSID=abc123; aat={TOKEN}; SimpleSAML=xyz789"
    client = _make_client(cookie)
    headers = client._get_headers()

    assert client._aat_token == TOKEN
    assert headers["Authorization-Request"] == TOKEN
    assert "PHPSESSID=abc123" in headers["Cookie"]
    assert f"aat={TOKEN}" in headers["Cookie"]
    assert "SimpleSAML=xyz789" in headers["Cookie"]


def test_full_cookie_header_with_trailing_whitespace_and_semicolon() -> None:
    """Trailing whitespace/semicolon in a full header doesn't drop cookies."""
    cookie = f"  PHPSESSID=abc123; aat={TOKEN}; SimpleSAML=xyz789 ; "
    client = _make_client(cookie)
    headers = client._get_headers()

    assert client._aat_token == TOKEN
    assert headers["Authorization-Request"] == TOKEN
    assert "PHPSESSID=abc123" in headers["Cookie"]
    assert "SimpleSAML=xyz789" in headers["Cookie"]


def test_update_session_cookie_applies_normalization() -> None:
    """update_session_cookie normalizes a bare token just like construction."""
    client = _make_client(f"aat={TOKEN}")
    new_token = "newheader.newpayload.newsig"

    client.update_session_cookie(new_token)
    headers = client._get_headers()

    assert client._aat_token == new_token
    assert headers["Authorization-Request"] == new_token
    assert headers["Cookie"] == f"aat={new_token}"


def test_blank_cookie_yields_no_authorization_header() -> None:
    """A blank input produces no aat token and omits the Authorization header."""
    client = _make_client("   ")
    headers = client._get_headers()

    assert client._aat_token == ""
    assert "Authorization-Request" not in headers
