"""Async client and data processing for the Moj Elektro API."""

from __future__ import annotations

import aiohttp
from datetime import date, datetime, timedelta
import logging
from typing import Any

from .const import (
    API_BASE_URL,
    CONTRACTED_POWER_SENSORS,
    DAILY_SENSORS,
    DEFAULT_ENABLE_15MIN,
    DEFAULT_ENABLE_CONTRACTED_POWER,
    DEFAULT_ENABLE_DAILY,
    DEFAULT_ENABLE_TOTAL,
    DEFAULT_ENABLE_TARIFF_BLOCKS,
    DEFAULT_ENABLE_SOUPORABA,
    DEFAULT_LOOKBACK_DAYS,
    FIFTEEN_MINUTE_SENSORS,
    TOTAL_REGISTER_SENSORS,
    TARIFF_BLOCK_SENSORS,
    SOUPORABA_SENSORS,
)

_LOGGER = logging.getLogger(__name__)


class MojElektroError(Exception):
    """Base Moj Elektro API error."""


class MojElektroAuthError(MojElektroError):
    """Authentication or authorization failed."""


class MojElektroRequestError(MojElektroError):
    """The API rejected the request or meter identifier."""


class MojElektroConnectionError(MojElektroError):
    """The API could not be reached or returned a server error."""


