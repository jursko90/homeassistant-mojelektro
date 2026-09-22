# Changelog


## [0.3.0] - Unreleased

### API refresh

- remove the hard-coded Moj Elektro `readingType` identifier catalogue
- discover reading types dynamically from the official `GET /reading-type` endpoint
- use structured query parameters instead of hand-built meter-reading URLs
- add reusable API methods for `/reading-qualities`, `/merilno-mesto`, `/merilna-tocka` and `/souporaba`
- use the newest actually published 15-minute reading instead of indexing by the current wall-clock quarter hour
- allow opt-in Advanced reading types populated directly from the live `/reading-type` catalogue
- combine advanced and built-in interval registers into one meter-readings request
- refresh a cached reading-type catalogue and retry once when upstream rejects an obsolete opaque ID
- bound API requests to 30 seconds, report HTTP 429 rate limits clearly and translate malformed JSON into controlled API errors
- retain safe meter API response/message timestamps for support diagnostics
- redact EIMM/GSRN/souporaba identifiers from API error strings before they can reach logs
- keep authorization failures from optional endpoints nonfatal after a successful core meter-readings request

### Home Assistant configuration

- keep connection credentials (token and EIMM) in config-entry data
- move runtime behavior to Home Assistant Configure/Options
- add configurable decimal precision
- add configurable polling interval
- add configurable 15-minute lookback window
- add switches for 15-minute, daily/monthly, tariff-block and contracted-power sensor groups
- add Slovenian config/options translations
- automatically reload the integration after option changes using Home Assistant's current OptionsFlowWithReload pattern
- migrate legacy 0.2.x decimal configuration into the 0.3.0 Options schema without losing user settings
- use ConfigEntry runtime data to share one API client/coordinator across platforms
- add a localized manual Refresh data button for immediate API refreshes
- add a configurable stale-data threshold (24-168 hours, default 48)
- preserve and synchronize the legacy decimal copy during migration; downgrading the schema-v2 entry still requires restoring a pre-upgrade Home Assistant backup
- use a conservative 60-minute default polling interval while allowing 5-1440 minutes
- require the tested Home Assistant 2026.9+ baseline for the 0.3.0 HACS build

### Data quality, statistics and diagnostics

- fix the Last published reading diagnostic entity failing to initialize on Home Assistant 2026.9 when no numeric state class is defined
- load the official `/reading-qualities` catalogue and retain quality flags/descriptions as non-sensitive diagnostics metadata
- add cumulative import/export meter-register sensors for Home Assistant Energy Dashboard use
- correct sensor state classes: interval/daily/monthly values use reset-aware totals, cumulative meter registers use increasing totals, and contracted power uses measurement semantics
- calculate tariff-block totals from the latest complete 15-minute day only (92/96/100 intervals), avoiding partial overnight data and multi-day double counting
- correct the Slovenian network tariff hour boundaries against the current Energy Agency act and isolate the tariff/holiday rules in a dedicated tested module
- use the Home Assistant timezone for date boundaries instead of the host/container timezone
- add privacy-safe diagnostics that redact token and EIMM and never include measurement values
- add opt-in privacy-safe `souporaba` status-count sensors while keeping EIMM/GSRN/contact details out of entity states
- add API methods for souporaba detail and network-charge overview without exposing those sensitive payloads by default
- add a last-published-reading timestamp diagnostic sensor
- add a stale-data problem binary sensor based on the user-configured freshness threshold
- expose source timestamps and reading-quality flags as non-sensitive entity attributes
- retain a privacy-safe technical meter metadata subset for diagnostics only
- cache contracted-power metadata for the current day instead of querying two metadata endpoints on every poll
- stop exposing EIMM as the Home Assistant device model
- add full English and Slovenian entity display-name translations
- handle delayed daily register data across month boundaries without inflating monthly totals
- suppress negative calculated deltas after a meter register reset/replacement instead of corrupting statistics
- deduplicate and validate quarter-hour tariff intervals before declaring a day complete
- reject NaN/Infinity values from API payloads
- mark never-populated entities unavailable while retaining previous good values across transient partial responses
- derive dynamic-register reset periods from API `perioda` metadata rather than hard-coded intervals

### Tests

- add regression tests for runtime reading-type discovery
- verify meter-reading requests use IDs returned by the official catalogue
- verify empty API responses never synthesize false zero energy values
- verify 15-minute sensors select the newest published reading
- verify reset boundaries for interval, daily and monthly energy values
- verify 0.2.x to 0.3.0 config-entry migration preserves settings
- verify reading-quality metadata, total registers, complete-day tariff calculation and souporaba privacy
- verify current Slovenian tariff boundaries and work-free-day handling
- verify freshness threshold behavior and last-published timestamp selection
- verify safe technical diagnostics exclude personal identifiers
- verify contracted-power metadata caching
- verify config-flow auth/request/connection error mapping
- verify month-boundary fallback, duplicate/off-grid tariff intervals and meter-reset protection
- verify NaN/Infinity rejection, optional-endpoint auth behavior and API error redaction
- verify dynamic register metadata, period parsing, stable keys and combined request behavior
- verify stale reading-type catalogue self-healing
- verify Moj Elektro API contract expectations with a weekly OpenAPI schema-drift workflow
- add a repeatable real-Home-Assistant 0.3.0 beta test checklist

