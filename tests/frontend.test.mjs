import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { compactCss } from "./frontend-test-helpers.mjs";

const flattenTranslations = (value, prefix = "") => Object.entries(value).reduce(
  (result, [key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === "object") {
      Object.assign(result, flattenTranslations(item, path));
    } else {
      result[`component.alert_manager.config_panel.${path}`] = item;
    }
    return result;
  },
  {},
);
const translationFile = (language) => JSON.parse(readFileSync(
  new URL(`../custom_components/alert_manager/translations/${language}.json`, import.meta.url),
  "utf8",
));
const TRANSLATIONS = Object.fromEntries(["en", "fr"].map((language) => [
  language,
  flattenTranslations(translationFile(language).config_panel),
]));

globalThis.HTMLElement = class {
  constructor() {
    this.isConnected = true;
  }

  attachShadow() {
    this.shadowRoot = {
      addEventListener() {},
      querySelector() { return null; },
      querySelectorAll() { return []; },
      innerHTML: "",
    };
    return this.shadowRoot;
  }

  dispatchEvent(event) {
    this.dispatchedEvent = event;
    return true;
  }
};
globalThis.CustomEvent = class {
  constructor(type, options) {
    this.type = type;
    Object.assign(this, options);
  }
};
const fakeDomElement = (tagName) => ({
  tagName: tagName.toUpperCase(),
  attributes: {},
  children: [],
  dataset: {},
  style: { cssText: "" },
  textContent: "",
  setAttribute(name, value) { this.attributes[name] = String(value); },
  append(...children) { this.children.push(...children); },
  addEventListener(name, callback) { this.listeners ??= {}; this.listeners[name] = callback; },
});
globalThis.document = { createElement: fakeDomElement };
globalThis.customElements = {
  _items: new Map(),
  define(name, value) {
    this._items.set(name, class extends value {
      constructor() {
        super();
        this._language = "fr";
        this._translations = TRANSLATIONS.fr;
        this._englishTranslations = TRANSLATIONS.en;
      }
    });
  },
  get(name) { return this._items.get(name); },
};
globalThis.window = {
  confirm: () => true,
  localStorage: {
    values: new Map(),
    getItem(key) { return this.values.get(key) ?? null; },
    setItem(key, value) { this.values.set(key, value); },
    clear() { this.values.clear(); },
  },
};
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    clipboard: {
      async writeText(value) {
        globalThis.navigator.clipboard.lastValue = value;
      },
    },
  },
});

const { makeTableState, lines, newRuleDefaults } = await import(
  "../frontend-src/alert-manager-panel.js"
);

test("human duration formatter", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  assert.equal(panel._durationText(45), "45 s");
  assert.equal(panel._durationText(900), "15 min");
  assert.equal(panel._durationText(7200), "2 h");
});

test("textarea list parser", () => {
  assert.deepEqual(lines("sensor.one\nsensor.two, sensor.three"), [
    "sensor.one",
    "sensor.two",
    "sensor.three",
  ]);
});

test("panel is registered", () => {
  assert.ok(customElements.get("alert-manager-panel"));
});

test("coherence tab is available without starting a scan", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const tab = panel._tabs().find((item) => item.path === "/alert-manager/coherence");
  assert.equal(tab.name, "Cohérence");
  assert.equal(panel._coherence, null);
});

test("coherence scan runs only from its explicit action", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._render = () => {};
  const response = {
    results: [],
    missing_count: 0,
    files_scanned: 4,
    files_skipped: 0,
    references_checked: 12,
    duration_ms: 8,
    scanned_at: "2026-08-24T12:00:00+00:00",
  };
  const calls = [];
  panel._hass = {
    async callWS(message) {
      calls.push(message);
      return response;
    },
  };
  await panel._handleClick({
    target: {
      closest() {
        return { dataset: { action: "scan-coherence" } };
      },
    },
  });
  assert.deepEqual(calls, [{ type: "alert_manager/coherence/scan" }]);
  assert.equal(panel._coherence, response);
  assert.equal(panel._coherenceLoading, false);
});

test("deleted entities are loaded only when their drawer opens", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  let renders = 0;
  panel._render = () => { renders += 1; };
  const response = {
    entities: [{
      entity_id: "sensor.deleted",
      name: null,
      platform: "test",
      deleted_at: "2026-08-24T12:00:00+00:00",
    }],
  };
  const calls = [];
  panel._hass = {
    async callWS(message) {
      calls.push(message);
      return response;
    },
  };

  assert.deepEqual(calls, []);
  await panel._handleClick({
    target: {
      closest() {
        return { dataset: { action: "open-deleted-entities" } };
      },
    },
  });

  assert.deepEqual(calls, [{
    type: "alert_manager/coherence/deleted_entities/list",
  }]);
  assert.deepEqual(panel._deletedEntitiesState.data, response);
  assert.deepEqual(panel._configurationDrawer, { kind: "deleted-entities" });
  assert.equal(panel._deletedEntitiesState.loading, false);
  assert.equal(renders, 2);

  await panel._handleClick({
    target: {
      closest() {
        return { dataset: { action: "close-deleted-entities" } };
      },
    },
  });
  assert.equal(panel._configurationDrawer, null);
  assert.equal(renders, 3);
});

