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

# The "zone" query param is a Java ZoneOffset, and only the compact form
# (no colon, e.g. "+0200") is accepted — "+02:00" is rejected. Also accepts
# plain integers (interpreted as something other than hours, confirmed by
# testing — steer clear of those and always use the strftime("%z") form.
HISTORY_DAILY_SCALE = "DAILY"

# NOTE: /users/authenticated does not exist (confirmed 404 against the real
# API) despite being referenced in the app's JS — use ME_ENDPOINT to check
# session validity instead.

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
