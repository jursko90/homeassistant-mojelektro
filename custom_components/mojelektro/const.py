"""Constants for the Moj Elektro integration."""

DOMAIN = "mojelektro"
VERSION = "0.3.0"

API_BASE_URL = "https://api.informatika.si/mojelektro/v1"
REQUEST_TIMEOUT_SECONDS = 30

CONF_TOKEN = "token"
CONF_METER_ID = "meter_id"
CONF_DECIMAL = "decimal"
CONF_UPDATE_INTERVAL = "update_interval_minutes"
CONF_LOOKBACK_DAYS = "lookback_days"
CONF_ENABLE_15MIN = "enable_15min"
CONF_ENABLE_DAILY = "enable_daily"
CONF_ENABLE_TOTAL = "enable_total"
CONF_ENABLE_TARIFF_BLOCKS = "enable_tariff_blocks"
CONF_ENABLE_CONTRACTED_POWER = "enable_contracted_power"
CONF_ENABLE_SOUPORABA = "enable_souporaba"
CONF_STALE_AFTER_HOURS = "stale_after_hours"
CONF_EXTRA_READING_TAGS = "extra_reading_tags"

DEFAULT_DECIMAL = 4
DEFAULT_UPDATE_INTERVAL = 60
DEFAULT_LOOKBACK_DAYS = 2
DEFAULT_ENABLE_15MIN = True
DEFAULT_ENABLE_DAILY = True
DEFAULT_ENABLE_TOTAL = True
DEFAULT_ENABLE_TARIFF_BLOCKS = True
DEFAULT_ENABLE_CONTRACTED_POWER = True
DEFAULT_ENABLE_SOUPORABA = False
DEFAULT_STALE_AFTER_HOURS = 48
DEFAULT_EXTRA_READING_TAGS = ()

MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 1440
MIN_LOOKBACK_DAYS = 1
MAX_LOOKBACK_DAYS = 7
MIN_STALE_AFTER_HOURS = 24
MAX_STALE_AFTER_HOURS = 168

# Stable Home Assistant sensor keys mapped to the semantic register labels
# returned by GET /reading-type. The opaque readingType IDs themselves are
# intentionally not stored in the integration and are discovered at runtime.
FIFTEEN_MINUTE_SENSORS = {
    "A+": "15min_input",
    "A-": "15min_output",
}

DAILY_SENSORS = {
    "A+_T0": "daily_input",
    "A+_T1": "daily_input_peak",
    "A+_T2": "daily_input_offpeak",
    "A-_T0": "daily_output",
    "A-_T1": "daily_output_peak",
    "A-_T2": "daily_output_offpeak",
}

TOTAL_REGISTER_SENSORS = {
    "A+_T0": "total_input",
    "A+_T1": "total_input_peak",
    "A+_T2": "total_input_offpeak",
    "A-_T0": "total_output",
    "A-_T1": "total_output_peak",
    "A-_T2": "total_output_offpeak",
}

TARIFF_BLOCK_SENSORS = {
    1: "daily_input_blok_1",
    2: "daily_input_blok_2",
    3: "daily_input_blok_3",
    4: "daily_input_blok_4",
    5: "daily_input_blok_5",
}

CONTRACTED_POWER_SENSORS = tuple(
    f"casovni_blok_{block_number}" for block_number in range(1, 6)
)

SOUPORABA_SENSORS = {
    "total": "souporaba_total",
    "POTRJENA": "souporaba_confirmed",
    "V_IZVAJANJU": "souporaba_in_progress",
    "ZAVRNJENA": "souporaba_rejected",
}

LAST_PUBLISHED_READING_SENSOR = "last_published_reading"

SENSOR_TRANSLATION_KEYS = {
    "15min_input": "interval_input",
    "15min_output": "interval_output",
}