All notable changes to this maintained fork are documented here.

This project is a maintained fork of [frlequ/homeassistant-mojelektro](https://github.com/frlequ/homeassistant-mojelektro). Upstream authorship and the original MIT license are preserved.

## [0.2.7] - 2026-09-21

First maintained-fork release.

### Home Assistant compatibility

- migrate legacy suffixed sensor unique IDs (for example `_2`, `_3`) in the entity registry before using deterministic IDs, preserving existing entity IDs, history, dashboards and automations
- fixed the device-registry `model` value so it is a string and remains compatible with Home Assistant 2026.12+
- removed synchronous `manifest.json` reads from the Home Assistant event loop
- migrated sensor state handling to `SensorEntity.native_value`
- switched startup to `DataUpdateCoordinator.async_config_entry_first_refresh()`
- updated config-entry unloading to current Home Assistant helpers
- added `strings.json` for current config-flow validation
- refreshed CI for Python 3.14 and Home Assistant 2026.9.x

### Authentication and configuration

- added separate authentication, invalid-request and connection errors
- added Home Assistant reauthentication when an API token expires or is revoked
- added duplicate EIMM protection in the config flow
- migrate legacy config entries to a stable EIMM unique ID when safe
- made entity unique IDs deterministic while preserving the historic ID shape

### API and data robustness

- correct Slovenian network tariff-block hour boundaries and work-free-day handling against the current Energy Agency schedule
- preserve prior sensor values when Moj Elektro temporarily returns an empty successful payload instead of synthesizing zero values
- preserve `TOTAL_INCREASING` statistics from false zero/reset/rebound sequences
- fixed crashes caused by missing or unknown reading types
- fixed accidental list access using index `-1` when a required reading type is absent
- preserve the expected entity set when Moj Elektro temporarily returns partial data
- preserve previous values where appropriate during partial responses
- validate API payload shapes more defensively
- derive validation and tariff reading types from the integration's mapping rather than duplicating IDs
- removed unused `requests` dependency
- removed `dateutil` dependency and use Python's built-in datetime parser

### Contracted power

- included the upstream fix for contracted-power values becoming unavailable on the last day of their validity period

### Documentation and packaging

- changed project documentation to clearly identify this repository as a maintained fork
- updated the Moj Elektro token location to **API storitve**
- changed HACS instructions to use this repository as a custom integration
- updated repository URLs in the integration manifest
- set integration version to `0.2.7`

### Upstream work incorporated or adapted

- [upstream PR #59](https://github.com/frlequ/homeassistant-mojelektro/pull/59) — blocking `manifest.json` file read  
  Adapted and superseded by removing the runtime manifest read entirely.

- [upstream PR #60](https://github.com/frlequ/homeassistant-mojelektro/pull/60) — contracted-power validity on the final day  
  Incorporated into 0.2.7.

- [upstream PR #64](https://github.com/frlequ/homeassistant-mojelektro/pull/64) — new Moj Elektro portal wording  
  Incorporated into the documentation.

### Upstream issues addressed

- [#54](https://github.com/frlequ/homeassistant-mojelektro/issues/54) — blocking call
- [#62](https://github.com/frlequ/homeassistant-mojelektro/issues/62) — database executor / blocking-call warnings
- [#63](https://github.com/frlequ/homeassistant-mojelektro/issues/63) — integration slowdowns caused by blocking I/O
- [#65](https://github.com/frlequ/homeassistant-mojelektro/issues/65) — non-string device model

### Reviewed but intentionally deferred

- [upstream PR #57](https://github.com/frlequ/homeassistant-mojelektro/pull/57) — alternate 15-minute cache window  
  Needs validation against current API behaviour before inclusion.

- [upstream PR #58](https://github.com/frlequ/homeassistant-mojelektro/pull/58) — total meter readings  
  Planned for the 0.3.x API refresh.

- [upstream issue #66](https://github.com/frlequ/homeassistant-mojelektro/issues/66) — souporaba  
  Planned for 0.3.x using the official `GET /souporaba` endpoint.

## Planned: 0.3.x

The next feature series is intended to align the integration more closely with the current official Moj Elektro API.

Planned work includes:

- dynamic reading types from `GET /reading-type`
- reading quality handling from `GET /reading-qualities`
- souporaba support from `GET /souporaba`
- total meter-reading sensors
- improved long-term statistics and Energy Dashboard integration
- useful metering-point metadata from `GET /merilno-mesto/{identifikator}`
- improved contracted-power metadata from `GET /merilna-tocka/{gsrn}`
- automated API/config-flow tests
- Slovenian translations
