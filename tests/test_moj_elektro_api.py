"""Regression tests for Moj Elektro API processing."""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp

from custom_components.mojelektro.const import (
    FIFTEEN_MINUTE_SENSORS,
    TOTAL_REGISTER_SENSORS,
)
from custom_components.mojelektro.moj_elektro_api import (
    MojElektroApi,
    MojElektroAuthError,
    MojElektroConnectionError,
    MojElektroRequestError,
)


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
        "souporaba_total": 4,
        "souporaba_confirmed": 2,
        "souporaba_in_progress": 1,
        "souporaba_rejected": 1,
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


def test_daily_delta_rejects_missing_calendar_day():
    """Two register states spanning multiple days are not a daily total."""
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
                        "timestamp": "2026-09-19T00:00:00+02:00",
                        "value": "1120.0",
                    },
                    {
                        "timestamp": "2026-09-21T00:00:00+02:00",
                        "value": "1135.0",
                    },
                ],
            }
        ],
        {"A+_T0": "daily_input"},
        interval=False,
    )

    assert "daily_input" not in result
    assert result["monthly_input"] == 135.0


def test_monthly_delta_requires_first_state_of_month():
    """A partial month must not be published as full month-to-date usage."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    result = api.sensors_output(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
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
    assert "monthly_input" not in result


def test_daily_dates_are_normalized_to_slovenian_time():
    """UTC daily states must use their Slovenian calendar date."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    result = api.sensors_output(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-30T22:00:00Z",
                        "value": "1010.0",
                    },
                    {
                        "timestamp": "2026-10-01T22:00:00Z",
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


def test_dynamic_sensor_key_encodes_semantic_signs():
    """Dynamic entity keys should be readable and collision-resistant for signs."""
    assert MojElektroApi.sensor_key_for_tag("P+") == "reading_p_plus_a1fd3d99"
    assert MojElektroApi.sensor_key_for_tag("Q-") == "reading_q_minus_c64bbeb4"
    assert MojElektroApi.sensor_key_for_tag("R+_T0") == "reading_r_plus_t0_cfcc10a8"
    assert (
        MojElektroApi.sensor_key_for_tag("P+")
        != MojElektroApi.sensor_key_for_tag("P_plus")
    )


def test_extra_reading_output_uses_live_catalogue_metadata():
    """Selected advanced readings should inherit semantic metadata from API."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        None,
        extra_reading_tags=("P+",),
    )
    api._tag_by_reading_type = {
        "dynamic-power-import": "P+",
        "dynamic-reactive": "R+",
    }
    api._reading_types_by_tag = {
        "P+": {
            "oznaka": "P+",
            "naziv": "Prejeta 15 minutna delovna moč",
            "perioda": "15 min",
            "vrsta": "KOLICINA",
        },
        "R+": {
            "oznaka": "R+",
            "naziv": "Prejeta jalova energija",
            "perioda": "15 min",
            "vrsta": "KOLICINA",
        },
    }

    result = api.extra_readings_output(
        [
            {
                "readingType": "dynamic-power-import",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-21T10:15:00+02:00",
                        "value": "2.75",
                    }
                ],
            },
            {
                "readingType": "dynamic-reactive",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-21T10:15:00+02:00",
                        "value": "1.25",
                    }
                ],
            },
        ]
    )

    assert result == {"reading_p_plus_a1fd3d99": 2.75}
    assert api.dynamic_sensor_metadata["reading_p_plus_a1fd3d99"] == {
        "tag": "P+",
        "naziv": "Prejeta 15 minutna delovna moč",
        "opis": None,
        "perioda": "15 min",
        "vrsta": "KOLICINA",
        "unit": None,
    }
    assert (
        api.last_reading_metadata["reading_p_plus_a1fd3d99"]["last_reset"]
        == "2026-09-21T10:00:00+02:00"
    )


class FakeHttpResponse:
    """Minimal async HTTP response."""

    def __init__(self, status, payload=None, headers=None, json_error=None):
        self.status = status
        self.payload = payload
        self.headers = headers or {}
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeHttpSession:
    """Minimal aiohttp-like session."""

    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


class FailingHttpSession:
    """HTTP session whose exception text contains sensitive request data."""

    def get(self, *args, **kwargs):
        raise aiohttp.ClientConnectionError("SECRET-EIMM")


def test_rate_limit_error_includes_retry_after():
    """HTTP 429 should be recognizable and preserve Retry-After context."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        FakeHttpSession(
            FakeHttpResponse(
                429,
                headers={"Retry-After": "120"},
            )
        ),
    )

    try:
        asyncio.run(api._request_json("/reading-type"))
        assert False, "Expected MojElektroConnectionError"
    except MojElektroConnectionError as err:
        assert "rate limit" in str(err).lower()
        assert "120" in str(err)


