"""Standalone probe script — calls the real Sunology Stream API with real
credentials to capture actual JSON response shapes.

Not part of the Home Assistant integration itself. Run manually:

    python scripts/probe.py

Reads SUNOLOGY_USERNAME / SUNOLOGY_PASSWORD from a local .env file (see
.env.example) or from the environment. Never commit real credentials.

Saves each response body to dev/fixtures/<name>.json (gitignored) for
inspection and later use as test fixtures.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "dev" / "fixtures"

BASE_URL = "https://backend-mobile.stream.sunology.eu/api"


def load_dotenv(path: Path) -> None:
    """Minimal .env loader — no external dependency needed for this."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def save_fixture(name: str, response: requests.Response) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"{name}.json"
    try:
        data = response.json()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except ValueError:
        path.with_suffix(".txt").write_text(response.text, encoding="utf-8")


def show(name: str, response: requests.Response) -> None:
    print(f"\n=== {name} ===")
    print(f"status: {response.status_code}")
    ct = response.headers.get("content-type", "")
    print(f"content-type: {ct}")
    if "application/json" in ct:
        try:
            print(json.dumps(response.json(), indent=2, ensure_ascii=False)[:2000])
        except ValueError:
            print(response.text[:500])
    else:
        print(response.text[:500])
    save_fixture(name, response)


def main() -> int:
    load_dotenv(ROOT / ".env")
    username = os.environ.get("SUNOLOGY_USERNAME")
    password = os.environ.get("SUNOLOGY_PASSWORD")
    if not username or not password:
        print("SUNOLOGY_USERNAME / SUNOLOGY_PASSWORD not set (check your .env file)", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    login_resp = session.post(
        f"{BASE_URL}/login-post",
        json={"username": username.lower(), "password": password},
        timeout=15,
    )
    show("login-post", login_resp)
    print(f"\nSet-Cookie header present: {'set-cookie' in login_resp.headers}")
    print(f"Session cookies after login: {list(session.cookies.keys())}")

    if not login_resp.ok:
        print("\nLogin failed, stopping here.", file=sys.stderr)
        return 1

    show("users-me", session.get(f"{BASE_URL}/users/me", timeout=15))
    show("users-authenticated", session.get(f"{BASE_URL}/users/authenticated", timeout=15))
    show("client", session.get(f"{BASE_URL}/client", timeout=15))

    # /overview is a POST in the app's code; body content unknown, try empty first.
    show("overview", session.post(f"{BASE_URL}/overview", json={}, timeout=15))

    show("devices-stations-and-storages", session.get(f"{BASE_URL}/devices/stations-and-storages", timeout=15))
    show("devices-accessories", session.get(f"{BASE_URL}/devices/accessories", timeout=15))
    show("stream-meter", session.get(f"{BASE_URL}/stream-meter", timeout=15))
    show("storage-battery-all-paired", session.get(f"{BASE_URL}/storage-battery/all-paired", timeout=15))
    show("erl", session.get(f"{BASE_URL}/erl", timeout=15))
    show("irradiance", session.get(f"{BASE_URL}/irradiance", timeout=15))
    show("irradiance-forecast", session.get(f"{BASE_URL}/irradiance-forecast", timeout=15))

    print(f"\nFixtures saved to {FIXTURES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
