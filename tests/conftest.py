"""Small Home Assistant 2026.8 test doubles for isolated custom-component tests."""

from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]


def _module(name: str, *, package: bool = False) -> ModuleType:
    module = ModuleType(name)
    if package:
        module.__path__ = []
    sys.modules[name] = module
    return module


# Bypass the integration __init__ when importing individual test subjects.
custom_components = _module("custom_components", package=True)
custom_components.__path__ = [str(ROOT / "custom_components")]
alert_manager_package = _module("custom_components.alert_manager", package=True)
alert_manager_package.__path__ = [str(ROOT / "custom_components" / "alert_manager")]

homeassistant = _module("homeassistant", package=True)
components = _module("homeassistant.components", package=True)
helpers = _module("homeassistant.helpers", package=True)
util = _module("homeassistant.util", package=True)

const = _module("homeassistant.const")


class Platform:
    SENSOR = "sensor"


const.Platform = Platform
const.ATTR_DEVICE_CLASS = "device_class"
const.ATTR_FRIENDLY_NAME = "friendly_name"
const.ATTR_UNIT_OF_MEASUREMENT = "unit_of_measurement"
const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
const.EVENT_STATE_CHANGED = "state_changed"
const.STATE_HOME = "home"
const.STATE_UNAVAILABLE = "unavailable"
const.STATE_UNKNOWN = "unknown"

hass_dict = _module("homeassistant.util.hass_dict")
hass_dict.HassKey = lambda value: value

core = _module("homeassistant.core")


def callback(function):
    function._hass_callback = True
    return function


def valid_entity_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value or ""))


class Event:
    def __init__(self, data=None):
        self.data = data or {}


class State:
    def __init__(self, entity_id: str, state: str, attributes=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}


core.callback = callback
core.valid_entity_id = valid_entity_id
core.Event = Event
core.HomeAssistant = object
core.State = State

config_entries = _module("homeassistant.config_entries")


class ConfigEntry:
    entry_id = "alert-manager-entry"

    def __init__(self):
        self.created_task_names = []

    def async_create_task(self, hass, coroutine, name=None, eager_start=True):
        self.created_task_names.append(name)
        return asyncio.create_task(coroutine, name=name)


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        return super().__init_subclass__()


config_entries.ConfigEntry = ConfigEntry
config_entries.ConfigFlow = ConfigFlow
homeassistant.config_entries = config_entries

data_entry_flow = _module("homeassistant.data_entry_flow")
data_entry_flow.FlowResult = dict


class Registry:
    def __init__(self, kind: str):
        self.kind = kind
        self.entries = {}
        self.labels = {}

    def async_get(self, item_id):
        return self.entries.get(item_id)

    def async_get_area(self, item_id):
        return self.entries.get(item_id)

    def async_get_label_by_name(self, name):
        return self.labels.get(name)


for name, event in (
    ("entity_registry", "entity_registry_updated"),
    ("device_registry", "device_registry_updated"),
    ("label_registry", "label_registry_updated"),
    ("area_registry", "area_registry_updated"),
):
    module = _module(f"homeassistant.helpers.{name}")
    module.EVENT_ENTITY_REGISTRY_UPDATED = event
    module.EVENT_DEVICE_REGISTRY_UPDATED = event
    module.EVENT_LABEL_REGISTRY_UPDATED = event
    module.EVENT_AREA_REGISTRY_UPDATED = event
    module.async_get = lambda hass, registry=name: getattr(hass, registry)
    setattr(helpers, name, module)

dispatcher = _module("homeassistant.helpers.dispatcher")


def async_dispatcher_send(hass, signal, *args):
    for listener in tuple(hass.dispatchers[signal]):
        listener(*args)


def async_dispatcher_connect(hass, signal, listener):
    hass.dispatchers[signal].append(listener)

    def remove():
        hass.dispatchers[signal].remove(listener)

    return remove


dispatcher.async_dispatcher_send = async_dispatcher_send
dispatcher.async_dispatcher_connect = async_dispatcher_connect

event_helper = _module("homeassistant.helpers.event")


def async_track_point_in_utc_time(hass, action, point):
    item = {"action": action, "point": point, "cancelled": False}
    hass.timers.append(item)

    def cancel():
        item["cancelled"] = True

    return cancel


event_helper.async_track_point_in_utc_time = async_track_point_in_utc_time

storage = _module("homeassistant.helpers.storage")