def test_invalid_json_is_translated_to_request_error():
    """Malformed HTTP 200 payload should not escape as an unknown exception."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        FakeHttpSession(
            FakeHttpResponse(
                200,
                json_error=ValueError("invalid json"),
            )
        ),
    )

    try:
        asyncio.run(api._request_json("/reading-type"))
        assert False, "Expected MojElektroRequestError"
    except MojElektroRequestError as err:
        assert "invalid JSON" in str(err)


def test_connection_error_does_not_expose_identifier():
    """Low-level client errors must not leak EIMM through their message."""
    api = MojElektroApi(
        "token",
        "SECRET-EIMM",
        4,
        FailingHttpSession(),
    )

    try:
        asyncio.run(
            api._request_json(
                "/meter-readings",
                params={"usagePoint": "SECRET-EIMM"},
            )
        )
        assert False, "Expected MojElektroConnectionError"
    except MojElektroConnectionError as err:
        rendered = str(err)
        assert "SECRET-EIMM" not in rendered
        assert "/meter-readings" in rendered
        assert err.__cause__ is None


def test_dynamic_metadata_exists_before_first_reading():
    """Selected dynamic entities should have correct metadata even with no data."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        None,
        extra_reading_tags=("P+",),
    )
    api._reading_types_by_tag = {
        "P+": {
            "oznaka": "P+",
            "naziv": "Prejeta 15 minutna delovna moč",
            "opis": "15 minutna moč, A+, kW",
            "perioda": "15 min",
            "vrsta": "KOLICINA",
        }
    }

    api.prepare_dynamic_sensor_metadata()

    assert api.dynamic_sensor_metadata["reading_p_plus_a1fd3d99"] == {
        "tag": "P+",
        "naziv": "Prejeta 15 minutna delovna moč",
        "opis": "15 minutna moč, A+, kW",
        "perioda": "15 min",
        "vrsta": "KOLICINA",
        "unit": None,
    }
    assert "reading_p_plus_a1fd3d99" in api.expected_sensor_names()


def test_dynamic_reading_reset_uses_catalogue_period():
    """Dynamic total readings should reset at timestamp minus API period."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        None,
        extra_reading_tags=("P+",),
    )
    api._tag_by_reading_type = {"dynamic-power-import": "P+"}
    api._reading_types_by_tag = {
        "P+": {
            "oznaka": "P+",
            "perioda": "30 min",
            "vrsta": "KOLICINA",
        }
    }
    api.prepare_dynamic_sensor_metadata()

    api.extra_readings_output(
        [
            {
                "readingType": "dynamic-power-import",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-21T10:30:00+02:00",
                        "value": "2.75",
                    }
                ],
            }
        ]
    )

    assert (
        api.last_reading_metadata["reading_p_plus_a1fd3d99"]["last_reset"]
        == "2026-09-21T10:00:00+02:00"
    )


def test_dynamic_metadata_works_with_current_official_schema_fields():
    """Advanced readings must not require an undocumented unit field."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        None,
        extra_reading_tags=("P+",),
    )
    api._reading_types_by_tag = {
        "P+": {
            "naziv": "Prejeta 15 minutna delovna moč",
            "oznaka": "P+",
            "tip": "MOČ",
            "perioda": "15 min",
            "opis": "15 minutna delovna moč",
            "readingType": "dynamic-power",
            "vrsta": "KOLICINA",
        }
    }

    api.prepare_dynamic_sensor_metadata()

    metadata = api.dynamic_sensor_metadata["reading_p_plus_a1fd3d99"]
    assert metadata["tag"] == "P+"
    assert metadata["perioda"] == "15 min"
    assert metadata["vrsta"] == "KOLICINA"
    assert metadata["unit"] is None


