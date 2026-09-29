"""Translation coverage tests for Moj Elektro entities."""

import json
from pathlib import Path

from custom_components.mojelektro.const import (
    CONTRACTED_POWER_SENSORS,
    DAILY_SENSORS,
    FIFTEEN_MINUTE_SENSORS,
    LAST_PUBLISHED_READING_SENSOR,
    SENSOR_TRANSLATION_KEYS,
    SOUPORABA_SENSORS,
    TARIFF_BLOCK_SENSORS,
    TOTAL_REGISTER_SENSORS,
)


ROOT = Path(__file__).resolve().parents[1]
TRANSLATION_FILES = (
    ROOT / "custom_components" / "mojelektro" / "strings.json",
    ROOT / "custom_components" / "mojelektro" / "translations" / "en.json",
    ROOT / "custom_components" / "mojelektro" / "translations" / "sl.json",
)


def expected_sensor_translation_keys() -> set[str]:
    """Return translation keys for every statically defined sensor."""
    measurement_names = set(FIFTEEN_MINUTE_SENSORS.values())

    for sensor in DAILY_SENSORS.values():
        measurement_names.add(sensor)
        measurement_names.add(sensor.replace("daily_", "monthly_", 1))

    measurement_names.update(TOTAL_REGISTER_SENSORS.values())
    measurement_names.update(TARIFF_BLOCK_SENSORS.values())
    measurement_names.update(CONTRACTED_POWER_SENSORS)
    measurement_names.update(SOUPORABA_SENSORS.values())
    measurement_names.add(LAST_PUBLISHED_READING_SENSOR)

    return {
        SENSOR_TRANSLATION_KEYS.get(name, name)
        for name in measurement_names
    }


def test_all_static_entities_have_english_and_slovenian_translations():
    """Every static entity key should exist in strings, English and Slovenian."""
    expected_sensors = expected_sensor_translation_keys()

    for path in TRANSLATION_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        entity = data["entity"]

        assert expected_sensors <= set(entity["sensor"])
        assert "refresh_data" in entity["button"]
        assert "data_stale" in entity["binary_sensor"]
