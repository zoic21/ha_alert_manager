"""Small Home Assistant 2026.8 test doubles for isolated custom-component tests."""

from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from enum import Enum, StrEnum
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

automation_component = _module("homeassistant.components.automation")
automation_component.DATA_COMPONENT = "automation_component"
trace_component = _module("homeassistant.components.trace", package=True)
trace_const = _module("homeassistant.components.trace.const")
trace_const.DATA_TRACE = "trace"

const = _module("homeassistant.const")


class Platform:
    BUTTON = "button"
    SENSOR = "sensor"
    SWITCH = "switch"


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


class Context:
    def __init__(self, *, user_id=None):
        self.user_id = user_id


class ServiceCall:
    def __init__(self, data=None, *, context=None):
        self.data = data or {}
        self.context = context or Context()


class State:
    def __init__(
        self, entity_id: str, state: str, attributes=None, *, last_updated=None
    ):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        self.last_updated = last_updated or _clock["now"]


core.callback = callback
core.valid_entity_id = valid_entity_id
core.Context = Context
core.Event = Event
core.HomeAssistant = object
core.ServiceCall = ServiceCall
core.State = State

exceptions = _module("homeassistant.exceptions")


class ServiceValidationError(Exception):
    pass


class TemplateError(Exception):
    pass


exceptions.ServiceValidationError = ServiceValidationError
exceptions.TemplateError = TemplateError

config_entries = _module("homeassistant.config_entries")


class ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    UNLOAD_IN_PROGRESS = "unload_in_progress"