test("coherence scan date is red only when older than 48 hours", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._coherence = {
    results: [],
    missing_count: 0,
    files_scanned: 4,
    references_checked: 12,
    duration_ms: 8,
    scanned_at: "2026-08-25T11:59:59+00:00",
  };
  const originalNow = Date.now;
  Date.now = () => Date.parse("2026-08-27T12:00:00+00:00");
  try {
    const stale = panel._renderCoherence();
    assert.match(stale, /coherence-scan-date stale/);
    assert.match(stale, /Dernière analyse/);

    panel._coherence.scanned_at = "2026-08-25T12:00:01+00:00";
    const fresh = panel._renderCoherence();
    assert.match(fresh, /coherence-scan-date/);
    assert.doesNotMatch(fresh, /coherence-scan-date stale/);
  } finally {
    Date.now = originalNow;
  }
});

test("external coherence scans refresh the open panel even when the count is unchanged", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "coherence";
  panel._coherenceLoaded = true;
  panel._coherenceScannedAt = "2026-08-24T12:00:00+00:00";
  panel._coherence = {
    missing_entity_count: 2,
    scanned_at: panel._coherenceScannedAt,
    results: [{ entity_id: "sensor.old" }],
  };
  const refreshed = {
    missing_entity_count: 2,
    scanned_at: "2026-08-24T13:00:00+00:00",
    results: [{ entity_id: "sensor.new" }],
  };
  const calls = [];
  panel._render = () => {};

  panel.hass = {
    locale: { language: "fr" },
    states: {
      "sensor.alert_manager_coherence_issue": {
        state: "2",
        attributes: { scanned_at: refreshed.scanned_at },
      },
    },
    callWS: async (message) => {
      calls.push(message);
      return refreshed;
    },
  };
  await panel._coherenceLoadPromise;

  assert.deepEqual(calls, [{ type: "alert_manager/coherence/get" }]);
  assert.equal(panel._coherence, refreshed);
});

test("coherence result actions open their exact Home Assistant target", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  let navigatedTo = null;
  let moreInfo = null;
  panel._navigate = (path) => { navigatedTo = path; };
  panel._openMoreInfo = (entityId) => { moreInfo = entityId; };

  const navigation = panel._nativeCoherenceActionCell({
    link: { type: "navigate", path: "/config/automation/edit/123" },
  });
  navigation.listeners.click({ stopPropagation() {} });
  assert.equal(navigatedTo, "/config/automation/edit/123");

  const template = panel._nativeCoherenceActionCell({
    link: { type: "more_info", entity_id: "sensor.template_result" },
  });
  template.listeners.click({ stopPropagation() {} });
  assert.equal(moreInfo, "sensor.template_result");
});

test("closing more info restores the mobile overview scroll position", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const scroller = { scrollTop: 96 };
  const listeners = new Map();
  const eventTarget = {
    addEventListener(name, listener) { listeners.set(name, listener); },
    removeEventListener(name, listener) {
      if (listeners.get(name) === listener) listeners.delete(name);
    },
  };
  panel._hass = { states: { "sensor.mobile": {} } };
  panel._narrow = true;
  panel._overviewContentScroller = () => scroller;
  panel._dialogEventTarget = () => eventTarget;
  const previousAnimationFrame = globalThis.requestAnimationFrame;
  const animationFrames = [];
  globalThis.requestAnimationFrame = (callback) => {
    animationFrames.push(callback);
    return animationFrames.length;
  };
  try {
    panel._openMoreInfo("sensor.mobile");
    assert.equal(panel.dispatchedEvent.detail.entityId, "sensor.mobile");
    listeners.get("dialog-closed")({ detail: { dialog: "another-dialog" } });
    assert.equal(listeners.has("dialog-closed"), true);
    scroller.scrollTop = 0;
    listeners.get("dialog-closed")({ detail: { dialog: "ha-more-info-dialog" } });
    assert.equal(scroller.scrollTop, 96);
    scroller.scrollTop = 24;
    animationFrames.shift()();
    scroller.scrollTop = 12;
    animationFrames.shift()();
  } finally {
    globalThis.requestAnimationFrame = previousAnimationFrame;
  }
  assert.equal(scroller.scrollTop, 96);
  assert.equal(listeners.has("dialog-closed"), false);
});

test("more info scroll restoration is limited to the mobile overview", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const eventTarget = {
    calls: 0,
    addEventListener() { this.calls += 1; },
    removeEventListener() {},
  };
  panel._hass = { states: { "sensor.desktop": {} } };
  panel._narrow = false;
  panel._dialogEventTarget = () => eventTarget;
  panel._overviewContentScroller = () => ({ scrollTop: 42 });
  panel._openMoreInfo("sensor.desktop");
  assert.equal(eventTarget.calls, 0);

  panel._narrow = true;
  panel._activeTab = "coherence";
  panel._openMoreInfo("sensor.desktop");
  assert.equal(eventTarget.calls, 0);
});