class SequentialDataStub(MojElektroApi):
    """Return one good interval payload followed by an empty payload."""

    def __init__(self):
        super().__init__(
            "token",
            "meter",
            4,
            None,
            enable_daily=False,
            enable_total=False,
            enable_tariff_blocks=False,
            enable_contracted_power=False,
        )
        self._reading_types_by_tag = {
            "A+": {"readingType": "dynamic-a-plus"},
            "A-": {"readingType": "dynamic-a-minus"},
        }
        self._tag_by_reading_type = {
            "dynamic-a-plus": "A+",
            "dynamic-a-minus": "A-",
        }
        self.responses = [
            [
                {
                    "readingType": "dynamic-a-plus",
                    "intervalReadings": [
                        {
                            "timestamp": "2026-09-21T10:15:00+02:00",
                            "value": "0.42",
                        }
                    ],
                }
            ],
            [],
        ]

    async def get_meter_readings(self, tags, *, start_date, end_date):
        return self.responses.pop(0)

    async def get_reading_qualities(self, *, force_refresh=False):
        return []


def test_get_data_preserves_last_good_value_across_empty_success():
    """A successful empty API response must not wipe a previous sensor state."""
    api = SequentialDataStub()

    first = asyncio.run(api.getData())
    second = asyncio.run(api.getData())

    assert first["15min_input"] == 0.42
    assert second["15min_input"] == 0.42
    assert second["15min_output"] is None


def test_expected_entity_set_follows_enabled_options_only():
    """Entity set should be stable and change only through explicit options."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        None,
        enable_15min=False,
        enable_daily=False,
        enable_total=False,
        enable_tariff_blocks=False,
        enable_contracted_power=False,
        enable_souporaba=False,
        extra_reading_tags=("P+",),
    )

    names = api.expected_sensor_names()

    assert names == [
        "reading_p_plus_a1fd3d99",
        "last_published_reading",
    ]


def test_builtin_tags_are_not_duplicated_as_dynamic_entities():
    """Selecting a built-in API tag must not create a second entity."""
    api = MojElektroApi(
        "token",
        "meter",
        4,
        None,
        extra_reading_tags=("A+", "A+_T0", "P+"),
    )

    names = api.expected_sensor_names()

    assert names.count("15min_input") == 1
    assert "reading_a_plus" not in names
    assert "reading_a_plus_t0" not in names
    assert "reading_p_plus_a1fd3d99" in names


def test_dynamic_period_parser_supports_common_api_labels():
    """Dynamic reset periods should accept common Slovenian and ISO labels."""
    assert MojElektroApi._period_to_timedelta("15 min") == timedelta(minutes=15)
    assert MojElektroApi._period_to_timedelta("30 minut") == timedelta(minutes=30)
    assert MojElektroApi._period_to_timedelta("1 ura") == timedelta(hours=1)
    assert MojElektroApi._period_to_timedelta("24 h") == timedelta(hours=24)
    assert MojElektroApi._period_to_timedelta("1 dan") == timedelta(days=1)
    assert MojElektroApi._period_to_timedelta("PT15M") == timedelta(minutes=15)
    assert MojElektroApi._period_to_timedelta("P1D") == timedelta(days=1)
    assert MojElektroApi._period_to_timedelta("unknown") is None


def test_daily_sparse_detection_checks_each_available_core_register():
    """One incomplete present direction should trigger month fallback."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {
        "daily-a-plus": "A+_T0",
        "daily-a-minus": "A-_T0",
    }

    data = [
        {
            "readingType": "daily-a-plus",
            "intervalReadings": [
                {"timestamp": "2026-10-01T00:00:00+02:00", "value": "100"},
                {"timestamp": "2026-10-02T00:00:00+02:00", "value": "110"},
            ],
        },
        {
            "readingType": "daily-a-minus",
            "intervalReadings": [
                {"timestamp": "2026-10-01T00:00:00+02:00", "value": "10"},
            ],
        },
    ]

    assert api._daily_history_is_sparse(data)


