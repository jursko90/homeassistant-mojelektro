"""Diagnostics privacy tests for Moj Elektro."""

import asyncio
from types import SimpleNamespace

from custom_components.mojelektro.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.mojelektro.moj_elektro_api import MojElektroApi


def test_diagnostics_do_not_expose_credentials_or_measurements():
    """Support diagnostics must remain safe to share."""
    api = MojElektroApi("top-secret-token", "secret-eimm", 4, None)
    api.safe_meter_metadata = {
        "stevilo_faz": 3,
        "obstoj_15_min_meritve": True,
    }
    api.last_data = {
        "total_input": 12345.6789,
    }
    api.last_reading_metadata = {
        "total_input": {
            "source_timestamp": "2026-09-21T00:00:00+02:00",
            "quality_flags_present": False,
            "reading_qualities": [],
        }
    }

    entry = SimpleNamespace(
        data={
            "token": "top-secret-token",
            "meter_id": "secret-eimm",
        },
        options={
            "decimal": 4,
        },
        runtime_data=SimpleNamespace(api=api),
    )

    result = asyncio.run(
        async_get_config_entry_diagnostics(None, entry)
    )
    rendered = repr(result)

    assert "top-secret-token" not in rendered
    assert "secret-eimm" not in rendered
    assert "12345.6789" not in rendered
    assert result["safe_meter_metadata"]["stevilo_faz"] == 3
    assert (
        result["latest_reading_metadata"]["total_input"][
            "source_timestamp"
        ]
        == "2026-09-21T00:00:00+02:00"
    )