class Store:
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, hass, version, key, **kwargs):
        self.hass = hass
        self.key = key

    async def async_load(self):
        return self.hass.stores.get(self.key)

    async def async_save(self, data):
        self.hass.store_save_count += 1
        self.hass.stores[self.key] = data


storage.Store = Store

dt_module = _module("homeassistant.util.dt")
_clock = {"now": datetime(2026, 8, 24, 12, 0, tzinfo=UTC)}
dt_module.now = lambda: _clock["now"]
util.dt = dt_module

async_module = _module("homeassistant.util.async_")
async_module.create_eager_task = lambda coro, **kwargs: asyncio.create_task(coro)

sensor_module = _module("homeassistant.components.sensor")


class SensorEntity:
    def __init__(self):
        self._removers = []
        self.writes = 0

    def async_on_remove(self, callback_):
        if not hasattr(self, "_removers"):
            self._removers = []
        self._removers.append(callback_)

    def async_write_ha_state(self):
        self.writes = getattr(self, "writes", 0) + 1


sensor_module.SensorEntity = SensorEntity

entity_platform = _module("homeassistant.helpers.entity_platform")
entity_platform.AddConfigEntryEntitiesCallback = object

websocket_api = _module("homeassistant.components.websocket_api")
components.websocket_api = websocket_api
websocket_api.ActiveConnection = object


def websocket_command(schema):
    def decorate(function):
        function._ws_schema = schema
        return function

    return decorate


def async_response(function):
    return function


def require_admin(function):
    async def wrapped(hass, connection, msg):
        if not connection.user.is_admin:
            connection.send_error(msg["id"], "unauthorized", "Unauthorized")
            return None
        return await function(hass, connection, msg)

    return wrapped


websocket_api.websocket_command = websocket_command
websocket_api.async_response = async_response
websocket_api.require_admin = require_admin
websocket_api.async_register_command = lambda hass, command: hass.commands.append(
    command
)


class FakeBus:
    def __init__(self):
        self.listeners = defaultdict(list)
        self.fired = []

    def async_listen(self, event_type, listener):
        self.listeners[event_type].append(listener)

        def remove():
            if listener in self.listeners[event_type]:
                self.listeners[event_type].remove(listener)

        return remove

    def async_listen_once(self, event_type, listener):
        return self.async_listen(event_type, listener)

    def async_fire(self, event_type, data=None):
        self.fired.append((event_type, data or {}))


class FakeStates:
    def __init__(self):
        self.data = {}

    def get(self, entity_id):
        return self.data.get(entity_id)

    def async_all(self):
        return list(self.data.values())

    def set(self, entity_id, state, attributes=None):
        self.data[entity_id] = State(entity_id, state, attributes)
        return self.data[entity_id]


class FakeHass:
    def __init__(self):
        self.is_running = True
        self.bus = FakeBus()
        self.states = FakeStates()
        self.data = {}
        self.stores = {}
        self.store_save_count = 0
        self.timers = []
        self.dispatchers = defaultdict(list)
        self.commands = []
        self.entity_registry = Registry("entity")
        self.device_registry = Registry("device")
        self.label_registry = Registry("label")
        self.area_registry = Registry("area")


@pytest.fixture
def hass():
    _clock["now"] = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    return FakeHass()


@pytest.fixture
def entry():
    return ConfigEntry()


@pytest.fixture
def set_now():
    def set_value(value):
        _clock["now"] = value

    return set_value


@pytest.fixture
def registry_entry():
    def create(
        hass,
        entity_id,
        *,
        platform="test",
        device_id=None,
        disabled_by=None,
        labels=None,
        area_id=None,
    ):
        item = SimpleNamespace(
            entity_id=entity_id,
            platform=platform,
            device_id=device_id,
            disabled_by=disabled_by,
            labels=set(labels or ()),
            area_id=area_id,
        )
        hass.entity_registry.entries[entity_id] = item
        return item

    return create


@pytest.fixture
def device_entry():
    def create(
        hass,
        device_id="a" * 32,
        *,
        disabled_by=None,
        labels=None,
        area_id=None,
        name="Device",
    ):
        item = SimpleNamespace(
            id=device_id,
            disabled_by=disabled_by,
            labels=set(labels or ()),
            area_id=area_id,
            name=name,
            name_by_user=None,
        )
        hass.device_registry.entries[device_id] = item
        return item

    return create