def test_daily_sparse_detection_ignores_absent_export_direction():
    """No export block at all should not force fallback when import is sufficient."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    data = [
        {
            "readingType": "daily-a-plus",
            "intervalReadings": [
                {"timestamp": "2026-10-01T00:00:00+02:00", "value": "100"},
                {"timestamp": "2026-10-02T00:00:00+02:00", "value": "110"},
            ],
        }
    ]

    assert not api._daily_history_is_sparse(data)


def test_negative_register_delta_is_not_published():
    """Meter replacement/reset must not create negative energy statistics."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"daily-a-plus": "A+_T0"}

    result = api.sensors_output(
        [
            {
                "readingType": "daily-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-01T00:00:00+02:00",
                        "value": "1200.0",
                    },
                    {
                        "timestamp": "2026-09-20T00:00:00+02:00",
                        "value": "1300.0",
                    },
                    {
                        "timestamp": "2026-09-21T00:00:00+02:00",
                        "value": "10.0",
                    },
                ],
            }
        ],
        {"A+_T0": "daily_input"},
        interval=False,
    )

    assert "daily_input" not in result
    assert "monthly_input" not in result


def test_tariff_day_duplicates_do_not_fake_completeness():
    """Duplicate timestamps must not turn an incomplete day into a complete day."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    start = datetime(
        2026,
        9,
        19,
        0,
        15,
        tzinfo=timezone(timedelta(hours=2)),
    )
    readings = [
        {
            "timestamp": (start + timedelta(minutes=15 * index)).isoformat(),
            "value": "1.0",
        }
        for index in range(95)
    ]
    readings.append(dict(readings[-1]))

    result = api.consumption_by_block(
        [
            {
                "readingType": "dynamic-a-plus",
                "intervalReadings": readings,
            }
        ]
    )

    assert result == {}


def test_tariff_day_uses_date_specific_dst_interval_count():
    """A 92-reading ordinary day is partial, not a complete DST day."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    start = datetime(
        2026,
        9,
        19,
        0,
        15,
        tzinfo=timezone(timedelta(hours=2)),
    )
    readings = [
        {
            "timestamp": (start + timedelta(minutes=15 * index)).isoformat(),
            "value": "1.0",
        }
        for index in range(92)
    ]

    assert api.consumption_by_block(
        [
            {
                "readingType": "dynamic-a-plus",
                "intervalReadings": readings,
            }
        ]
    ) == {}


def test_tariff_days_accept_utc_and_dst_interval_sequences():
    """Complete Slovenian days remain complete across UTC and DST forms."""
    zone = ZoneInfo("Europe/Ljubljana")

    for reading_date, expected_count in (
        (date(2026, 3, 29), 92),
        (date(2026, 9, 19), 96),
        (date(2026, 10, 25), 100),
    ):
        api = MojElektroApi("token", "meter", 4, None)
        api._tag_by_reading_type = {"dynamic-a-plus": "A+"}
        local_start = datetime.combine(reading_date, time.min, tzinfo=zone)
        next_local_start = datetime.combine(
            reading_date + timedelta(days=1),
            time.min,
            tzinfo=zone,
        )
        interval_end = local_start.astimezone(timezone.utc) + timedelta(
            minutes=15
        )
        end = next_local_start.astimezone(timezone.utc)
        readings = []
        while interval_end <= end:
            readings.append(
                {
                    "timestamp": interval_end.isoformat(),
                    "value": "1.0",
                }
            )
            interval_end += timedelta(minutes=15)

        result = api.consumption_by_block(
            [
                {
                    "readingType": "dynamic-a-plus",
                    "intervalReadings": readings,
                }
            ]
        )

        assert len(readings) == expected_count
        assert round(sum(result.values()), 4) == float(expected_count)


def test_interval_reset_uses_real_instant_across_spring_dst():
    """The reset point must not be an imaginary spring-forward local time."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    result = api.sensors_output(
        [
            {
                "readingType": "dynamic-a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-03-29T03:00:00+02:00",
                        "value": "0.25",
                    }
                ],
            }
        ],
        FIFTEEN_MINUTE_SENSORS,
        interval=True,
    )

    assert result["15min_input"] == 0.25
    assert (
        api.last_reading_metadata["15min_input"]["last_reset"]
        == "2026-03-29T01:45:00+01:00"
    )


def test_tariff_day_rejects_off_grid_interval():
    """A non-quarter-hour reading must not count toward day completeness."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"dynamic-a-plus": "A+"}

    start = datetime(
        2026,
        9,
        19,
        0,
        15,
        tzinfo=timezone(timedelta(hours=2)),
    )
    readings = [
        {
            "timestamp": (start + timedelta(minutes=15 * index)).isoformat(),
            "value": "1.0",
        }
        for index in range(95)
    ]
    readings.append(
        {
            "timestamp": "2026-09-19T12:07:00+02:00",
            "value": "1.0",
        }
    )

    assert api.consumption_by_block(
        [
            {
                "readingType": "dynamic-a-plus",
                "intervalReadings": readings,
            }
        ]
    ) == {}


class CombinedIntervalRequestStub(MojElektroApi):
    """Capture interval requests made by getData."""

    def __init__(self):
        super().__init__(
            "token",
            "meter",
            4,
            None,
            enable_daily=False,
            enable_total=False,
            enable_tariff_blocks=False,
            enable_contracted_power=False,
            extra_reading_tags=("P+",),
        )
        self.calls = []
        self._reading_types_by_tag = {
            "A+": {"readingType": "a-plus"},
            "A-": {"readingType": "a-minus"},
            "P+": {
                "readingType": "p-plus",
                "naziv": "Power",
                "perioda": "15 min",
                "vrsta": "KOLICINA",
            },
        }
        self._tag_by_reading_type = {
            "a-plus": "A+",
            "a-minus": "A-",
            "p-plus": "P+",
        }

    async def get_meter_readings(self, tags, *, start_date, end_date):
        self.calls.append(set(tags))
        return []

    async def get_reading_qualities(self, *, force_refresh=False):
        return []


def test_advanced_and_builtin_interval_tags_share_one_api_request():
    """Advanced interval registers should not add a duplicate meter-readings call."""
    api = CombinedIntervalRequestStub()

    asyncio.run(api.getData())

    assert api.calls == [{"A+", "A-", "P+"}]


class MeterMessageTimestampStub(MojElektroApi):
    """Return controlled meter-readings messageCreated timestamps."""

    def __init__(self):
        super().__init__("token", "meter", 4, None)
        self._reading_types_by_tag = {
            "A+": {"readingType": "dynamic-a-plus"},
        }
        self._tag_by_reading_type = {
            "dynamic-a-plus": "A+",
        }
        self.timestamps = [
            "2026-09-22T06:30:00+00:00",
            "2026-09-22T06:00:00+00:00",
        ]

    async def _request_json(self, path, *, params=None):
        assert path == "/meter-readings"
        return {
            "messageCreated": self.timestamps.pop(0),
            "intervalBlocks": [],
        }


def test_meter_message_created_keeps_newest_server_timestamp():
    """Diagnostics should retain the newest API message timestamp seen."""
    api = MeterMessageTimestampStub()

    asyncio.run(
        api.get_meter_readings(
            ["A+"],
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 22),
        )
    )
    first = api.last_meter_message_created

    asyncio.run(
        api.get_meter_readings(
            ["A+"],
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 22),
        )
    )

    assert first is not None
    assert first.isoformat() == "2026-09-22T06:30:00+00:00"
    assert api.last_meter_message_created == first
    assert api.last_meter_response_at is not None


def test_non_finite_interval_values_are_ignored():
    """NaN/Infinity must never be exposed as Home Assistant sensor states."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {
        "a-plus": "A+",
        "a-minus": "A-",
    }

    result = api.sensors_output(
        [
            {
                "readingType": "a-plus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-21T10:15:00+02:00",
                        "value": "NaN",
                    }
                ],
            },
            {
                "readingType": "a-minus",
                "intervalReadings": [
                    {
                        "timestamp": "2026-09-21T10:15:00+02:00",
                        "value": "Infinity",
                    }
                ],
            },
        ],
        FIFTEEN_MINUTE_SENSORS,
        interval=True,
    )

    assert result == {}


def test_non_finite_contracted_power_becomes_unavailable():
    """Malformed static power values should be represented as unavailable."""
    result = MojElektroApi._extract_casovni_bloki(
        [
            {
                "datumOd": "2020-01-01T00:00:00+01:00",
                "datumDo": "2035-12-31T23:59:59+01:00",
                "veljavnost": True,
                "casovniBlok1": "NaN",
                "casovniBlok2": "5.2",
                "casovniBlok3": "5.3",
                "casovniBlok4": "5.4",
                "casovniBlok5": "5.5",
            }
        ]
    )

    assert result["casovni_blok_1"] is None
    assert result["casovni_blok_2"] == 5.2


class OptionalAuthStub(MojElektroApi):
    """Exercise optional endpoint authorization behavior."""

    def __init__(self, *, core_enabled):
        super().__init__(
            "token",
            "meter",
            4,
            None,
            enable_15min=core_enabled,
            enable_daily=False,
            enable_total=False,
            enable_tariff_blocks=False,
            enable_contracted_power=True,
            enable_souporaba=False,
        )
        self._reading_types_by_tag = {
            "A+": {"readingType": "a-plus"},
            "A-": {"readingType": "a-minus"},
        }
        self._tag_by_reading_type = {
            "a-plus": "A+",
            "a-minus": "A-",
        }

    async def get_meter_readings(self, tags, *, start_date, end_date):
        return []

    async def get_casovni_blok(self):
        raise MojElektroAuthError("metadata access denied")


def test_optional_auth_failure_is_nonfatal_after_core_access_succeeds():
    """Optional 403 must not force reauth after meter-readings already worked."""
    api = OptionalAuthStub(core_enabled=True)

    result = asyncio.run(api.getData())

    assert "15min_input" in result
    assert result["casovni_blok_1"] is None


def test_optional_auth_failure_propagates_without_core_verification():
    """If only the optional endpoint is used, its auth error must still reauth."""
    api = OptionalAuthStub(core_enabled=False)

    try:
        asyncio.run(api.getData())
        assert False, "Expected MojElektroAuthError"
    except MojElektroAuthError:
        pass


def test_api_error_path_redacts_meter_identifiers():
    """EIMM/GSRN values must not be included in log-safe endpoint labels."""
    assert MojElektroApi._safe_path_label(
        "/merilno-mesto/SECRET-EIMM"
    ) == "/merilno-mesto/{identifikator}"
    assert MojElektroApi._safe_path_label(
        "/merilna-tocka/SECRET-GSRN"
    ) == "/merilna-tocka/{gsrn}"
    assert MojElektroApi._safe_path_label(
        "/souporaba/12345"
    ) == "/souporaba/{sifra}"
    assert MojElektroApi._safe_path_label(
        "/reading-type"
    ) == "/reading-type"


def test_request_error_does_not_expose_identifier():
    """HTTP request errors must use the redacted endpoint label."""
    api = MojElektroApi(
        "token",
        "SECRET-EIMM",
        4,
        FakeHttpSession(FakeHttpResponse(404)),
    )

    try:
        asyncio.run(
            api._request_json("/merilno-mesto/SECRET-EIMM")
        )
        assert False, "Expected MojElektroRequestError"
    except MojElektroRequestError as err:
        rendered = str(err)
        assert "SECRET-EIMM" not in rendered
        assert "/merilno-mesto/{identifikator}" in rendered


class NoDataNoFeaturesStub(MojElektroApi):
    """Ensure diagnostics-only mode makes no meter-reading request."""

    def __init__(self):
        super().__init__(
            "token",
            "meter",
            4,
            None,
            enable_15min=False,
            enable_daily=False,
            enable_total=False,
            enable_tariff_blocks=False,
            enable_contracted_power=False,
            enable_souporaba=False,
            extra_reading_tags=(),
        )
        self.meter_calls = 0

    async def get_meter_readings(self, tags, *, start_date, end_date):
        self.meter_calls += 1
        raise AssertionError("meter-readings should not be called")


def test_diagnostics_only_mode_starts_without_measurement_data():
    """All data groups may be disabled without breaking integration setup."""
    api = NoDataNoFeaturesStub()

    result = asyncio.run(api.getData())

    assert api.meter_calls == 0
    assert result == {
        "last_published_reading": None,
    }


class StaleCatalogueRetryStub(MojElektroApi):
    """Simulate a cached readingType ID becoming invalid upstream."""

    def __init__(self):
        super().__init__("token", "meter", 4, None)
        self._reading_types_by_tag = {
            "A+": {"readingType": "old-id"},
        }
        self._tag_by_reading_type = {"old-id": "A+"}
        self.force_refresh_calls = 0
        self.meter_params = []

    async def get_reading_types(self, *, force_refresh=False):
        if force_refresh:
            self.force_refresh_calls += 1
            self._reading_types_by_tag = {
                "A+": {"readingType": "new-id"},
            }
            self._tag_by_reading_type = {"new-id": "A+"}
        return self._reading_types_by_tag

    async def _request_json(self, path, *, params=None):
        assert path == "/meter-readings"
        self.meter_params.append(list(params))
        options = [
            value
            for key, value in params
            if key == "option"
        ]
        if options == ["ReadingType=old-id"]:
            raise MojElektroRequestError("old register id rejected")
        assert options == ["ReadingType=new-id"]
        return {"intervalBlocks": []}


def test_stale_reading_type_catalogue_refreshes_and_retries_once():
    """Cached opaque IDs should self-heal when upstream replaces them."""
    api = StaleCatalogueRetryStub()

    result = asyncio.run(
        api.get_meter_readings(
            ["A+"],
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 22),
        )
    )

    assert result == []
    assert api.force_refresh_calls == 1
    assert len(api.meter_params) == 2
    assert ("option", "ReadingType=old-id") in api.meter_params[0]
    assert ("option", "ReadingType=new-id") in api.meter_params[1]


def test_reading_sort_uses_absolute_time_across_dst_fallback():
    """Repeated local hour must be ordered by timezone-aware instant."""
    api = MojElektroApi("token", "meter", 4, None)
    api._tag_by_reading_type = {"a-plus": "A+"}

    result = api.sensors_output(
        [
            {
                "readingType": "a-plus",
                "intervalReadings": [
                    {
                        # 00:30 UTC
                        "timestamp": "2026-10-25T02:30:00+02:00",
                        "value": "1.0",
                    },
                    {
                        # 01:15 UTC: later even though local clock says 02:15
                        "timestamp": "2026-10-25T02:15:00+01:00",
                        "value": "2.0",
                    },
                ],
            }
        ],
        FIFTEEN_MINUTE_SENSORS,
        interval=True,
    )

    assert result["15min_input"] == 2.0


def test_naive_or_invalid_timestamps_are_ignored():
    """OpenAPI requires offsets; ambiguous/invalid timestamps must not be used."""
    readings = MojElektroApi._sorted_readings(
        {
            "intervalReadings": [
                {"timestamp": "2026-09-21T10:15:00", "value": "1"},
                {"timestamp": "not-a-date", "value": "2"},
                {
                    "timestamp": "2026-09-21T10:30:00+02:00",
                    "value": "3",
                },
            ]
        }
    )

    assert readings == [
        {
            "timestamp": "2026-09-21T10:30:00+02:00",
            "value": "3",
        }
    ]


def test_source_metadata_timestamp_uses_absolute_dst_order():
    """Freshness metadata must choose the latest instant, not max ISO text."""
    api = MojElektroApi("token", "meter", 4, None)

    api._remember_reading_metadata(
        "test_sensor",
        {
            "timestamp": "2026-10-25T02:30:00+02:00",
            "value": "1",
        },
        {
            "timestamp": "2026-10-25T02:15:00+01:00",
            "value": "2",
        },
    )

    assert (
        api.last_reading_metadata["test_sensor"]["source_timestamp"]
        == "2026-10-25T02:15:00+01:00"
    )


def test_preferred_reading_type_accepts_official_variants():
    """Catalogue rows without primary readingType should remain usable."""
    assert MojElektroApi._preferred_reading_type(
        {
            "readingType": "primary",
            "readingTypeBrezObracuna": "non-billing",
            "readingTypeObracun": "billing",
        }
    ) == "primary"
    assert MojElektroApi._preferred_reading_type(
        {
            "readingTypeBrezObracuna": "non-billing",
            "readingTypeObracun": "billing",
        }
    ) == "non-billing"
    assert MojElektroApi._preferred_reading_type(
        {
            "readingTypeObracun": "billing",
        }
    ) == "billing"
    assert MojElektroApi._preferred_reading_type({}) is None


class ReadingTypeVariantStub(MojElektroApi):
    """Expose a catalogue row that has only a non-primary official ID."""

    async def _request_json(self, path, *, params=None):
        assert path == "/reading-type"
        return [
            {
                "oznaka": "P+",
                "naziv": "Power",
                "readingTypeBrezObracuna": "variant-id",
                "vrsta": "KOLICINA",
            }
        ]


def test_reading_type_catalogue_keeps_non_primary_variant():
    """Official variant IDs must remain queryable even without readingType."""
    api = ReadingTypeVariantStub("token", "meter", 4, None)

    catalogue = asyncio.run(api.get_reading_types())

    assert "P+" in catalogue
    params, missing = api._build_meter_reading_params(
        ["P+"],
        start_date=date(2026, 9, 20),
        end_date=date(2026, 9, 22),
        reading_types=catalogue,
    )
    assert missing == []
    assert ("option", "ReadingType=variant-id") in params


class DuplicateReadingTypeRowsStub(MojElektroApi):
    """Return split/duplicate rows for one semantic tag."""

    async def _request_json(self, path, *, params=None):
        assert path == "/reading-type"
        return [
            {
                "oznaka": "P+",
                "naziv": "Power",
                "readingTypeBrezObracuna": "non-billing-id",
                "vrsta": "KOLICINA",
            },
            {
                "oznaka": "P+",
                "naziv": "Power duplicate",
                "readingTypeObracun": "billing-id",
                "vrsta": "KOLICINA",
            },
        ]


def test_duplicate_reading_type_rows_merge_without_last_row_wins():
    """Split catalogue rows should merge variant IDs and keep stable metadata."""
    api = DuplicateReadingTypeRowsStub("token", "meter", 4, None)

    catalogue = asyncio.run(api.get_reading_types())
    row = catalogue["P+"]

    assert row["naziv"] == "Power"
    assert row["readingTypeBrezObracuna"] == "non-billing-id"
    assert row["readingTypeObracun"] == "billing-id"
    assert api._tag_by_reading_type == {
        "non-billing-id": "P+",
        "billing-id": "P+",
    }


class CoreValidationStub(MojElektroApi):
    """Validate using core reading endpoints only."""

    def __init__(self):
        super().__init__("token", "meter", 4, None)
        self.reading_calls = 0

    async def get_reading_types(self, *, force_refresh=False):
        return {
            "A+": {
                "readingType": "a-plus",
            }
        }

    async def get_meter_readings(self, tags, *, start_date, end_date):
        self.reading_calls += 1
        assert tags == ["A+"]
        return []

    async def get_meter_site(self):
        raise AssertionError("optional meter metadata must not validate core access")


def test_validate_token_uses_core_meter_readings_and_accepts_empty_success():
    """A valid account with no fresh readings should still pass setup."""
    api = CoreValidationStub()

    assert asyncio.run(api.validate_token())
    assert api.reading_calls == 1


def test_latest_source_timestamp_ignores_naive_values():
    """Freshness lookup should ignore timestamps without timezone offsets."""
    api = MojElektroApi("token", "meter", 4, None)
    api.last_reading_metadata = {
        "bad": {
            "source_timestamp": "2026-10-25T02:30:00",
        },
        "good": {
            "source_timestamp": "2026-10-25T02:15:00+01:00",
        },
    }

    latest = api.latest_source_timestamp()

    assert latest is not None
    assert latest.isoformat() == "2026-10-25T02:15:00+01:00"


class MissingContractedPowerStub(MojElektroApi):
    """Stub a meter that has no OMTO contracted-power metadata."""

    def __init__(self):
        super().__init__("token", "meter", 4, None)
        self.site_calls = 0

    async def get_meter_site(self):
        self.site_calls += 1
        return {"merilneTocke": []}


def test_missing_contracted_power_is_cached_for_the_day():
    """A successful no-data metadata lookup should not repeat every poll."""
    api = MissingContractedPowerStub()

    first = asyncio.run(api.get_casovni_blok())
    second = asyncio.run(api.get_casovni_blok())

    assert first == {}
    assert second == {}
    assert api.site_calls == 1
