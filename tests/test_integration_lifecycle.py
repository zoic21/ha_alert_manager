"""Top-level integration lifecycle regression tests."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from custom_components.alert_manager.const import DATA_MANAGER


def _load_integration_module():
    """Load the real package initializer despite the isolated test package stub."""
    module_name = "custom_components.alert_manager.integration_lifecycle"
    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).parents[1] / "custom_components/alert_manager/__init__.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_aborted_manager_setup_stops_entry_setup_and_cleans_up(
    hass, entry, monkeypatch
):
    """A terminal Home Assistant state cannot install panel or platforms."""
    integration = _load_integration_module()
    instances = []

    class AbortedManager:
        def __init__(self, _hass, _entry):
            self.unloaded = False
            instances.append(self)

        async def async_setup(self):
            return False

        async def async_unload(self):
            self.unloaded = True

    monkeypatch.setattr(integration, "AlertManager", AbortedManager)

    result = asyncio.run(integration.async_setup_entry(hass, entry))

    assert result is False
    assert instances[0].unloaded is True
    assert DATA_MANAGER not in hass.data
    assert hass.commands == []


def test_cancelled_manager_setup_is_cleaned_before_propagation(
    hass, entry, monkeypatch
):
    """Cancellation cannot strand a partially initialized manager."""
    integration = _load_integration_module()
    instances = []

    class CancelledManager:
        def __init__(self, _hass, _entry):
            self.unloaded = False
            instances.append(self)

        async def async_setup(self):
            raise asyncio.CancelledError

        async def async_unload(self):
            self.unloaded = True

    monkeypatch.setattr(integration, "AlertManager", CancelledManager)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert instances[0].unloaded is True
    assert DATA_MANAGER not in hass.data


@pytest.mark.parametrize("fail_setup", [False, True])
def test_dashboard_module_follows_entry_lifecycle(hass, entry, monkeypatch, fail_setup):
    """Register the card once and remove its URL on unload or setup rollback."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.alert_manager.const import DATA_STATIC_REGISTERED

    integration = _load_integration_module()
    modules = set()
    manager = SimpleNamespace(
        async_setup=AsyncMock(return_value=True), async_unload=AsyncMock()
    )
    monkeypatch.setattr(integration, "AlertManager", lambda *_args: manager)
    monkeypatch.setattr(
        integration.frontend,
        "add_extra_js_url",
        lambda _hass, url: modules.add(url),
        raising=False,
    )
    monkeypatch.setattr(
        integration.frontend,
        "remove_extra_js_url",
        lambda _hass, url: modules.remove(url),
        raising=False,
    )
    hass.data[DATA_STATIC_REGISTERED] = True
    hass.config_entries.async_forward_entry_setups = AsyncMock(
        side_effect=RuntimeError("platform failed") if fail_setup else None
    )
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    async def exercise():
        if fail_setup:
            with pytest.raises(RuntimeError, match="platform failed"):
                await integration.async_setup_entry(hass, entry)
        else:
            assert await integration.async_setup_entry(hass, entry)
            assert modules == {integration.CARD_MODULE_URL}
            assert await integration.async_unload_entry(hass, entry)
        assert not modules
        assert DATA_MANAGER not in hass.data
        manager.async_unload.assert_awaited_once()

    asyncio.run(exercise())
