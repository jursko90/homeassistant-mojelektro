"""Repository metadata consistency tests."""

import json
from pathlib import Path

from custom_components.mojelektro.const import DOMAIN, VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_matches_runtime_constants():
    """Runtime constants and package manifest must not drift apart."""
    manifest = json.loads(
        (
            ROOT
            / "custom_components"
            / "mojelektro"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert manifest["domain"] == DOMAIN
    assert manifest["version"] == VERSION


def test_hacs_baseline_matches_03_development_policy():
    """0.3.0 branch should advertise only the HA baseline we validate in CI."""
    hacs = json.loads(
        (ROOT / "hacs.json").read_text(encoding="utf-8")
    )

    assert VERSION == "0.3.0-beta.2"
    assert hacs["homeassistant"] == "2026.9.0"
