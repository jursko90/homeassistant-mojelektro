"""Validate the public Moj Elektro OpenAPI contract used by the integration."""

from __future__ import annotations

import argparse
import sys
import urllib.request

import yaml

DEFAULT_SPEC_URL = (
    "https://docs.informatika.si/mojelektro/api/mojelektro-openapi.yaml"
)
PRODUCTION_API_URL = "https://api.informatika.si/mojelektro/v1"

REQUIRED_PATHS = {
    "/meter-readings": "get",
    "/merilno-mesto/{identifikator}": "get",
    "/merilna-tocka/{gsrn}": "get",
    "/reading-qualities": "get",
    "/reading-type": "get",
    "/souporaba": "get",
    "/souporaba/{sifra}": "get",
    "/souporaba/pregled-obracunov-omreznine": "get",
}

REQUIRED_SCHEMA_PROPERTIES = {
    "ReadingType": {
        "naziv",
        "oznaka",
        "perioda",
        "opis",
        "readingType",
        "readingTypeBrezObracuna",
        "readingTypeObracun",
        "vrsta",
    },
    "IntervalReading": {
        "timestamp",
        "value",
        "readingQualities",
    },
    "IntervalBlock": {
        "readingType",
        "intervalReadings",
    },
    "MeterReadings": {
        "usagePoint",
        "messageCreated",
        "intervalBlocks",
    },
    "PogodbeniPodatki": {
        "steviloFaz",
        "vrstaOmejevalcaToka",
        "jakostOmejevalcaToka",
        "prikljucnaMoc",
        "dovoljenaMocOddaje",
        "instaliranaMocProizvodnje",
        "virPrimarnegaEnergenta",
        "daljinskoCitanje",
        "obstoj15MinutneMeritve",
        "nazivFrekvenceOdbiranja",
    },
    "TehnicniPodatki": {
        "tipStevca",
        "letoIzdelave",
    },
}


def validate_spec(spec: dict) -> list[str]:
    """Return contract-drift problems found in an OpenAPI document."""
    problems: list[str] = []

    servers = {
        server.get("url")
        for server in spec.get("servers", [])
        if isinstance(server, dict)
    }
    if PRODUCTION_API_URL not in servers:
        problems.append(
            f"Production API server missing: {PRODUCTION_API_URL}"
        )

    paths = spec.get("paths") or {}
    for path, method in REQUIRED_PATHS.items():
        operation = paths.get(path)
        if not isinstance(operation, dict) or method not in operation:
            problems.append(f"Required operation missing: {method.upper()} {path}")

    schemas = (
        (spec.get("components") or {}).get("schemas")
        or {}
    )
    for schema_name, required_properties in REQUIRED_SCHEMA_PROPERTIES.items():
        schema = schemas.get(schema_name)
        if not isinstance(schema, dict):
            problems.append(f"Required schema missing: {schema_name}")
            continue

        properties = schema.get("properties") or {}
        missing = sorted(required_properties - set(properties))
        if missing:
            problems.append(
                f"{schema_name} missing properties: {', '.join(missing)}"
            )

    value_type = schemas.get("ReadingTypeValueType") or {}
    enum_values = set(value_type.get("enum") or [])
    expected_value_types = {"KOLICINA", "STANJE"}
    if not expected_value_types.issubset(enum_values):
        problems.append(
            "ReadingTypeValueType no longer contains both "
            "KOLICINA and STANJE"
        )

    return problems


def load_spec(url: str) -> dict:
    """Download and parse the OpenAPI YAML."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "homeassistant-mojelektro-schema-check"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()

    loaded = yaml.safe_load(payload)
    if not isinstance(loaded, dict):
        raise ValueError("OpenAPI document root is not an object")
    return loaded


def main() -> int:
    """Run the public schema drift check."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_SPEC_URL)
    args = parser.parse_args()

    try:
        spec = load_spec(args.url)
    except Exception as err:
        print(f"Unable to load Moj Elektro OpenAPI: {err}", file=sys.stderr)
        return 2

    problems = validate_spec(spec)
    if problems:
        print("Moj Elektro API contract drift detected:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Moj Elektro OpenAPI contract matches integration expectations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
