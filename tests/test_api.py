"""Tests for the low-level Sunology Stream API client."""

from __future__ import annotations

import aiohttp
import pytest
import pytest_asyncio
from aioresponses import aioresponses
from yarl import URL

from custom_components.sunology_stream.api import (
    API_URL,
    SunologyStreamApiClient,
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)


@pytest_asyncio.fixture
async def client():
    api = SunologyStreamApiClient("test@example.com", "hunter2")
    yield api
    await api.close()


@pytest.mark.asyncio
async def test_login_success(client: SunologyStreamApiClient):
    with aioresponses() as m:
        m.post(f"{API_URL}/login-post", status=204)
        await client.login()


@pytest.mark.asyncio
async def test_login_lowercases_username():
    api = SunologyStreamApiClient("Test@Example.com", "hunter2")
    try:
        with aioresponses() as m:
            m.post(f"{API_URL}/login-post", status=204)
            await api.login()
            request = m.requests[("POST", URL(f"{API_URL}/login-post"))][0]
            assert request.kwargs["json"]["username"] == "test@example.com"
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: SunologyStreamApiClient):
    with aioresponses() as m:
        m.post(f"{API_URL}/login-post", status=401)
        with pytest.raises(SunologyStreamAuthError):
            await client.login()


@pytest.mark.asyncio
async def test_get_client_parses_json_without_content_length(
    client: SunologyStreamApiClient,
):
    # Regression test: a response with no Content-Length header (e.g.
    # chunked transfer) must still be parsed, not treated as empty.
    with aioresponses() as m:
        m.get(f"{API_URL}/client", payload={"hasErl": True}, headers={})
        result = await client.get_client()
    assert result == {"hasErl": True}


@pytest.mark.asyncio
async def test_request_retries_once_after_session_expiry(
    client: SunologyStreamApiClient,
):
    with aioresponses() as m:
        m.get(f"{API_URL}/client", status=401)
        m.post(f"{API_URL}/login-post", status=204)
        m.get(f"{API_URL}/client", payload={"ok": True})
        result = await client.get_client()
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_request_raises_auth_error_after_failed_retry(
    client: SunologyStreamApiClient,
):
    with aioresponses() as m:
        m.get(f"{API_URL}/client", status=401)
        m.post(f"{API_URL}/login-post", status=204)
        m.get(f"{API_URL}/client", status=401)
        with pytest.raises(SunologyStreamAuthError):
            await client.get_client()


@pytest.mark.asyncio
async def test_connection_error_is_wrapped(client: SunologyStreamApiClient):
    with aioresponses() as m:
        m.get(f"{API_URL}/client", exception=aiohttp.ClientConnectionError("boom"))
        with pytest.raises(SunologyStreamConnectionError):
            await client.get_client()


@pytest.mark.asyncio
async def test_no_content_response_returns_none(client: SunologyStreamApiClient):
    with aioresponses() as m:
        m.post(f"{API_URL}/overview", status=204)
        result = await client.get_overview()
    assert result is None
