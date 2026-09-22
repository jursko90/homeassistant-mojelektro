"""Tests for the Moj Elektro OpenAPI drift checker."""

from copy import deepcopy

from scripts.check_api_schema import (
    OPTIONAL_PATHS,
    PRODUCTION_API_URL,
    REQUIRED_PATHS,
    REQUIRED_SCHEMA_PROPERTIES,
    optional_contract_warnings,
    validate_spec,
)


def make_valid_spec():
    """Create the smallest OpenAPI document accepted by the checker."""
    return {
        "servers": [{"url": PRODUCTION_API_URL}],
        "paths": {
            path: {method: {}}
            for path, method in REQUIRED_PATHS.items()
        },
        "components": {
            "schemas": {
                **{
                    name: {
                        "properties": {
                            prop: {}
                            for prop in properties
                        }
                    }
                    for name, properties
                    in REQUIRED_SCHEMA_PROPERTIES.items()
                },
                "ReadingTypeValueType": {
                    "enum": ["KOLICINA", "STANJE"],
                },
            }
        },
    }


def test_valid_contract_has_no_problems():
    """Known-good contract shape should pass."""
    assert validate_spec(make_valid_spec()) == []


def test_missing_endpoint_is_detected():
    """Endpoint removal must fail the drift check."""
    spec = make_valid_spec()
    del spec["paths"]["/reading-type"]

    problems = validate_spec(spec)

    assert any("/reading-type" in problem for problem in problems)


def test_missing_schema_property_is_detected():
    """Field removal must fail the drift check."""
    spec = make_valid_spec()
    del spec["components"]["schemas"]["ReadingType"]["properties"]["perioda"]

    problems = validate_spec(spec)

    assert any(
        "ReadingType missing properties" in problem
        and "perioda" in problem
        for problem in problems
    )


def test_value_type_enum_drift_is_detected():
    """The KOLICINA/STANJE semantic contract must remain explicit."""
    spec = deepcopy(make_valid_spec())
    spec["components"]["schemas"]["ReadingTypeValueType"]["enum"] = [
        "KOLICINA"
    ]

    problems = validate_spec(spec)

    assert any("KOLICINA and STANJE" in problem for problem in problems)


def test_optional_endpoint_drift_warns_without_failing_core_contract():
    """Optional feature drift should stay visible without blocking core release."""
    spec = make_valid_spec()

    assert validate_spec(spec) == []
    warnings = optional_contract_warnings(spec)

    assert all(
        f"Optional operation missing: {method.upper()} {path}" in warnings
        for path, method in OPTIONAL_PATHS.items()
    )