class MojElektroApi:
    """Interact with the official Moj Elektro API."""

    def __init__(
        self,
        token: str,
        meter_id: str,
        decimal: int | None,
        session,
        *,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        enable_15min: bool = DEFAULT_ENABLE_15MIN,
        enable_daily: bool = DEFAULT_ENABLE_DAILY,
        enable_total: bool = DEFAULT_ENABLE_TOTAL,
        enable_tariff_blocks: bool = DEFAULT_ENABLE_TARIFF_BLOCKS,
        enable_contracted_power: bool = DEFAULT_ENABLE_CONTRACTED_POWER,
        enable_souporaba: bool = DEFAULT_ENABLE_SOUPORABA,
    ) -> None:
        self.token = token
        self.meter_id = meter_id
        self.decimal = int(decimal) if decimal is not None else 4
        self.session = session
        self.lookback_days = int(lookback_days)
        self.enable_15min = bool(enable_15min)
        self.enable_daily = bool(enable_daily)
        self.enable_total = bool(enable_total)
        self.enable_tariff_blocks = bool(enable_tariff_blocks)
        self.enable_contracted_power = bool(enable_contracted_power)
        self.enable_souporaba = bool(enable_souporaba)

        self.last_data: dict[str, float | None] | None = None
        self._reading_types_by_tag: dict[str, dict[str, Any]] | None = None
        self._tag_by_reading_type: dict[str, str] = {}
        self._reading_qualities: list[dict[str, Any]] | None = None
        self._reading_quality_descriptions: dict[str, str] = {}
        self.last_reading_metadata: dict[str, dict[str, Any]] = {}

    @property
    def headers(self) -> dict[str, str]:
        """Return request headers."""
        return {
            "accept": "application/json",
            "X-API-TOKEN": self.token,
        }

    async def _request_json(
        self,
        path: str,
        *,
        params: list[tuple[str, str]] | dict[str, str] | None = None,
    ) -> Any:
        """Fetch and validate JSON from the Moj Elektro API."""
        url = f"{API_BASE_URL}{path}"
        try:
            async with self.session.get(
                url,
                headers=self.headers,
                params=params,
            ) as response:
                if response.status == 200:
                    return await response.json(content_type=None)
                if response.status in (401, 403):
                    raise MojElektroAuthError(
                        f"Moj Elektro authentication failed (HTTP {response.status})"
                    )
                if response.status in (400, 404):
                    raise MojElektroRequestError(
                        f"Moj Elektro rejected {path} (HTTP {response.status})"
                    )
                raise MojElektroConnectionError(
                    f"Moj Elektro API returned HTTP {response.status} for {path}"
                )
        except aiohttp.ClientError as err:
            raise MojElektroConnectionError(
                f"Error connecting to Moj Elektro: {err}"
            ) from err

    async def validate_token(self) -> bool:
        """Validate the token and access to the configured metering point."""
        await self.get_meter_site()
        return True

    async def get_reading_types(
        self, *, force_refresh: bool = False
    ) -> dict[str, dict[str, Any]]:
        """Return the official reading-type catalogue keyed by semantic label."""
        if self._reading_types_by_tag is not None and not force_refresh:
            return self._reading_types_by_tag

        payload = await self._request_json("/reading-type")
        if not isinstance(payload, list):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid /reading-type payload"
            )

        by_tag: dict[str, dict[str, Any]] = {}
        by_reading_type: dict[str, str] = {}

        for item in payload:
            if not isinstance(item, dict):
                continue

            tag = item.get("oznaka")
            reading_type = item.get("readingType")
            if not tag or not reading_type:
                continue

            by_tag[str(tag)] = item
            for key in (
                "readingType",
                "readingTypeBrezObracuna",
                "readingTypeObracun",
            ):
                value = item.get(key)
                if value:
                    by_reading_type[str(value)] = str(tag)

        if not by_tag:
            raise MojElektroRequestError(
                "Moj Elektro returned no usable reading types"
            )

        self._reading_types_by_tag = by_tag
        self._tag_by_reading_type = by_reading_type
        return by_tag

    async def get_reading_qualities(
        self, *, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """Return the official reading-quality catalogue."""
        if self._reading_qualities is not None and not force_refresh:
            return self._reading_qualities

        payload = await self._request_json("/reading-qualities")
        if not isinstance(payload, list):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid /reading-qualities payload"
            )

        self._reading_qualities = [
            item for item in payload if isinstance(item, dict)
        ]
        self._reading_quality_descriptions = {
            str(item["readingQualityType"]): str(item.get("description", ""))
            for item in self._reading_qualities
            if item.get("readingQualityType")
        }
        return self._reading_qualities

    async def get_meter_site(self) -> dict[str, Any]:
        """Return metadata for the configured metering point."""
        payload = await self._request_json(f"/merilno-mesto/{self.meter_id}")
        if not isinstance(payload, dict):
            raise MojElektroRequestError(
                "Moj Elektro returned invalid metering-point metadata"
            )
        return payload

    async def get_meter_point(self, gsrn: str) -> dict[str, Any]:
        """Return metadata for a GSRN meter point."""
        payload = await self._request_json(f"/merilna-tocka/{gsrn}")
        if not isinstance(payload, dict):
            raise MojElektroRequestError(
                "Moj Elektro returned invalid meter-point metadata"
            )
        return payload

    async def get_souporaba(self) -> list[dict[str, Any]]:
        """Return sharing relationships available to the authenticated user."""
        payload = await self._request_json("/souporaba")
        if not isinstance(payload, list):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid /souporaba payload"
            )
        return [item for item in payload if isinstance(item, dict)]

    async def get_souporaba_detail(self, code: int) -> dict[str, Any]:
        """Return details for one sharing relationship."""
        payload = await self._request_json(f"/souporaba/{int(code)}")
        if not isinstance(payload, dict):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid souporaba detail payload"
            )
        return payload

    async def get_souporaba_network_charges(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return network-charge periods for a sharing organizer."""
        payload = await self._request_json(
            "/souporaba/pregled-obracunov-omreznine",
            params={
                "datumOd": start_date.isoformat(),
                "datumDo": end_date.isoformat(),
            },
        )
        if not isinstance(payload, list):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid network-charge overview payload"
            )
        return [item for item in payload if isinstance(item, dict)]

    async def get_meter_readings(
        self,
        tags: list[str] | tuple[str, ...] | set[str],
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch readings for semantic register labels discovered at runtime."""
        reading_types = await self.get_reading_types()

        params: list[tuple[str, str]] = [
            ("usagePoint", self.meter_id),
            ("startTime", start_date.isoformat()),
            ("endTime", end_date.isoformat()),
        ]

        missing_tags: list[str] = []
        for tag in tags:
            definition = reading_types.get(tag)
            reading_type = definition.get("readingType") if definition else None
            if not reading_type:
                missing_tags.append(tag)
                continue
            params.append(("option", f"ReadingType={reading_type}"))

        if missing_tags:
            _LOGGER.warning(
                "Moj Elektro no longer exposes requested reading types: %s",
                ", ".join(sorted(missing_tags)),
            )

        if len(params) == 3:
            return []

        payload = await self._request_json("/meter-readings", params=params)
        if not isinstance(payload, dict):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid meter-readings payload"
            )

        interval_blocks = payload.get("intervalBlocks", [])
        if not isinstance(interval_blocks, list):
            raise MojElektroRequestError(
                "Moj Elektro returned an invalid intervalBlocks payload"
            )

        return [
            block for block in interval_blocks if isinstance(block, dict)
        ]

    async def getMeterReadings(self, rType=None):
        """Compatibility wrapper for code using the 0.2.x API method."""
        today = datetime.now().date()
        if rType == "15min":
            return await self.get_meter_readings(
                list(FIFTEEN_MINUTE_SENSORS),
                start_date=today - timedelta(days=self.lookback_days),
                end_date=today,
            )

        start_date = (
            today - timedelta(days=1)
            if today.day == 1
            else today.replace(day=1)
        )
        return await self.get_meter_readings(
            list(DAILY_SENSORS),
            start_date=start_date,
            end_date=today,
        )

    async def getData(self) -> dict[str, float | None]:
        """Fetch the configured sensor groups and preserve prior good values."""
        today = datetime.now().date()
        sensor_return: dict[str, float | None] = {}

        fifteen_data: list[dict[str, Any]] = []
        daily_data: list[dict[str, Any]] = []

        requested_15_tags: set[str] = set()
        if self.enable_15min:
            requested_15_tags.update(FIFTEEN_MINUTE_SENSORS)
        if self.enable_tariff_blocks:
            requested_15_tags.add("A+")

        if requested_15_tags:
            fifteen_data = await self.get_meter_readings(
                requested_15_tags,
                start_date=today - timedelta(days=self.lookback_days),
                end_date=today,
            )

        if self.enable_daily or self.enable_total:
            daily_start = (
                today - timedelta(days=1)
                if today.day == 1
                else today.replace(day=1)
            )
            daily_data = await self.get_meter_readings(
                list(DAILY_SENSORS),
                start_date=daily_start,
                end_date=today,
            )

        if fifteen_data or daily_data:
            try:
                await self.get_reading_qualities()
            except MojElektroAuthError:
                raise
            except MojElektroError as err:
                _LOGGER.warning(
                    "Unable to load Moj Elektro reading-quality descriptions: %s",
                    err,
                )

        if self.enable_15min:
            sensor_return.update(
                self.sensors_output(
                    fifteen_data,
                    FIFTEEN_MINUTE_SENSORS,
                    interval=True,
                )
            )

        if self.enable_daily:
            sensor_return.update(
                self.sensors_output(
                    daily_data,
                    DAILY_SENSORS,
                    interval=False,
                )
            )

        if self.enable_total:
            sensor_return.update(
                self.total_registers_output(
                    daily_data,
                    TOTAL_REGISTER_SENSORS,
                )
            )

        if self.enable_tariff_blocks:
            sensor_return.update(self.consumption_by_block(fifteen_data))

        if self.enable_contracted_power:
            sensor_return.update(await self.get_casovni_blok())

        if self.enable_souporaba:
            try:
                sensor_return.update(
                    self.souporaba_summary_output(
                        await self.get_souporaba()
                    )
                )
            except MojElektroAuthError:
                raise
            except MojElektroError as err:
                _LOGGER.warning(
                    "Unable to update Moj Elektro souporaba summary: %s",
                    err,
                )

        for sensor_name in self.expected_sensor_names():
            previous_value = (
                self.last_data.get(sensor_name)
                if self.last_data is not None
                else None
            )
            sensor_return.setdefault(sensor_name, previous_value)

        self.last_data = sensor_return
        return sensor_return

    def expected_sensor_names(self) -> list[str]:
        """Return sensor keys enabled by the current options."""
        names: list[str] = []

        if self.enable_15min:
            names.extend(FIFTEEN_MINUTE_SENSORS.values())

        if self.enable_daily:
            for sensor in DAILY_SENSORS.values():
                names.append(sensor)
                names.append(sensor.replace("daily_", "monthly_", 1))

        if self.enable_total:
            names.extend(TOTAL_REGISTER_SENSORS.values())

        if self.enable_tariff_blocks:
            names.extend(TARIFF_BLOCK_SENSORS.values())

        if self.enable_contracted_power:
            names.extend(CONTRACTED_POWER_SENSORS)

        if self.enable_souporaba:
            names.extend(SOUPORABA_SENSORS.values())

        return names

    def _tag_for_reading_type(self, reading_type: str) -> str | None:
        """Resolve an opaque API readingType ID back to its semantic label."""
        return self._tag_by_reading_type.get(reading_type)

    @staticmethod
    def _sorted_readings(block: dict[str, Any]) -> list[dict[str, Any]]:
        """Return timestamped readings in chronological order."""
        readings = block.get("intervalReadings") or []
        if not isinstance(readings, list):
            return []
        return sorted(
            (item for item in readings if isinstance(item, dict)),
            key=lambda item: str(item.get("timestamp", "")),
        )

    def _quality_details(self, *readings: dict[str, Any]) -> list[dict[str, str]]:
        """Return de-duplicated reading-quality codes and descriptions."""
        details: dict[str, dict[str, str]] = {}
        for reading in readings:
            qualities = reading.get("readingQualities") or []
            if not isinstance(qualities, list):
                continue
            for quality in qualities:
                if not isinstance(quality, dict):
                    continue
                code = quality.get("readingQualityType")
                if not code:
                    continue
                code = str(code)
                detail = {"code": code}
                description = self._reading_quality_descriptions.get(code)
                if description:
                    detail["description"] = description
                details[code] = detail
        return list(details.values())

    def _remember_reading_metadata(
        self,
        sensor: str,
        *readings: dict[str, Any],
        last_reset: str | None = None,
        source_date: str | None = None,
    ) -> None:
        """Remember non-sensitive source metadata for diagnostics/state handling."""
        metadata: dict[str, Any] = {}
        timestamps = [
            str(reading.get("timestamp"))
            for reading in readings
            if reading.get("timestamp")
        ]
        if timestamps:
            metadata["source_timestamp"] = max(timestamps)
        if source_date:
            metadata["source_date"] = source_date
        if last_reset:
            metadata["last_reset"] = last_reset

        quality_details = self._quality_details(*readings)
        metadata["reading_valid"] = not quality_details
        metadata["reading_qualities"] = quality_details
        self.last_reading_metadata[sensor] = metadata

    def sensors_output(
        self,
        data: list[dict[str, Any]],
        sensor_map: dict[str, str],
        *,
        interval: bool,
    ) -> dict[str, float]:
        """Convert API interval blocks to stable Home Assistant sensor values."""
        sensor_output: dict[str, float] = {}

        if not data:
            return sensor_output

        for block in data:
            reading_type = str(block.get("readingType", ""))
            tag = self._tag_for_reading_type(reading_type)
            if tag is None:
                _LOGGER.debug("Unknown reading type returned by API: %s", reading_type)
                continue

            sensor = sensor_map.get(tag)
            if sensor is None:
                continue

            readings = self._sorted_readings(block)
            if not readings:
                continue

            if interval:
                latest = readings[-1]
                try:
                    sensor_output[sensor] = round(
                        float(latest["value"]),
                        self.decimal,
                    )
                    self._remember_reading_metadata(
                        sensor,
                        latest,
                        last_reset=str(latest.get("timestamp") or "") or None,
                    )
                except (KeyError, TypeError, ValueError):
                    _LOGGER.debug("Invalid latest interval reading for %s", sensor)
                continue

            if len(readings) < 2:
                _LOGGER.debug("Not enough daily readings for %s", sensor)
                continue

            try:
                first_value = float(readings[0]["value"])
                previous_value = float(readings[-2]["value"])
                latest_value = float(readings[-1]["value"])
            except (KeyError, TypeError, ValueError):
                _LOGGER.debug("Invalid daily readings for %s", sensor)
                continue

            sensor_output[sensor] = round(
                latest_value - previous_value,
                self.decimal,
            )
            monthly_sensor = sensor.replace("daily_", "monthly_", 1)
            sensor_output[monthly_sensor] = round(
                latest_value - first_value,
                self.decimal,
            )

            self._remember_reading_metadata(
                sensor,
                readings[-2],
                readings[-1],
                last_reset=str(readings[-2].get("timestamp") or "") or None,
            )
            self._remember_reading_metadata(
                monthly_sensor,
                readings[0],
                readings[-1],
                last_reset=str(readings[0].get("timestamp") or "") or None,
            )

        return sensor_output

    def total_registers_output(
        self,
        data: list[dict[str, Any]],
        sensor_map: dict[str, str],
    ) -> dict[str, float]:
        """Expose the latest cumulative meter-register values."""
        output: dict[str, float] = {}

        for block in data or []:
            reading_type = str(block.get("readingType", ""))
            tag = self._tag_for_reading_type(reading_type)
            sensor = sensor_map.get(tag) if tag else None
            if sensor is None:
                continue

            readings = self._sorted_readings(block)
            if not readings:
                continue

            latest = readings[-1]
            try:
                output[sensor] = round(float(latest["value"]), self.decimal)
            except (KeyError, TypeError, ValueError):
                continue

            self._remember_reading_metadata(sensor, latest)

        return output

    @staticmethod
    def souporaba_summary_output(
        items: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Return privacy-safe counts by souporaba status."""
        counts = {
            "total": len(items),
            "POTRJENA": 0,
            "V_IZVAJANJU": 0,
            "ZAVRNJENA": 0,
        }

        for item in items:
            status = item.get("statusZahteve")
            if status in counts:
                counts[status] += 1

        return {
            sensor_name: float(counts[key])
            for key, sensor_name in SOUPORABA_SENSORS.items()
        }

    async def get_casovni_blok(self) -> dict[str, float | None]:
        """Get currently valid contracted powers for tariff blocks."""
        try:
            meter_site = await self.get_meter_site()
            gsrn_omto = self._extract_gsrn_omto(
                meter_site.get("merilneTocke", [])
            )
            if not gsrn_omto:
                return {}

            meter_point = await self.get_meter_point(gsrn_omto)
            return self._extract_casovni_bloki(
                meter_point.get("dogovorjeneMoci", [])
            )
        except MojElektroAuthError:
            raise
        except MojElektroError as err:
            _LOGGER.warning("Unable to update contracted powers: %s", err)
            return {}

    @staticmethod
    def _extract_gsrn_omto(merilne_tocke) -> str | None:
        """Extract the GSRN value whose type is OMTO."""
        if not isinstance(merilne_tocke, list):
            return None
        for point in merilne_tocke:
            if isinstance(point, dict) and point.get("vrsta") == "OMTO":
                gsrn = point.get("gsrn")
                return str(gsrn) if gsrn else None
        return None

    @staticmethod
    def _extract_casovni_bloki(dogovorjene_moci) -> dict[str, float | None]:
        """Extract contracted powers valid on the current date."""
        current_date = datetime.now().date()

        if not isinstance(dogovorjene_moci, list):
            return {}

        for power in dogovorjene_moci:
            if not isinstance(power, dict):
                continue
            try:
                datum_od = datetime.fromisoformat(
                    str(power.get("datumOd")).replace("Z", "+00:00")
                ).date()
                datum_do = datetime.fromisoformat(
                    str(power.get("datumDo")).replace("Z", "+00:00")
                ).date()
            except (TypeError, ValueError):
                continue

            if power.get("veljavnost") and datum_od <= current_date <= datum_do:
                result: dict[str, float | None] = {}
                for index in range(1, 6):
                    raw_value = power.get(f"casovniBlok{index}")
                    try:
                        value = (
                            float(raw_value)
                            if raw_value is not None
                            else None
                        )
                    except (TypeError, ValueError):
                        value = None
                    result[f"casovni_blok_{index}"] = value
                return result

        return {}

    def consumption_by_block(
        self,
        data: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calculate imported energy by tariff block for the latest complete day."""
        if not data:
            return {}

        readings_by_date: dict[date, list[tuple[datetime, dict[str, Any]]]] = {}

        for block in data:
            reading_type = str(block.get("readingType", ""))
            if self._tag_for_reading_type(reading_type) != "A+":
                continue

            for reading in self._sorted_readings(block):
                try:
                    timestamp = str(reading["timestamp"])
                    interval_end = datetime.fromisoformat(
                        timestamp.replace("Z", "+00:00")
                    )
                    interval_start = interval_end - timedelta(minutes=15)
                    float(reading["value"])
                except (KeyError, TypeError, ValueError):
                    continue

                readings_by_date.setdefault(
                    interval_start.date(),
                    [],
                ).append((interval_start, reading))

        complete_dates = [
            reading_date
            for reading_date, readings in readings_by_date.items()
            if len(readings) in (92, 96, 100)
        ]
        if not complete_dates:
            _LOGGER.debug(
                "No complete 15-minute day available for tariff-block totals"
            )
            return {}

        selected_date = max(complete_dates)
        selected_readings = readings_by_date[selected_date]
        blocks_sums = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}

        for _interval_start, reading in selected_readings:
            try:
                timestamp = str(reading["timestamp"])
                value = float(reading["value"])
                block_num = self.calculate_tariff(timestamp)
            except (KeyError, TypeError, ValueError):
                continue

            if block_num in blocks_sums:
                blocks_sums[block_num] += value

        reset_at = min(
            interval_start for interval_start, _reading in selected_readings
        ).isoformat()
        source_readings = tuple(
            reading for _interval_start, reading in selected_readings
        )

        result = {
            sensor_name: round(blocks_sums[block_num], self.decimal)
            for block_num, sensor_name in TARIFF_BLOCK_SENSORS.items()
        }

        for sensor_name in result:
            self._remember_reading_metadata(
                sensor_name,
                *source_readings,
                last_reset=reset_at,
                source_date=selected_date.isoformat(),
            )

        return result

    @staticmethod
    def calculate_easter(year: int) -> date:
        """Calculate Easter Sunday for a given year."""
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    @classmethod
    def is_weekend_or_holiday(cls, value: datetime) -> bool:
        """Check whether a timestamp falls on a weekend or Slovenian holiday."""
        if value.weekday() in (5, 6):
            return True

        public_holidays = {
            (1, 1),
            (1, 2),
            (2, 8),
            (4, 27),
            (5, 1),
            (5, 2),
            (6, 25),
            (8, 15),
            (10, 31),
            (11, 1),
            (12, 25),
            (12, 26),
        }

        easter_sunday = cls.calculate_easter(value.year)
        easter_saturday = easter_sunday - timedelta(days=1)
        easter_monday = easter_sunday + timedelta(days=1)
        public_holidays.add(
            (easter_saturday.month, easter_saturday.day)
        )
        public_holidays.add(
            (easter_monday.month, easter_monday.day)
        )

        return (value.month, value.day) in public_holidays

    @classmethod
    def calculate_tariff(cls, timestamp: str) -> int:
        """Calculate the Slovenian network tariff block for a reading."""
        reading_time = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ) - timedelta(minutes=15)

        month = reading_time.month
        hour = reading_time.hour
        is_high_season = month in (11, 12, 1, 2)
        weekend_or_holiday = cls.is_weekend_or_holiday(reading_time)

        tariffs = (
            ((0, 5), (3, 4), (5, 4)),
            ((6, 6), (2, 3), (4, 3)),
            ((7, 13), (1, 2), (3, 2)),
            ((14, 15), (2, 3), (4, 3)),
            ((16, 19), (1, 2), (3, 2)),
            ((20, 21), (2, 3), (4, 3)),
            ((22, 23), (3, 4), (5, 4)),
        )

        for time_range, high_season_tariff, low_season_tariff in tariffs:
            start, end = time_range
            if start <= hour <= end:
                if is_high_season and not weekend_or_holiday:
                    return high_season_tariff[0]
                if not is_high_season and weekend_or_holiday:
                    return low_season_tariff[0]
                return (
                    high_season_tariff[1]
                    if is_high_season
                    else low_season_tariff[1]
                )

        return 0
