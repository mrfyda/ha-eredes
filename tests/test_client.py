"""Tests for the E-REDES API client access-token normalization."""

from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.eredes.eredes_api.client import ERedesClient
from custom_components.eredes.eredes_api.exceptions import (
    ERedesAuthenticationError,
    ERedesConnectionError,
)

# A representative JWT-shaped token (base64url segments joined by dots).
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.abc-def_ghi"


def _make_client(access_token: str) -> ERedesClient:
    """Build a client with a stub session (the session is unused by headers)."""
    return ERedesClient(MagicMock(), access_token)


@pytest.mark.parametrize(
    "access_token",
    [
        pytest.param(TOKEN, id="bare-value"),
        pytest.param(f"aat={TOKEN}", id="prefixed"),
        pytest.param(f"  {TOKEN}  ", id="bare-with-whitespace"),
        pytest.param(f"aat={TOKEN};", id="prefixed-trailing-semicolon"),
        pytest.param(f"  aat={TOKEN} ; ", id="prefixed-whitespace-and-semicolon"),
    ],
)
def test_aat_token_normalized_from_various_shapes(access_token: str) -> None:
    """Bare, prefixed and whitespace/semicolon-padded inputs all yield the token."""
    client = _make_client(access_token)
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


def test_update_access_token_applies_normalization() -> None:
    """update_access_token normalizes a bare token just like construction."""
    client = _make_client(f"aat={TOKEN}")
    new_token = "newheader.newpayload.newsig"

    client.update_access_token(new_token)
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


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_token_claims_decodes_jwt_payload_from_any_shape() -> None:
    """token_claims reads the aat JWT payload, bare or inside a cookie header."""
    token = f"{_b64({'alg': 'HS256'})}.{_b64({'iss': 'msauth-jwt', 'exp': 123})}.sig"
    for pasted in (token, f"aat={token}", f"PHPSESSID=x; aat={token}; other=y"):
        assert _make_client(pasted).token_claims() == {"iss": "msauth-jwt", "exp": 123}


@pytest.mark.parametrize(
    "access_token",
    ["", "not-a-jwt", "a.b", "a.%%%.c", f"a.{_b64(['not', 'a', 'dict'])}.c"],
)
def test_token_claims_returns_none_for_non_jwt(access_token: str) -> None:
    """Values that are not a JWT with an object payload yield None."""
    assert _make_client(access_token).token_claims() is None


def _session_answering(
    status: int | None = None, *, delay: float = 0, error: Exception | None = None
) -> MagicMock:
    """A ClientSession whose post() answers with ``status`` after ``delay`` s."""

    class _Response:
        def __init__(self) -> None:
            self.status = status

        async def __aenter__(self) -> _Response:
            if delay:
                await asyncio.sleep(delay)
            if error:
                raise error
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    session = MagicMock()
    session.post = MagicMock(side_effect=lambda *_a, **_k: _Response())
    return session


@pytest.mark.parametrize("status", [401, 403])
async def test_check_token_rejected(status: int) -> None:
    """E-Redes rejecting the token raises an authentication error."""
    client = ERedesClient(_session_answering(status), "aat=token")
    with pytest.raises(ERedesAuthenticationError):
        await client.check_token("PT0000000000000000XX")


async def test_check_token_accepted_on_200() -> None:
    """A 200 means E-Redes accepted the token."""
    session = _session_answering(200)
    await ERedesClient(session, "aat=token").check_token("PT0000000000000000XX")
    body = session.post.call_args.kwargs["json"]
    assert body["start_date"] > body["end_date"]  # reversed range: no data to fetch


async def test_check_token_accepted_when_eredes_keeps_working() -> None:
    """No answer within the timeout means the token passed authentication."""
    client = ERedesClient(_session_answering(200, delay=1), "aat=token")
    await client.check_token("PT0000000000000000XX", timeout=0.05)


@pytest.mark.parametrize(
    "session",
    [
        pytest.param(
            _session_answering(error=aiohttp.ClientConnectionError("down")),
            id="unreachable",
        ),
        pytest.param(_session_answering(500), id="server_error"),
    ],
)
async def test_check_token_connection_problems(session: MagicMock) -> None:
    """Network errors and unexpected statuses are connection errors."""
    with pytest.raises(ERedesConnectionError):
        await ERedesClient(session, "aat=token").check_token("PT0000000000000000XX")
