"""Config-flow validation tests for Moj Elektro."""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.mojelektro.config_flow import async_validate_connection
from custom_components.mojelektro.moj_elektro_api import (
    MojElektroAuthError,
    MojElektroConnectionError,
    MojElektroRequestError,
)


class FakeApi:
    """API stub that raises a configured validation result."""

    error = None

    def __init__(self, *args, **kwargs):
        pass

    async def validate_token(self):
        if self.error is not None:
            raise self.error
        return True


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MojElektroAuthError("bad token"), "invalid_auth"),
        (MojElektroRequestError("bad meter"), "invalid_meter"),
        (MojElektroConnectionError("offline"), "cannot_connect"),
    ],
)
def test_connection_validation_maps_api_errors(error, expected):
    """Config flow should present a useful error for known API failures."""
    FakeApi.error = error

    with (
        patch(
            "custom_components.mojelektro.config_flow.async_get_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.mojelektro.config_flow.MojElektroApi",
            FakeApi,
        ),
    ):
        result = asyncio.run(
            async_validate_connection(
                object(),
                "token",
                "meter",
            )
        )

    assert result == expected


def test_connection_validation_accepts_valid_access():
    """Valid token/EIMM access should pass config validation."""
    FakeApi.error = None

    with (
        patch(
            "custom_components.mojelektro.config_flow.async_get_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.mojelektro.config_flow.MojElektroApi",
            FakeApi,
        ),
    ):
        result = asyncio.run(
            async_validate_connection(
                object(),
                "token",
                "meter",
            )
        )

    assert result is None


def test_connection_validation_maps_unexpected_errors():
    """Unexpected validation exceptions should stay distinguishable."""
    FakeApi.error = RuntimeError("unexpected")

    with (
        patch(
            "custom_components.mojelektro.config_flow.async_get_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.mojelektro.config_flow.MojElektroApi",
            FakeApi,
        ),
    ):
        result = asyncio.run(
            async_validate_connection(
                object(),
                "token",
                "meter",
            )
        )

    assert result == "unknown"
