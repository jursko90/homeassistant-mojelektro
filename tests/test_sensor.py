"""Regression tests for Moj Elektro sensor state handling."""

from types import SimpleNamespace

from custom_components.mojelektro.sensor import MojElektroSensor


def _sensor_with_value(measurement_name, value):
    """Create the minimum sensor instance needed to exercise native_value."""
    sensor = object.__new__(MojElektroSensor)
    sensor.measurement_name = measurement_name
    sensor._last_known_state = None
    sensor.coordinator = SimpleNamespace(data={measurement_name: value})
    return sensor


def test_souporaba_count_native_value_stays_integer():
    """Privacy-safe souporaba counts must not be converted to floats."""
    sensor = _sensor_with_value("souporaba_total", 2)

    assert sensor.native_value == 2
    assert isinstance(sensor.native_value, int)


def test_measurement_native_value_remains_float():
    """Regular energy and power measurements should retain float semantics."""
    sensor = _sensor_with_value("15min_input", "1.25")

    assert sensor.native_value == 1.25
    assert isinstance(sensor.native_value, float)
