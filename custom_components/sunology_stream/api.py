"""Low-level HTTP client for the (unofficial, reverse-engineered) Sunology
Stream cloud API.

Authentication is session-cookie based, not token based. Each client owns
its own aiohttp session with its own cookie jar rather than reusing Home
Assistant's shared session, so multiple config entries (multiple Sunology
accounts) never share cookies.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    CLIENT_ENDPOINT,
    ERL_ENDPOINT,
    LOGIN_ENDPOINT,
    LOGOUT_ENDPOINT,
    ME_ENDPOINT,
    OVERVIEW_ENDPOINT,
    STORAGE_BATTERY_ALL_PAIRED_ENDPOINT,
    STREAM_METER_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

API_URL = f"{BASE_URL}/api"


class SunologyStreamApiError(Exception):
    """Base error for the Sunology Stream API client."""


class SunologyStreamAuthError(SunologyStreamApiError):
    """Raised when authentication fails or the session has expired."""


class SunologyStreamConnectionError(SunologyStreamApiError):
    """Raised when the API cannot be reached at all."""


class SunologyStreamApiClient:
    """Thin async wrapper around the Sunology Stream cloud API."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())

    async def close(self) -> None:
        """Close the underlying session. Must be called on unload."""
        await self._session.close()

    async def login(self) -> None:
        """Authenticate and store the resulting session cookie."""
        try:
            response = await self._session.post(
                f"{API_URL}{LOGIN_ENDPOINT}",
                json={"username": self._username.lower(), "password": self._password},
            )
        except aiohttp.ClientError as err:
            raise SunologyStreamConnectionError(str(err)) from err

        if response.status in (401, 403):
            raise SunologyStreamAuthError("Invalid username or password")
        if not response.ok:
            raise SunologyStreamApiError(
                f"Unexpected status {response.status} during login"
            )

    async def logout(self) -> None:
        """Log out and invalidate the session cookie."""
        try:
            await self._session.post(f"{API_URL}{LOGOUT_ENDPOINT}")
        except aiohttp.ClientError:
            # Best-effort — nothing to recover from a failed logout.
            _LOGGER.debug("Logout request failed, ignoring", exc_info=True)

    async def _request(
        self, method: str, endpoint: str, *, retry_on_auth_error: bool = True, **kwargs: Any
    ) -> dict[str, Any] | list[Any] | None:
        """Make an authenticated request, re-logging in once on 401/403."""
        try:
            response = await self._session.request(method, f"{API_URL}{endpoint}", **kwargs)
        except aiohttp.ClientError as err:
            raise SunologyStreamConnectionError(str(err)) from err

        if response.status in (401, 403):
            if not retry_on_auth_error:
                raise SunologyStreamAuthError("Session expired and re-login failed")
            _LOGGER.debug("Session expired, re-logging in")
            await self.login()
            return await self._request(
                method, endpoint, retry_on_auth_error=False, **kwargs
            )

        if not response.ok:
            raise SunologyStreamApiError(
                f"Unexpected status {response.status} for {method} {endpoint}"
            )

        if response.status == 204 or not response.content_length:
            return None
        return await response.json()

    async def get_me(self) -> dict[str, Any]:
        """Return the current user's profile. Also used as a session check."""
        return await self._request("GET", ME_ENDPOINT)  # type: ignore[return-value]

    async def get_client(self) -> dict[str, Any]:
        """Return the client profile, including capability flags."""
        return await self._request("GET", CLIENT_ENDPOINT)  # type: ignore[return-value]

    async def get_overview(self) -> dict[str, Any]:
        """Return the live dashboard overview (production/consumption/storage)."""
        return await self._request("POST", OVERVIEW_ENDPOINT, json={})  # type: ignore[return-value]

    async def get_stream_meter(self) -> list[Any]:
        """Return paired grid stream meters (empty if hasGridStreamMeter is False)."""
        return await self._request("GET", STREAM_METER_ENDPOINT)  # type: ignore[return-value]

    async def get_storage_battery_all_paired(self) -> list[Any]:
        """Return paired storage batteries (empty if hasStorageBattery is False)."""
        return await self._request("GET", STORAGE_BATTERY_ALL_PAIRED_ENDPOINT)  # type: ignore[return-value]

    async def get_erl(self) -> dict[str, Any]:
        """Return the ERL (Linky TIC reader) device status."""
        return await self._request("GET", ERL_ENDPOINT)  # type: ignore[return-value]