test("reconnecting during initial load does not duplicate WebSocket requests", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = {};
  panel._render = () => {};
  panel._loadPromise = Promise.resolve();
  let loads = 0;
  let intervals = 0;
  panel._load = () => { loads += 1; };
  const previousSetInterval = window.setInterval;
  window.setInterval = () => { intervals += 1; return intervals; };
  try {
    panel.connectedCallback();
    panel.connectedCallback();
  } finally {
    window.setInterval = previousSetInterval;
  }
  assert.equal(loads, 0);
  assert.equal(intervals, 1);
});

test("a directly loaded panel replays pre-upgrade Home Assistant properties", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const hass = { locale: { language: "fr" }, states: {} };
  const route = { prefix: "/alert-manager", path: "/settings" };
  const panelConfig = { title: "Alert Manager" };
  Object.defineProperties(panel, {
    hass: { configurable: true, writable: true, value: hass },
    route: { configurable: true, writable: true, value: route },
    panel: { configurable: true, writable: true, value: panelConfig },
    narrow: { configurable: true, writable: true, value: true },
  });
  panel._render = () => {};
  let loads = 0;
  panel._load = () => {
    loads += 1;
    panel._loadPromise = Promise.resolve();
  };
  const previousSetInterval = window.setInterval;
  window.setInterval = () => 1;
  try {
    panel.connectedCallback();
  } finally {
    window.setInterval = previousSetInterval;
  }

  assert.equal(Object.hasOwn(panel, "hass"), false);
  assert.equal(Object.hasOwn(panel, "route"), false);
  assert.equal(Object.hasOwn(panel, "panel"), false);
  assert.equal(Object.hasOwn(panel, "narrow"), false);
  assert.equal(panel._hass, hass);
  assert.equal(panel._route, route);
  assert.equal(panel._panel, panelConfig);
  assert.equal(panel._narrow, true);
  assert.equal(panel._activeTab, "settings");
  assert.equal(loads, 1);
});

test("an open side drawer follows Home Assistant narrow resize changes", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._activeTab = "settings";
  panel._configurationDrawer = { kind: "settings", id: "entity_delays" };
  let captures = 0;
  let renders = 0;
  panel._captureEntityDelayValues = () => { captures += 1; };
  panel._loadNativeBottomSheet = async () => true;
  panel._render = () => { renders += 1; };

  panel.narrow = true;
  await Promise.resolve();
  assert.equal(captures, 1);
  assert.equal(renders, 1);

  panel.narrow = false;
  assert.equal(captures, 2);
  assert.equal(renders, 2);
  panel.narrow = false;
  assert.equal(renders, 2);
});

test("new rules start enabled with safe defaults", () => {
  assert.deepEqual(newRuleDefaults(), {
    name: "",
    entity_ids: [],
    enabled: true,
    source: "state",
    attribute: "",
    operator: "equals",
    value: [""],
    duration: 900,
    message: "",
    update_message_when_active: false,
    condition_template: "",
    flapping_enabled: false,
    flapping_occurrences: null,
    flapping_window: null,
    flapping_recovery: null,
  });
});

test("valid YAML switches back to the visual rule editor", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._render = () => {};
  panel._editingRule = { ...ruleValues(), id: "stable" };
  panel._ruleEditorMode = "yaml";
  panel._ruleYaml = "name: Liste vide\n";
  panel._call = async () => ({
    name: "Liste YAML",
    enabled: true,
    entity_ids: ["todo.liste_d_achats"],
    source: "state",
    operator: "equals",
    value: ["0"],
    duration: 900,
    message: null,
  });
  await panel._switchRuleEditor();
  assert.equal(panel._ruleEditorMode, "visual");
  assert.equal(panel._editingRule.name, "Liste YAML");
  assert.equal(panel._editingRule.id, "stable");
});

test("invalid YAML stays in the YAML editor", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._render = () => {};
  panel._editingRule = { ...ruleValues() };
  panel._ruleEditorMode = "yaml";
  panel._ruleYaml = "name: [broken";
  panel._notice = { kind: "error", text: "Invalid YAML" };
  panel._call = async () => null;
  await panel._switchRuleEditor();
  assert.equal(panel._ruleEditorMode, "yaml");
  assert.equal(panel._ruleYamlError, "Invalid YAML");
});

test("unrelated Home Assistant updates do not rerender the overview", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = { rules: [] };
  let renders = 0;
  panel._render = () => { renders += 1; };
  const active = {
    state: "0",
    attributes: { alerts: [] },
  };
  const pending = { state: "0", attributes: { alerts: [] } };
  const acknowledge = { state: "0", attributes: { alerts: [] } };
  const monitoring = { state: "on", attributes: {} };
  const states = {
    "sensor.alert_manager_main_active": active,
    "sensor.alert_manager_main_pending": pending,
    "sensor.alert_manager_main_acknowledge": acknowledge,
    "switch.alert_manager_main_monitoring": monitoring,
  };
  panel.hass = { states };
  panel.hass = {
    states: { ...states, "sensor.other": { state: "1" } },
  };
  assert.equal(renders, 1);
});

const completeConfig = () => ({
  monitoring_enabled: true,
  history_limit: 100,
  coherence_schedule: