from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from custom_components.thessla_green_modbus._config_flow.options_form import (
    build_options_defaults,
    build_options_schema,
)
from custom_components.thessla_green_modbus.registers.loader import get_registers_by_function
from custom_components.thessla_green_modbus.services import async_setup_services
from homeassistant.exceptions import ServiceValidationError

from tests.helpers_entity_data_correctness import _make_select

SUPPLY = "thessla_green_modbus.filter_type_replace_supply_filter"
EXHAUST = "thessla_green_modbus.filter_type_replace_exhaust_filter"
CLEANPAD_PURE = "thessla_green_modbus.filter_type_cleanpad_pure"

AFC_ABSENT = SimpleNamespace(options={"filter_afc": "absent"})
AFC_PRESENT_OR_UNSET = [
    SimpleNamespace(options={"filter_afc": "present"}),
    SimpleNamespace(options={}),
    None,
]


class _Services:
    def __init__(self):
        self.handlers: dict = {}

    def async_register(self, _domain, service, handler, _schema=None, supports_response=None):
        self.handlers[service] = handler

    def async_remove(self, _domain, service):
        self.handlers.pop(service, None)


class _Coordinator:
    def __init__(self, entry):
        self.entry = entry
        self.async_write_register = AsyncMock(return_value=True)
        self.async_request_refresh = AsyncMock()
        self.available_registers = {
            "holding_registers": {r.name for r in get_registers_by_function("03")}
        }
        self.data = {}


async def _reset_filters(monkeypatch, entry, filter_type):
    from custom_components.thessla_green_modbus import services as svc_mod

    coordinator = _Coordinator(entry)
    hass = SimpleNamespace(
        services=_Services(), data={}, bus=SimpleNamespace(async_fire=MagicMock())
    )
    monkeypatch.setattr(svc_mod, "_get_coordinator_from_entity_id", lambda _h, _e: coordinator)
    monkeypatch.setattr(svc_mod, "async_extract_entity_ids", lambda c: c.data["entity_id"])
    await async_setup_services(hass)
    handler = hass.services.handlers["reset_filters"]
    call = SimpleNamespace(data={"entity_id": ["climate.dev"], "filter_type": filter_type})
    return coordinator, handler, call


@pytest.mark.asyncio
@pytest.mark.parametrize(("filter_type", "value"), [(SUPPLY, 17), (EXHAUST, 33)])
async def test_reset_filters_without_afc_writes_replacement_command(
    monkeypatch, filter_type, value
):
    coordinator, handler, call = await _reset_filters(monkeypatch, AFC_ABSENT, filter_type)

    await handler(call)

    coordinator.async_write_register.assert_awaited_once_with(
        "filter_change", value, refresh=False, targeted_readback=False
    )


@pytest.mark.asyncio
async def test_reset_filters_without_afc_rejects_filter_type(monkeypatch):
    coordinator, handler, call = await _reset_filters(monkeypatch, AFC_ABSENT, CLEANPAD_PURE)

    with pytest.raises(ServiceValidationError, match=r"climate\.dev.*filter_afc set to absent"):
        await handler(call)

    coordinator.async_write_register.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", AFC_PRESENT_OR_UNSET)
async def test_reset_filters_with_afc_writes_filter_type(monkeypatch, entry):
    coordinator, handler, call = await _reset_filters(monkeypatch, entry, CLEANPAD_PURE)

    await handler(call)

    coordinator.async_write_register.assert_awaited_once_with(
        "filter_change", 4, refresh=False, targeted_readback=False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", AFC_PRESENT_OR_UNSET)
@pytest.mark.parametrize("filter_type", [SUPPLY, EXHAUST])
async def test_reset_filters_with_afc_rejects_replacement_command(monkeypatch, entry, filter_type):
    coordinator, handler, call = await _reset_filters(monkeypatch, entry, filter_type)

    with pytest.raises(ServiceValidationError, match=r"climate\.dev.*filter_afc set to present"):
        await handler(call)

    coordinator.async_write_register.assert_not_awaited()


@pytest.mark.asyncio
async def test_select_without_afc_offers_replacement_commands(mock_coordinator):
    mock_coordinator.entry = AFC_ABSENT
    entity = _make_select(mock_coordinator, "filter_change")

    assert entity._attr_options == ["replace_supply_filter", "replace_exhaust_filter"]

    await entity.async_select_option("replace_exhaust_filter")

    mock_coordinator.async_write_register.assert_awaited_once_with(
        "filter_change", 33, refresh=True
    )


@pytest.mark.parametrize("entry", AFC_PRESENT_OR_UNSET)
def test_select_with_afc_offers_filter_types(mock_coordinator, entry):
    mock_coordinator.entry = entry
    entity = _make_select(mock_coordinator, "filter_change")

    assert entity._attr_options == ["presostat", "flat_filters", "cleanpad", "cleanpad_pure"]


def test_register_definition_encodes_replacement_commands():
    register = next(r for r in get_registers_by_function("03") if r.name == "filter_change")

    assert register.encode(17) == 17
    assert register.encode(33) == 33


def test_options_form_defaults_filter_afc_to_present_and_accepts_absent():
    schema = build_options_schema(build_options_defaults({}, {}))

    assert schema({})["filter_afc"] == "present"
    assert schema({"filter_afc": "absent"})["filter_afc"] == "absent"
    with pytest.raises(vol.Invalid):
        schema({"filter_afc": "unknown"})


def test_options_form_defaults_filter_afc_from_entry_options():
    schema = build_options_schema(build_options_defaults({}, {"filter_afc": "absent"}))

    assert schema({})["filter_afc"] == "absent"
