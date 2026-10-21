from __future__ import annotations

import json
from importlib import resources

import pytest
from custom_components.thessla_green_modbus.mappings import ENTITY_MAPPINGS

from tests.helpers_entity_data_correctness import _make_select


def _season_mode_enum() -> dict[str, str]:
    path = resources.files("custom_components.thessla_green_modbus.registers").joinpath(
        "thessla_green_registers_full.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    registers = {entry["name"]: entry for entry in data["registers"]}
    return registers["season_mode"]["enum"]


def test_season_mode_select_follows_vendor_enum() -> None:
    enum = _season_mode_enum()
    states = ENTITY_MAPPINGS["select"]["season_mode"]["states"]

    assert enum[str(states["summer"])] == "LATO"
    assert enum[str(states["winter"])] == "ZIMA"


@pytest.mark.parametrize(("raw", "option"), [(1, "winter"), (0, "summer")])
def test_season_mode_select_reports_vendor_label(mock_coordinator, raw, option) -> None:
    mock_coordinator.data["season_mode"] = raw
    entity = _make_select(mock_coordinator, "season_mode")

    assert entity.current_option == option
