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
    assert (
        api.last_reading_metadata["15min_input"]["last_reset"]
        == "2026-09-20T10:15:00+02:00"
    )


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


def test_safe_meter_metadata_excludes_personal_identifiers():
    """Diagnostics metadata should contain technical fields only."""
    safe = MojElektroApi._extract_safe_meter_metadata(
        {
            "naziv": "Private home",
            "naslov": "Secret address",
            "lastnik": {
                "naziv": "Private owner",
                "davcnaSt": "secret-tax-id",
            },
            "pogodbeniPodatki": {
                "steviloFaz": 3,
                "prikljucnaMoc": 14,
                "dovoljenaMocOddaje": "11.0",
                "obstoj15MinutneMeritve": True,
                "daljinskoCitanje": True,
            },
            "tehnicniPodatki": {
                "tipStevca": "Example meter",
                "tovarniskaStevilkaMkn": "secret-serial",
                "letoIzdelave": 2024,
            },
        }
    )

    assert safe == {
        "stevilo_faz": 3,
        "prikljucna_moc": 14,
        "dovoljena_moc_oddaje": "11.0",
        "daljinsko_citanje": True,
        "obstoj_15_min_meritve": True,
        "tip_stevca": "Example meter",
        "leto_izdelave_stevca": 2024,
    }
    assert "secret" not in repr(safe)


class ContractedPowerStub(MojElektroApi):
    """Stub contracted-power metadata endpoints."""

    def __init__(self):
        super().__init__("token", "meter", 4, None)
        self.site_calls = 0
        self.point_calls = 0

    async def get_meter_site(self):
        self.site_calls += 1
        return {
            "merilneTocke": [
                {"vrsta": "OMTO", "gsrn": "123456789"}
            ]
        }

    async def get_meter_point(self, gsrn):
        self.point_calls += 1
        assert gsrn == "123456789"
        return {
            "dogovorjeneMoci": [
                {
                    "datumOd": "2020-01-01T00:00:00+01:00",
                    "datumDo": "2035-12-31T23:59:59+01:00",
                    "veljavnost": True,
                    "casovniBlok1": "5.1",
                    "casovniBlok2": "5.2",
                    "casovniBlok3": "5.3",
                    "casovniBlok4": "5.4",
                    "casovniBlok5": "5.5",
                }
            ]
        }


def test_contracted_power_metadata_is_cached_for_the_day():
    """Static contracted powers should not trigger two API calls every poll."""
    api = ContractedPowerStub()

    first = asyncio.run(api.get_casovni_blok())
    second = asyncio.run(api.get_casovni_blok())

    assert first == second
    assert first["casovni_blok_1"] == 5.1
    assert api.site_calls == 1
    assert api.point_calls == 1


def test_merge_interval_blocks_deduplicates_boundary_timestamp():
    """Previous/current month fallback must not duplicate the shared boundary."""
    merged = MojElektroApi._merge_interval_blocks(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-30T00:00:00+02:00",
                        "value": "100.0",
                    },
                    {
                        "timestamp": "2026-10-01T00:00:00+02:00",
                        "value": "110.0",
                    },
                ],
            }
        ],
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-10-01T00:00:00+02:00",
                        "value": "110.0",
                    },
                    {
                        "timestamp": "2026-10-02T00:00:00+02:00",
                        "value": "115.0",
                    },
                ],
            }
        ],
    )

    assert len(merged) == 1
    assert [
        item["timestamp"] for item in merged[0]["intervalReadings"]
    ] == [
        "2026-09-30T00:00:00+02:00",
        "2026-10-01T00:00:00+02:00",
        "2026-10-02T00:00:00+02:00",
    ]


def test_monthly_delta_uses_latest_reading_month_only():
    """Fallback history from the previous month must not inflate monthly totals."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    result = api.sensors_output(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-30T00:00:00+02:00",
                        "value": "1000.0",
                    },
                    {
                        "timestamp": "2026-10-01T00:00:00+02:00",
                        "value": "1010.0",
                    },
                    {
                        "timestamp": "2026-10-02T00:00:00+02:00",
                        "value": "1017.0",
                    },
                ],
            }
        ],
        {"A+_T0": "daily_input"},
        interval=False,
    )

    assert result["daily_input"] == 7.0
    assert result["monthly_input"] == 7.0
    assert (
        api.last_reading_metadata["monthly_input"]["last_reset"]
        == "2026-10-01T00:00:00+02:00"
    )


class DailyFallbackStub(MojElektroApi):
    """Stub daily register requests for month-boundary fallback tests."""

    def __init__(self, current_readings):
        super().__init__("token", "meter", 4, None)
        self.current_readings = current_readings
        self.calls = []
        self._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    async def get_meter_readings(self, tags, *, start_date, end_date):
        self.calls.append((start_date, end_date))
        if start_date.day == 1 and start_date.month == end_date.month:
            return [
                {
                    "readingType": "daily-a-plus",
                    "intervalReadings": self.current_readings,
                }
            ]
        return [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-30T00:00:00+02:00",
                        "value": "100.0",
                    }
                ],
            }
        ]


def test_daily_history_fetches_previous_month_only_when_sparse():
    """Previous-month request should be conditional, not done on every poll."""
    sparse = DailyFallbackStub(
        [
            {
                "timestamp": "2026-10-01T00:00:00+02:00",
                "value": "110.0",
            }
        ]
    )
    enough = DailyFallbackStub(
        [
            {
                "timestamp": "2026-10-01T00:00:00+02:00",
                "value": "110.0",
            },
            {
                "timestamp": "2026-10-02T00:00:00+02:00",
                "value": "115.0",
            },
        ]
    )

    sparse_result = asyncio.run(
        sparse._get_daily_readings(date(2026, 10, 2))
    )
    enough_result = asyncio.run(
        enough._get_daily_readings(date(2026, 10, 2))
    )

    assert len(sparse.calls) == 2
    assert len(sparse_result[0]["intervalReadings"]) == 2
    assert len(enough.calls) == 1
    assert len(enough_result[0]["intervalReadings"]) == 2
