"""Constants for the Sunology Stream integration."""

from datetime import timedelta

DOMAIN = "sunology_stream"

BASE_URL = "https://backend-mobile.stream.sunology.eu"
API_PREFIX = "/api"

LOGIN_ENDPOINT = "/login-post"
LOGOUT_ENDPOINT = "/logout"
ME_ENDPOINT = "/users/me"
CLIENT_ENDPOINT = "/client"
OVERVIEW_ENDPOINT = "/overview"
STREAM_METER_ENDPOINT = "/stream-meter"
STORAGE_BATTERY_ALL_PAIRED_ENDPOINT = "/storage-battery/all-paired"
ERL_ENDPOINT = "/erl"
DEVICES_STATIONS_AND_STORAGES_ENDPOINT = "/devices/stations-and-storages"
DEVICES_ACCESSORIES_ENDPOINT = "/devices/accessories"
HISTORY_ENDPOINT = "/history"
CLIENT_SIGNED_CONTRACT_ENDPOINT = "/client/clientSignedContract"
ENERGY_AMOUNTS_AND_COSTS_FOR_DAY_ENDPOINT = "/client/energyAmountsAndCostsForDay"

# The "zone" query param is the UTC offset in hours, as the app sends it
# (-(new Date().getTimezoneOffset()) / 60, e.g. "2" in CEST). "+0200" is also
# accepted but silently misinterpreted: history comes back spanning several
# days and consumption shifted by ~30h (confirmed against Enedis data).
HISTORY_DAILY_SCALE = "DAILY"

# NOTE: /users/authenticated does not exist (confirmed 404 against the real
# API) despite being referenced in the app's JS — use ME_ENDPOINT to check
# session validity instead.

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
# Hourly per-tariff energy and the contract only change once an hour at
# best, so they are refreshed less often than the live power data.
SLOW_SCAN_INTERVAL = timedelta(minutes=5)
