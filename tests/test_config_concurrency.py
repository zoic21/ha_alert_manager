"""Concurrent configuration mutation regression tests."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.alert_manager.const import DEFAULT_DELAY
from custom_components.alert_manager.manager import AlertManager


def test_failed_config_mutation_cannot_rollback_concurrent_rule_create(
    hass, entry, monkeypatch
):
    """A failed transaction cannot erase a later successful config mutation."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        first_save_started = asyncio.Event()
        release_first_save = asyncio.Event()
        save_count = 0

        async def controlled_save(_config, _records, **_kwargs) -> None:
            nonlocal save_count
            save_count += 1
            if save_count == 1:
                first_save_started.set()
                await release_first_save.wait()
                raise RuntimeError("simulated save failure")

        monkeypatch.setattr(manager.storage, "async_save", controlled_save)

        first = asyncio.create_task(manager.async_update_config({"global_delay": 123}))
        await first_save_started.wait()

        second = asyncio.create_task(
            manager.async_create_rule(
                {
                    "name": "Concurrent rule",
                    "entity_ids": ["sensor.concurrent"],
                    "enabled": True,
                    "source": "state",
                    "attribute": None,
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "message": None,
                }
            )
        )

        await asyncio.sleep(0)
        assert not second.done()
        assert manager.get_config()["rules"] == []

        release_first_save.set()
        with pytest.raises(RuntimeError, match="simulated save failure"):
            await first

        created = await second
        config = manager.get_config()
        assert config["global_delay"] == DEFAULT_DELAY
        assert config["rules"] == [created]
        assert save_count == 2

    asyncio.run(scenario())
