"""Config-flow validation tests for Moj Elektro."""

import asyncio
from types import SimpleNamespace

import custom_components.mojelektro.config_flow as config_flow
from custom_components.mojelektro.moj_elektro_api import (
    MojElektroAuthError,
    MojElektroConnectionError,
    MojElektroRequestError,
)


class FakeApi:
    """Configurable Moj Elektro validation stub."""

    error = None

    def __init__(self, token, meter_id, decimal, session):
        self.token = token
        self.meter_id = meter_id

    async def validate_token(self):
        if self.error is not None:
            raise self.error
        return True


def run_validation(monkeypatch, error):
    FakeApi.error = error
    monkeypatch.setattr(config_flow, "MojElektroApi", FakeApi)
    monkeypatch.setattr(
        config_flow,
        "async_get_clientsession",
        lambda hass: object(),
    )
    return asyncio.run(
        config_flow.async_validate_connection(
            object(),
            "token",
            "meter",
        )
    )


def test_config_validation_success(monkeypatch):
    assert run_validation(monkeypatch, None) is None


def test_config_validation_invalid_token(monkeypatch):
    assert run_validation(
        monkeypatch,
        MojElektroAuthError("bad token"),
    ) == "invalid_auth"


def test_config_validation_invalid_meter(monkeypatch):
    assert run_validation(
        monkeypatch,
        MojElektroRequestError("bad meter"),
    ) == "invalid_meter"


def test_config_validation_connection_error(monkeypatch):
    assert run_validation(
        monkeypatch,
        MojElektroConnectionError("offline"),
    ) == "cannot_connect"


def test_config_validation_unknown_error(monkeypatch):
    assert run_validation(
        monkeypatch,
        RuntimeError("unexpected"),
    ) == "unknown"


def test_duplicate_meter_detection_does_not_depend_on_unique_id():
    """Legacy entries without unique IDs must still block duplicate EIMM setup."""
    entries = [
        SimpleNamespace(data={"meter_id": "meter-a"}, unique_id=None),
        SimpleNamespace(data={"meter_id": "meter-b"}, unique_id=None),
    ]

    assert config_flow._meter_id_already_configured(entries, "meter-a")
    assert not config_flow._meter_id_already_configured(entries, "meter-c")


def test_advanced_choices_exclude_builtin_tags():
    """Built-in A+/A- sensors must not be duplicated in Advanced choices."""
    choices = config_flow._build_extra_reading_choices(
        {
            "A+": {
                "naziv": "Built-in import",
                "perioda": "15 min",
            },
            "P+": {
                "naziv": "Power import",
                "perioda": "15 min",
            },
        },
        (),
    )

    assert "A+" not in choices
    assert choices["P+"] == "P+ — Power import (15 min)"


def test_advanced_choices_preserve_saved_selection_without_catalogue():
    """Temporary catalogue failure must not make a saved option disappear."""
    choices = config_flow._build_extra_reading_choices(
        {},
        ("P+", "Q-"),
    )

    assert choices == {
        "P+": "P+",
        "Q-": "Q-",
    }


def test_advanced_choices_use_description_when_name_is_missing():
    """Catalogue description should provide a useful fallback label."""
    choices = config_flow._build_extra_reading_choices(
        {
            "R+": {
                "opis": "Reactive energy",
                "perioda": "1 h",
            }
        },
        (),
    )

    assert choices["R+"] == "R+ — Reactive energy (1 h)"
