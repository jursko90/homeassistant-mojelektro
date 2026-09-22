"""Regression tests for Moj Elektro API processing."""

import asyncio
from datetime import date, datetime, timedelta, timezone

from custom_components.mojelektro.const import (
    FIFTEEN_MINUTE_SENSORS,
    TOTAL_REGISTER_SENSORS,
)
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

        if path == "/reading-qualities":
            return [
                {
                    "readingQualityType": "ESTIMATED",
                    "description": "Estimated reading",
                }
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


def test_reading_quality_catalog_is_attached_to_metadata():
    """Quality codes should be explained without rejecting the reading."""
    api = StubMojElektroApi()
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    asyncio.run(api.get_reading_qualities())

    data = [
        {
            "readingType": "dynamic-a-plus",
            "intervalReadings": [
                {
                    "timestamp": "2026-09-20T10:30:00+02:00",
                    "value": "0.1300",
                    "readingQualities": [
                        {"readingQualityType": "ESTIMATED"}
                    ],
                }
            ],
        }
    ]

    result = api.sensors_output(
        data,
        FIFTEEN_MINUTE_SENSORS,
        interval=True,
    )

    assert result["15min_input"] == 0.13
    metadata = api.last_reading_metadata["15min_input"]
    assert metadata["quality_flags_present"] is True
    assert metadata["reading_qualities"] == [
        {
            "code": "ESTIMATED",
            "description": "Estimated reading",
        }
    ]


def test_total_register_uses_latest_raw_meter_state():
    """Total sensors should expose cumulative register state, not a delta."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    result = api.total_registers_output(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-19T00:00:00+02:00",
                        "value": "1200.0",
                    },
                    {
                        "timestamp": "2026-09-20T00:00:00+02:00",
                        "value": "1212.5",
                    },
                ],
            }
        ],
        TOTAL_REGISTER_SENSORS,
    )

    assert result["total_input"] == 1212.5


def test_tariff_blocks_ignore_partial_newer_day():
    """Daily tariff totals should use the latest complete 15-minute day."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    complete_day = date(2026, 9, 19)
    complete_readings = []
    interval_end = datetime(
        2026,
        9,
        19,
        0,
        15,
        tzinfo=timezone(timedelta(hours=2)),
    )
    for index in range(96):
        complete_readings.append(
            {
                "timestamp": (
                    interval_end + timedelta(minutes=15 * index)
                ).isoformat(),
                "value": "1.0",
            }
        )

    partial_readings = [
        {
            "timestamp": datetime(
                2026,
                9,
                20,
                0,
                15 + 15 * index,
                tzinfo=timezone(timedelta(hours=2)),
            ).isoformat(),
            "value": "100.0",
        }
        for index in range(3)
    ]

    result = api.consumption_by_block(
        [
            {
                "readingType": "dynamic-a-plus",
                "intervalReadings": complete_readings + partial_readings,
            }
        ]
    )

    assert round(sum(result.values()), 4) == 96.0
    assert {
        metadata["source_date"]
        for sensor, metadata in api.last_reading_metadata.items()
        if sensor.startswith("daily_input_blok_")
    } == {complete_day.isoformat()}


def test_souporaba_summary_exposes_counts_only():
    """Souporaba entities should expose status counts without identifiers."""
    result = MojElektroApi.souporaba_summary_output(
        [
            {"sifra": 1, "eiMmOddajnika": "secret-a", "statusZahteve": "POTRJENA"},
            {"sifra": 2, "eiMmPrejemnika": "secret-b", "statusZahteve": "V_IZVAJANJU"},
            {"sifra": 3, "statusZahteve": "ZAVRNJENA"},
            {"sifra": 4, "statusZahteve": "POTRJENA"},
        ]
    )

    assert result == {
        "souporaba_total": 4.0,
        "souporaba_confirmed": 2.0,
        "souporaba_in_progress": 1.0,
        "souporaba_rejected": 1.0,
    }
    assert "secret-a" not in repr(result)
    assert "secret-b" not in repr(result)


def test_daily_and_monthly_reset_metadata():
    """Daily/monthly deltas should expose their actual reset boundaries."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    result = api.sensors_output(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-01T00:00:00+02:00",
                        "value": "1000.0",
                    },
                    {
                        "timestamp": "2026-09-20T00:00:00+02:00",
                        "value": "1120.0",
                    },
                    {
                        "timestamp": "2026-09-21T00:00:00+02:00",
                        "value": "1127.5",
                    },
                ],
            }
        ],
        {"A+_T0": "daily_input"},
        interval=False,
    )

    assert result["daily_input"] == 7.5
    assert result["monthly_input"] == 127.5
    assert (
        api.last_reading_metadata["daily_input"]["last_reset"]
        == "2026-09-20T00:00:00+02:00"
    )
    assert (
        api.last_reading_metadata["monthly_input"]["last_reset"]
        == "2026-09-01T00:00:00+02:00"
    )


def test_latest_source_timestamp_uses_newest_published_register():
    """Freshness diagnostic should reflect the newest source timestamp."""
    api = MojElektroApi("token", "meter", 4, None)
    api.last_reading_metadata = {
        "15min_input": {
            "source_timestamp": "2026-09-20T10:30:00+02:00",
        },
        "daily_input": {
            "source_timestamp": "2026-09-21T00:00:00+02:00",
        },
        "total_input": {
            "source_timestamp": "2026-09-20T00:00:00+02:00",
        },
    }

    latest = api.latest_source_timestamp()

    assert latest is not None
    assert latest.isoformat() == "2026-09-21T00:00:00+02:00"
