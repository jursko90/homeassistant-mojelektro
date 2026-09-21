"""Regression tests for Moj Elektro API processing."""

import asyncio
from datetime import date

from custom_components.mojelektro.const import FIFTEEN_MINUTE_SENSORS
from custom_components.mojelektro.moj_elektro_api import MojElektroApi


class StubMojElektroApi(MojElektroApi):
    """API client with deterministic responses."""

    def __init__(self):
        super().__init__("token", "meter", 4, None)
        self.calls = []

    async def _request_json(self, path, *, params=None):
        self.calls.append((path, params))

        if path == "/reading-type":
            return [
                {
                    "oznaka": "A+",
                    "readingType": "dynamic-a-plus",
                    "readingTypeBrezObracuna": "dynamic-a-plus-raw",
                },
                {
                    "oznaka": "A-",
                    "readingType": "dynamic-a-minus",
                },
            ]

        if path == "/meter-readings":
            return {"intervalBlocks": []}

        raise AssertionError(f"Unexpected path: {path}")


def test_reading_type_catalog_is_discovered_at_runtime():
    """Opaque API IDs must come from /reading-type, not constants."""
    api = StubMojElektroApi()

    catalogue = asyncio.run(api.get_reading_types())

    assert catalogue["A+"]["readingType"] == "dynamic-a-plus"
    assert api._tag_for_reading_type("dynamic-a-plus") == "A+"
    assert api._tag_for_reading_type("dynamic-a-plus-raw") == "A+"


def test_meter_reading_request_uses_discovered_id():
    """Meter requests must use the ID returned by the API catalogue."""
    api = StubMojElektroApi()

    asyncio.run(
        api.get_meter_readings(
            ["A+"],
            start_date=date(2026, 9, 19),
            end_date=date(2026, 9, 21),
        )
    )

    path, params = api.calls[-1]
    assert path == "/meter-readings"
    assert ("option", "ReadingType=dynamic-a-plus") in params
    assert ("usagePoint", "meter") in params


def test_empty_payload_does_not_synthesize_zero():
    """Temporary missing data must preserve previous values upstream."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    assert (
        api.sensors_output(
            [],
            FIFTEEN_MINUTE_SENSORS,
            interval=True,
        )
        == {}
    )
    assert api.consumption_by_block([]) == {}


def test_interval_sensor_uses_latest_published_reading():
    """15-minute sensor should follow API freshness, not wall-clock offset."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    data = [
        {
            "readingType": "dynamic-a-plus",
            "intervalReadings": [
                {
                    "timestamp": "2026-09-20T10:15:00+02:00",
                    "value": "0.1200",
                },
                {
                    "timestamp": "2026-09-20T09:45:00+02:00",
                    "value": "0.1000",
                },
                {
                    "timestamp": "2026-09-20T10:30:00+02:00",
                    "value": "0.1300",
                },
            ],
        }
    ]

    result = api.sensors_output(
        data,
        FIFTEEN_MINUTE_SENSORS,
        interval=True,
    )

    assert result["15min_input"] == 0.13
