"""Registry compatibility on the oldest supported Home Assistant."""

from homeassistant.helpers import device_registry as dr

from custom_components.alert_manager.registry_metadata import device_area_id


def test_device_area_on_home_assistant_without_child_device_api(
    hass, device_entry, monkeypatch
):
    device = device_entry(hass, "device", area_id="garage")
    monkeypatch.delattr(dr, "async_get_effective_area_id")
    assert device_area_id(hass, device) == "garage"