class ConfigEntryChange(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    UPDATED = "updated"


class ConfigEntry:
    _next_id = 0

    def __init__(
        self,
        *,
        domain="alert_manager",
        state=ConfigEntryState.LOADED,
        disabled_by=None,
        source="user",
    ):
        type(self)._next_id += 1
        self.entry_id = f"entry-{type(self)._next_id}"
        self.domain = domain
        self.state = state
        self.disabled_by = disabled_by
        self.source = source
        self.created_task_names = []
        self.created_task_eager_starts = []
        self._state_listeners = []

    def async_create_task(self, hass, coroutine, name=None, eager_start=True):
        self.created_task_names.append(name)
        self.created_task_eager_starts.append(eager_start)
        return asyncio.create_task(coroutine, name=name)

    def async_on_state_change(self, listener):
        self._state_listeners.append(listener)

        def remove():
            if listener in self._state_listeners:
                self._state_listeners.remove(listener)

        return remove

    def set_state(self, state):
        self.state = state
        for listener in tuple(self._state_listeners):
            listener()


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        return super().__init_subclass__()


config_entries.ConfigEntry = ConfigEntry
config_entries.ConfigEntryChange = ConfigEntryChange
config_entries.ConfigEntryState = ConfigEntryState
config_entries.SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"
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

    def async_get_entity_id(self, domain, platform, unique_id):
        for item in self.entries.values():
            if (
                item.entity_id.partition(".")[0] == domain
                and item.platform == platform
                and getattr(item, "unique_id", None) == unique_id
            ):
                return item.entity_id
        return None

    def async_remove(self, item_id):
        self.entries.pop(item_id, None)


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

device_registry = sys.modules["homeassistant.helpers.device_registry"]


class DeviceEntryType(StrEnum):
    SERVICE = "service"


device_registry.DeviceEntryType = DeviceEntryType
device_registry.DeviceInfo = lambda **kwargs: kwargs

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


def async_track_time_change(hass, action, *, hour, minute, second):
    item = {
        "action": action,
        "hour": hour,
        "minute": minute,
        "second": second,
        "cancelled": False,
    }
    hass.timers.append(item)

    def cancel():
        item["cancelled"] = True

    return cancel


event_helper.async_track_point_in_utc_time = async_track_point_in_utc_time
event_helper.async_track_time_change = async_track_time_change

template_helper = _module("homeassistant.helpers.template")


class RenderInfo:
    def __init__(self, result, entities):
        self._result = result
        self.entities = frozenset(entities)

    def result(self):
        return self._result

    def filter(self, entity_id):
        return entity_id in self.entities


class Template:
    def __init__(self, template, hass):
        self.template = template.strip()
        self.hass = hass
        self._compiled = None

    def ensure_valid(self):
        if (
            self.template.count("{{") != self.template.count("}}")
            or "{% if %}" in self.template
        ):
            raise TemplateError("invalid template syntax")
        self._compiled = self.template

    def async_render_to_info(self, variables=None):
        if self._compiled is None:
            self.ensure_valid()
        variables = dict(variables or {})

        def states(entity_id):
            state = self.hass.states.get(entity_id)
            return state.state if state is not None else "unknown"

        def is_state(entity_id, value):
            return states(entity_id) == value

        entities = set(
            re.findall(
                r"(?:states|is_state)\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]",
                self.template,
            )
        )
        expression = self.template.strip()
        is_state_match = re.fullmatch(
            r"{{\s*is_state\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*}}",
            expression,
        )
        if is_state_match:
            result = str(is_state(*is_state_match.groups())).lower()
        elif expression in ("{{ true }}", "true", "True"):
            result = "true"
        elif expression in ("{{ false }}", "false", "False"):
            result = "false"
        else:
            result = expression
            result = re.sub(
                r"{{\s*states\(\s*['\"]([^'\"]+)['\"]\s*\)\s*}}",
                lambda match: states(match.group(1)),
                result,
            )
            replacements = {
                "entity_id": variables.get("entity_id", ""),
                "value": variables.get("value", ""),
                "state.state": getattr(variables.get("state"), "state", ""),
            }
            for name, value in replacements.items():
                result = re.sub(
                    rf"{{{{\s*{re.escape(name)}\s*}}}}",
                    str(value),
                    result,
                )
        return RenderInfo(result, entities)


template_helper.Template = Template

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

translation = _module("homeassistant.helpers.translation")


async def async_get_translations(hass, language, category, integrations=None):
    translation_file = (
        ROOT
        / "custom_components"
        / "alert_manager"
        / "translations"
        / f"{language}.json"
    )
    catalog = __import__("json").loads(translation_file.read_text())
    result = {}

    def flatten(value, prefix):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if isinstance(item, dict):
                flatten(item, path)
            else:
                result[path] = item

    flatten(catalog[category], f"component.alert_manager.{category}")
    return result


translation.async_get_translations = async_get_translations

config_validation = _module("homeassistant.helpers.config_validation")
config_validation.string = lambda value: str(value)

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

button_module = _module("homeassistant.components.button")


class ButtonEntity(SensorEntity):
    pass


button_module.ButtonEntity = ButtonEntity

switch_module = _module("homeassistant.components.switch")


class SwitchEntity(SensorEntity):
    pass


switch_module.SwitchEntity = SwitchEntity

persistent_notification = _module("homeassistant.components.persistent_notification")


def async_create_notification(hass, message, *, title=None, notification_id=None):
    hass.notifications[notification_id] = {"message": message, "title": title}


def async_dismiss_notification(hass, notification_id):
    hass.notifications.pop(notification_id, None)


persistent_notification.async_create = async_create_notification
persistent_notification.async_dismiss = async_dismiss_notification

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

    def set(self, entity_id, state, attributes=None, *, last_updated=None):
        self.data[entity_id] = State(
            entity_id,
            state,
            attributes,
            last_updated=last_updated,
        )
        return self.data[entity_id]


class FakeServices:
    def __init__(self):
        self.handlers = {}

    def async_register(self, domain, service, handler, schema=None):
        self.handlers[(domain, service)] = (handler, schema)

    def async_remove(self, domain, service):
        self.handlers.pop((domain, service), None)

    async def async_call(self, domain, service, data, *, context=None):
        handler, schema = self.handlers[(domain, service)]
        validated = schema(data) if schema is not None else data
        await handler(ServiceCall(validated, context=context))


class FakeAuth:
    def __init__(self):
        self.users = {}

    async def async_get_user(self, user_id):
        return self.users.get(user_id)


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
        self.notifications = {}
        self.config = SimpleNamespace(language="fr")
        self.services = FakeServices()
        self.auth = FakeAuth()
        self.config_entries = FakeConfigEntries()
        self.entity_registry = Registry("entity")
        self.device_registry = Registry("device")
        self.label_registry = Registry("label")
        self.area_registry = Registry("area")

    def async_create_task(self, coroutine, name=None, eager_start=True):
        return asyncio.create_task(coroutine, name=name)


class FakeConfigEntries:
    def __init__(self):
        self.entries = []

    def add(self, entry):
        self.entries.append(entry)
        return entry

    def async_entries(
        self,
        domain=None,
        include_ignore=True,
        include_disabled=True,
    ):
        return [
            entry
            for entry in self.entries
            if (domain is None or entry.domain == domain)
            and (include_ignore or entry.source != "ignore")
            and (include_disabled or entry.disabled_by is None)
        ]


@pytest.fixture
def hass():
    _clock["now"] = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    return FakeHass()


@pytest.fixture
def entry():
    return ConfigEntry()


@pytest.fixture
def config_entry():
    def create(
        hass,
        domain,
        *,
        state=ConfigEntryState.LOADED,
        disabled_by=None,
        source="user",
    ):
        return hass.config_entries.add(
            ConfigEntry(
                domain=domain,
                state=state,
                disabled_by=disabled_by,
                source=source,
            )
        )

    return create


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
        unique_id=None,
    ):
        item = SimpleNamespace(
            entity_id=entity_id,
            platform=platform,
            device_id=device_id,
            disabled_by=disabled_by,
            labels=set(labels or ()),
            area_id=area_id,
            unique_id=unique_id,
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
