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
  coherence_schedule: "none",
  coherence_scan_esphome: true,
  coherence_ignored_entity_references: [],
  automatic: {
    unavailable: { enabled: true, delay: 900 },
    connectivity: { enabled: true, delay: 900 },
    unifi: { enabled: true, delay: 900 },
    battery: { enabled: true, delay: 900, threshold: 15, device_thresholds: {} },
  },
  rules: [],
  global_delay: 900,
  pending_display_delay: 10,
  excluded_labels: [],
  excluded_entities: [],
  excluded_devices: [],
  entity_delays: {},
});

test("partitioned entities update counts without replacing full websocket rows", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel.hass = {
    states: {
      "sensor.alert_manager_main_active": {
        state: "1",
        attributes: { alerts: [{ id: "active" }] },
      },
      "sensor.alert_manager_main_pending": {
        state: "2",
        attributes: { alerts: [{ id: "pending-1" }, { id: "pending-2" }] },
      },
      "sensor.alert_manager_main_acknowledge": {
        state: "1",
        attributes: { alerts: [{ id: "acknowledged" }] },
      },
      "switch.alert_manager_main_monitoring": { state: "on", attributes: {} },
    },
  };
  assert.equal(panel._alerts.active_count, 1);
  assert.equal(panel._alerts.pending_count, 2);
  assert.equal(panel._alerts.acknowledge_count, 1);
  assert.deepEqual(panel._alerts.alerts, []);
  assert.deepEqual(panel._alerts.pending, []);
  assert.deepEqual(panel._alerts.acknowledge, []);
});

test("complete alert rows are refreshed through the websocket API", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  const snapshot = {
    active_count: 1,
    pending_count: 1,
    acknowledge_count: 0,
    tracked_count: 2,
    alerts: [{ id: "active", entity_id: "sensor.active", device_name: "Rack" }],
    pending: [{ id: "pending", entity_id: "sensor.pending", condition: "Hot" }],
    acknowledge: [],
  };
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return snapshot;
    },
  };

  await panel._refreshAlerts();

  assert.deepEqual(calls, [{ type: "alert_manager/alerts/list" }]);
  assert.deepEqual(panel._alerts, snapshot);
});

test("overview row changes update the native table without rebuilding the page", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._alerts = {
    active_count: 1,
    acknowledge_count: 0,
    pending_count: 0,
    tracked_count: 1,
    alerts: [{
      id: "unavailable:sensor.test",
      type: "unavailable",
      entity_id: "sensor.test",
      name: "Test",
      condition: "Unavailable",
      detected_at: "2026-08-27T10:00:00Z",
      active_since: "2026-08-27T10:00:10Z",
    }],
    pending: [],
    acknowledge: [],
  };
  panel._hass = { entities: {}, states: {} };
  const summaries = Object.fromEntries(["active", "pending", "acknowledged", "tracked"].map(
    (key) => [key, { textContent: "" }],
  ));
  const tablePage = {
    querySelector(selector) {
      const key = selector.match(/data-summary="([^"]+)/)?.[1];
      return summaries[key] ?? null;
    },
  };
  panel.shadowRoot.querySelector = (selector) =>
    selector === '[data-alert-table-page="overview"]' ? tablePage : null;
  panel._updateCountdowns = () => {};
  let renders = 0;
  panel._render = () => { renders += 1; };

  panel._refreshOverviewData();

  assert.equal(renders, 0);
  assert.equal(summaries.active.textContent, "1");
  assert.deepEqual(tablePage.data.map((row) => row.id), ["unavailable:sensor.test"]);
});

test("history data refresh updates the native table without rebuilding the page", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._activeTab = "history";
  panel._historyConfig = { retention_limit: 100, enabled: true };
  panel._history = { events: [], count: 0, retention_limit: 100, enabled: true };
  panel._hass = { entities: {}, states: {} };
  const tablePage = {};
  const messages = { innerHTML: "" };
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === '[data-alert-table-page="history"]') return tablePage;
    if (selector === "[data-page-messages]") return messages;
    return null;
  };
  let renders = 0;
  panel._render = () => { renders += 1; };

  panel._refreshHistoryData();

  assert.equal(renders, 0);
  assert.deepEqual(tablePage.data, []);
});

test("coherence data refresh updates stats and rows without rebuilding the page", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._activeTab = "coherence";
  panel._coherence = {
    results: [{
      entity_id: "sensor.missing",
      source_type: "automation",
      source_name: "Test",
      file: "automations.yaml",
      line: 12,
    }],
    missing_count: 1,
    files_scanned: 2,
    references_checked: 3,
    duration_ms: 4,
  };
  const stats = { innerHTML: "" };
  const label = { textContent: "" };
  const button = { disabled: false, querySelector: () => label };
  const tablePage = {
    querySelector(selector) {
      if (selector === "[data-coherence-stats]") return stats;
      if (selector === '[data-action="scan-coherence"]') return button;
      return null;
    },
  };
  const messages = { innerHTML: "" };
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "[data-coherence-table-page]") return tablePage;
    if (selector === "[data-page-messages]") return messages;
    return null;
  };
  let renders = 0;
  panel._render = () => { renders += 1; };

  panel._refreshCoherenceData();

  assert.equal(renders, 0);
  assert.equal(tablePage.data.length, 1);
  assert.match(stats.innerHTML, /1/);
});

test("rules data refresh updates filtered rows without rebuilding the page", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._activeTab = "rules";
  panel._config = {
    ...completeConfig(),
    rules: [{ ...ruleValues({ id: "rule-1", enabled: true }), entity_ids: ["sensor.one"] }],
  };
  const tablePage = {};
  const messages = { innerHTML: "" };
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "[data-rules-table-page]") return tablePage;
    if (selector === "[data-page-messages]") return messages;
    return null;
  };
  let renders = 0;
  panel._render = () => { renders += 1; };

  panel._refreshRulesData();

  assert.equal(renders, 0);
  assert.deepEqual(tablePage.data.map((row) => row.id), ["rule-1"]);
});

test("websocket actions update busy state and messages without rebuilding the page", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { callWS: async () => ({ ok: true }) };
  const messages = { innerHTML: "" };
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-page-messages]" ? messages : null
  );
  let renders = 0;
  panel._render = () => { renders += 1; };

  const result = await panel._call({ type: "alert_manager/test" }, "Saved");

  assert.deepEqual(result, { ok: true });
  assert.equal(renders, 0);
  assert.equal(panel._busy, false);
  assert.match(messages.innerHTML, /Saved/);
});

test("disabled monitoring warning can turn the switch back on", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = { ...completeConfig(), monitoring_enabled: false };
  panel._loading = false;
  panel._monitoringEnabled = false;
  const calls = [];
  panel._hass = {
    states: {},
    callService: async (...args) => { calls.push(args); },
  };
  panel._render();
  assert.match(panel.shadowRoot.innerHTML, /<ha-alert class="page-alert" alert-type="warning"/);
  assert.match(panel.shadowRoot.innerHTML, /<ha-button slot="action"/);
  assert.match(panel.shadowRoot.innerHTML, /La surveillance Alert Manager est désactivée/);

  await panel._handleClick(actionEvent("enable-monitoring"));
  assert.deepEqual(calls, [[
    "switch",
    "turn_on",
    { entity_id: "switch.alert_manager_main_monitoring" },
  ]]);
  assert.equal(panel._monitoringEnabled, true);
  assert.doesNotMatch(panel._pageMessagesContent(), /alert-type="warning"/);
});

const completePacks = () => [
  {
    id: "unavailable",
    translation_key: "unavailable",
    prerequisites: [],
    available: true,
  },
  {
    id: "connectivity",
    translation_key: "connectivity",
    prerequisites: [],
    available: true,
  },
  {
    id: "unifi",
    translation_key: "unifi",
    prerequisites: ["unifi"],
    available: true,
  },
  {
    id: "battery",
    translation_key: "battery",
    prerequisites: [],
    available: true,
    config_fields: [
      {
        id: "threshold",
        type: "number",
        translation_key: "threshold",
        default: 15,
        minimum: -1000000000,
        maximum: 1000000000,
        step: "any",
        unit: "%",
      },
      {
        id: "device_thresholds",
        type: "device_number_map",
        translation_key: "device_thresholds",
        default: {},
        minimum: -1000000000,
        maximum: 1000000000,
        step: "any",
        unit: "%",
      },
    ],
  },
];

const form = (values) => ({
  elements: {
    namedItem(name) {
      if (!(name in values)) return null;
      return ["enabled", "update_message_when_active"].includes(name)
        ? { checked: values[name] }
        : { value: values[name] };
    },
  },
  reportValidity: () => true,
});

const ruleValues = (changes = {}) => ({
  id: "",
  name: "Liste vide",
  entity_ids: ["todo.liste_d_achats"],
  enabled: true,
  source: "state",
  attribute: "",
  operator: "equals",
  value: "0",
  duration: "900",
  message: "",
  update_message_when_active: false,
  ...changes,
});

const actionEvent = (action, id, dataset = {}) => ({
  target: {
    closest() {
      return { dataset: { action, ...(id ? { id } : {}), ...dataset } };
    },
  },
});

test("initial load requests pack metadata from the backend", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._render = () => {};
  const calls = [];
  const retainedCoherence = {
    results: [{ entity_id: "sensor.gone" }],
    missing_count: 1,
    missing_entity_count: 1,
    scanned_at: "2026-08-24T12:00:00+00:00",
  };
  const responses = {
    "alert_manager/config/get": completeConfig(),
    "alert_manager/alerts/list": {
      active_count: 0,
      pending_count: 0,
      tracked_count: 0,
      alerts: [],
      pending: [],
    },
    "alert_manager/packs/list": completePacks(),
    "alert_manager/history/list": {
      events: [], count: 0, retention_limit: 100, enabled: true,
    },
    "alert_manager/history/config/get": { retention_limit: 100, enabled: true },
    "alert_manager/coherence/get": retainedCoherence,
    "config/label_registry/list": [],
  };
  panel._hass = {
    states: {},
    callWS: async (message) => {
      calls.push(message.type);
      if (message.type === "frontend/get_translations") {
        return { resources: TRANSLATIONS[message.language] };
      }
      return responses[message.type];
    },
  };

  await panel._load();

  assert.deepEqual(calls, [
    "alert_manager/config/get",
    "alert_manager/alerts/list",
    "alert_manager/packs/list",
    "alert_manager/history/list",
    "alert_manager/history/config/get",
    "alert_manager/coherence/get",
    "config/label_registry/list",
    "frontend/get_translations",
    "frontend/get_translations",
  ]);
  assert.deepEqual(panel._packs, completePacks());
  assert.equal(panel._coherence, retainedCoherence);
});

test("rule save button explicitly creates a rule and keeps typed values", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = { entity_ids: ["todo.liste_d_achats"] };
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "created-id", version: 2 };
    },
  };
  const ruleForm = form(ruleValues());
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "#rule-form") return ruleForm;
    if (selector === "#rule-condition-template") return { value: "{{ true }}" };
    if (selector === "#rule-message-template") {
      return { value: "État :\n{{ states('todo.liste_d_achats') }}" };
    }
    return null;
  };
  panel._render = () => {};

  await panel._handleClick(actionEvent("save-rule"));

  assert.deepEqual(calls, [
    {
      type: "alert_manager/rules/create",
      rule: {
        name: "Liste vide",
        entity_ids: ["todo.liste_d_achats"],
        enabled: true,
        source: "state",
        attribute: null,
        operator: "equals",
        value: ["0"],
        duration: 900,
        message: "État :\n{{ states('todo.liste_d_achats') }}",
        update_message_when_active: false,
        condition_template: "{{ true }}",
      },
    },
  ]);
  assert.equal(panel._config.rules[0].id, "created-id");
  assert.equal(panel._editingRule, null);
});

test("rule create errors remain visible without clearing the draft", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._hass = { callWS: async () => { throw new Error("Règle refusée"); } };
  panel._editingRule = { entity_ids: ["todo.liste_d_achats"] };
  panel._render = () => {};

  await panel._saveRule(form(ruleValues()));

  assert.equal(panel._notice, null);
  assert.equal(panel._ruleEditorError, "Une erreur inattendue s’est produite.");
  assert.deepEqual(panel._editingRule.entity_ids, ["todo.liste_d_achats"]);
  assert.deepEqual(panel._editingRule.value, ["0"]);
});

test("backend rule validation errors are localized without leaking English", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const validationError = (message) => ({ code: "invalid_format", message });

  assert.equal(
    panel._errorText(validationError("Range lower bound must not exceed upper bound")),
    "La borne inférieure doit être inférieure ou égale à la borne supérieure.",
  );
  assert.equal(
    panel._errorText(validationError("Range operators require two finite numeric bounds")),
    "Les deux bornes doivent être des nombres valides.",
  );
  assert.equal(
    panel._errorText(validationError("Text operator values must be unique")),
    "Les valeurs de comparaison doivent être uniques.",
  );
  assert.equal(
    panel._errorText(validationError("Invalid rule condition_template: parser details")),
    "Le code Jinja de la règle est invalide.",
  );
  assert.equal(
    panel._errorText(validationError("Invalid YAML: parser details")),
    "Le YAML est invalide. Vérifiez sa syntaxe.",
  );
  assert.equal(
    panel._errorText(validationError("A future backend validation message")),
    "Les données sont invalides. Vérifiez les champs et réessayez.",
  );
});

test("text rules serialize several trimmed comparison values", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = { entity_ids: ["sensor.ups"] };
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "contains-id", version: 2 };
    },
  };
  const ruleForm = form(ruleValues({
    name: "UPS",
    entity_ids: ["sensor.ups"],
    operator: "contains",
    value: "unused fallback",
  }));
  ruleForm.querySelectorAll = (selector) => selector === "[data-rule-value-index]"
    ? [{ value: " CHRG " }, { value: "ERROR" }]
    : [];
  panel._render = () => {};

  await panel._saveRule(ruleForm);

  assert.deepEqual(calls[0].rule.value, ["CHRG", "ERROR"]);
  assert.equal(calls[0].rule.operator, "contains");
});

const currentAlert = (changes = {}) => ({
  id: "rule:temperature:sensor.rack",
  type: "rule",
  rule_id: "temperature",
  rule_name: "Température baie",
  entity_id: "sensor.rack",
  name: "Température rack",
  device_id: "device-rack",
  device_name: "Sonde rack",
  area: "Bureau",
  message: "Refroidir la baie",
  value: 34.5,
  unit: "°C",
  condition: "État supérieur à 33 °C pendant 30 s",
  detected_at: "2026-08-26T12:00:00Z",
  due_at: "2026-08-26T12:00:30Z",
  active_since: "2026-08-26T12:00:30Z",
  ...changes,
});

const tablePanel = () => {
  window.localStorage.clear();
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._labels = [{
    label_id: "critical",
    name: "Critique",
    color: "purple",
    description: "Alerte importante",
  }];
  panel._hass = {
    states: {
      "sensor.rack": { state: "35" },
      "sensor.pending": { state: "10" },
      "sensor.acknowledged": { state: "unavailable" },
    },
    entities: {
      "sensor.rack": { platform: "mqtt", labels: ["critical"] },
      "sensor.pending": { platform: "mqtt", labels: [] },
      "sensor.acknowledged": { platform: "hassio", labels: [] },
    },
    localize: (key) => ({
      "component.mqtt.title": "MQTT",
      "component.hassio.title": "Home Assistant Supervisor",
    })[key],
  };
  panel._alerts = {
    active_count: 1,
    pending_count: 1,
    acknowledge_count: 1,
    tracked_count: 3,
    alerts: [currentAlert()],
    pending: [currentAlert({
      id: "battery:sensor.pending",
      type: "battery",
      rule_name: null,
      entity_id: "sensor.pending",
      name: "Batterie UPS",
      device_id: null,
      device_name: null,
      area: "Garage",
      message: null,
      value: 10,
      unit: "%",
      condition: "Batterie inférieure ou égale à 15%",
      condition_key: "automatic.battery",
      condition_params: { threshold: "15" },
      detected_at: "2026-08-26T12:05:00Z",
      due_at: "2099-08-26T12:15:00Z",
      active_since: null,
    })],
    acknowledge: [currentAlert({
      id: "unavailable:sensor.acknowledged",
      type: "unavailable",
      rule_name: null,
      entity_id: "sensor.acknowledged",
      name: "NAS",
      device_id: "device-nas",
      device_name: "NAS",
      value: "unavailable",
      unit: null,
      detected_at: "2026-08-26T11:00:00Z",
      active_since: "2026-08-26T11:15:00Z",
      acknowledged: true,
      acknowledged_at: "2026-08-26T11:20:00Z",
      acknowledged_by: "Loïc",
    })],
  };
  return panel;
};

test("alert table links keep entity, rule and device navigation separate from row details", () => {
  const panel = tablePanel();
  panel._config.rules = [{ id: "temperature", name: "Température baie" }];
  const row = panel._tableRows("overview")[0];
  const calls = [];
  panel._openMoreInfo = (entityId) => calls.push(["entity", entityId]);
  panel._navigate = (path) => calls.push(["device", path]);
  panel._openRuleEditor = (ruleId, options) => calls.push(["rule", ruleId, options]);
  const event = () => ({
    prevented: false,
    stopped: false,
    preventDefault() { this.prevented = true; },
    stopPropagation() { this.stopped = true; },
  });

  const entity = panel._nativeEntityCell(row).children[0];
  const entityEvent = event();
  entity.listeners.click(entityEvent);
  assert.equal(entityEvent.prevented, true);
  assert.equal(entityEvent.stopped, true);

  const entityId = panel._nativeEntityIdCell(row);
  entityId.listeners.click(event());
  const device = panel._nativeDeviceCell(row);
  device.listeners.click(event());
  const rule = panel._nativeRuleCell(row);
  rule.listeners.click(event());
  const narrowDevice = panel._nativeEntityCell(row, true, "overview").children[1].children[0];
  narrowDevice.listeners.click(event());

  assert.deepEqual(calls, [
    ["entity", "sensor.rack"],
    ["entity", "sensor.rack"],
    ["device", "/config/devices/device/device-rack"],
    ["rule", "temperature", { navigate: true }],
    ["device", "/config/devices/device/device-rack"],
  ]);
});

test("clicking an alert row opens its detail dialog instead of entity more info", () => {
  const panel = tablePanel();
  const listeners = {};
  const table = {
    addEventListener(name, listener) { listeners[name] = listener; },
    querySelectorAll() { return []; },
    dataset: { alertTablePage: "overview" },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );
  const opened = [];
  panel._openAlertDetails = (kind, row) => opened.push([kind, row.id]);
  panel._openMoreInfo = () => assert.fail("row click must not open more info");

  panel._hydrateDataTables();
  listeners["row-click"]({ detail: { id: "rule:temperature:sensor.rack" } });

  assert.deepEqual(opened, [["overview", "rule:temperature:sensor.rack"]]);
});

test("alert details expose translated fields and contextual links", () => {
  const panel = tablePanel();
  panel._config.rules = [{ id: "temperature", name: "Température baie" }];
  const row = panel._tableRows("overview")[0];
  const html = panel._renderAlertDetails("overview", row);

  assert.match(html, /alert-details-summary alert-details-status-active/);
  assert.match(html, /alert-details-status-label">Alerte active/);
  assert.match(html, /alert-details-entity table-cell-link/);
  assert.match(html, /alert-details-highlight[\s\S]*Message[\s\S]*Refroidir la baie/);
  assert.match(html, /alert-details-highlight[\s\S]*Condition[\s\S]*État supérieur/);
  assert.match(html, /data-action="more-info" data-entity-id="sensor\.rack"/);
  assert.match(html, /data-action="open-alert-device" data-device-id="device-rack"/);
  assert.match(html, /data-action="open-alert-rule" data-rule-id="temperature"/);
  assert.match(html, /ID de l’alerte/);
  assert.match(html, /data-action="close-alert-details">Fermer/);
});

test("more info opens only after the alert details dialog is fully closed", async () => {
  const panel = tablePanel();
  const listeners = {};
  const dialog = {
    open: true,
    removed: false,
    addEventListener(name, listener) { listeners[name] = listener; },
    remove() { this.removed = true; },
  };
  panel._alertDetailsDialog = dialog;
  let openedEntity = null;
  panel._openMoreInfo = (entityId) => { openedEntity = entityId; };
  const click = {
    prevented: false,
    stopped: false,
    preventDefault() { this.prevented = true; },
    stopPropagation() { this.stopped = true; },
    target: {
      closest() {
        return { dataset: { action: "more-info", entityId: "sensor.rack" } };
      },
    },
  };

  await panel._handleClick(click);

  assert.equal(click.prevented, true);
  assert.equal(click.stopped, true);
  assert.equal(dialog.open, false);
  assert.equal(openedEntity, null);
  listeners.closed();
  assert.equal(dialog.removed, true);
  assert.equal(openedEntity, "sensor.rack");
});

test("opening a custom rule from an alert navigates and opens its editor", () => {
  const panel = tablePanel();
  const configuredRule = {
    id: "temperature",
    name: "Température baie",
    entity_ids: ["sensor.rack"],
  };
  panel._config.rules = [configuredRule];
  const navigations = [];
  let renders = 0;
  panel._navigate = (path) => navigations.push(path);
  panel._render = () => { renders += 1; };

  assert.equal(panel._openRuleEditor("temperature", { navigate: true }), true);
  assert.deepEqual(navigations, ["/alert-manager/rules"]);
  assert.equal(panel._activeTab, "rules");
  assert.deepEqual(panel._editingRule, configuredRule);
  assert.notEqual(panel._editingRule, configuredRule);
  assert.equal(renders, 1);
});

test("dashboard renders one compact table with the required default columns and statuses", () => {
  const panel = tablePanel();
  const html = panel._renderOverview();
  assert.deepEqual(panel._tableState.overview.columns, [
    "status", "entity", "device", "rule", "integration", "timeline",
  ]);
  assert.equal(panel._tableState.overview.sortBy, "status");
  assert.equal(panel._tableState.overview.sortDirection, "asc");
  assert.deepEqual(panel._tableState.overview.filters.status, ["active"]);
  assert.equal(panel._filterCount("overview"), 1);
  assert.deepEqual(
    panel._filteredTableRows("overview", panel._tableRows("overview")).map((row) => row.status),
    ["active"],
  );
  assert.match(
    html,
    /data-table-filter-option="status" data-filter-value="active" checked/,
  );
  assert.match(html, /<hass-tabs-subpage-data-table[\s\S]*data-alert-table-page="overview"[\s\S]*selectable/);
  assert.match(html, /slot="filter-pane"/);
  assert.match(html, /slot="selection-bar"/);
  assert.doesNotMatch(html, /<ha-input-search|data-table-dropdown|class="table-toolbar"/);
  assert.doesNotMatch(html, /<table|<thead|<tbody|alert-card|device-alert-group/);
  const rows = panel._nativeTableData("overview", panel._tableRows("overview"));
  assert.equal(rows.length, 3);
  assert.deepEqual(new Set(rows.map((row) => row.statusLabel)), new Set([
    "Alerte active", "Alerte à venir", "Alerte acquittée",
  ]));
  const active = rows.find((row) => row.status === "active");
  const pending = rows.find((row) => row.status === "pending");
  assert.equal(active.value, "34.5 °C");
  assert.equal(active.condition, "État supérieur à 33 °C pendant 30 s");
  assert.equal(pending.message, "Batterie inférieure ou égale à 15 %");
  assert.equal(panel._nativeTableCell("overview", active, "integration"), "MQTT");
  const status = panel._nativeStatusCell(active, "overview");
  assert.equal(status.attributes["aria-label"], "Alerte active");
  assert.equal(status.children[0].tagName, "HA-SVG-ICON");
  assert.match(status.style.cssText, /align-items:center;justify-content:center/);
  assert.match(status.children[0].style.cssText, /margin:0/);
  assert.match(status.children[0].style.cssText, /translate\(-50%,-50%\)/);
});

test("native Home Assistant data table receives columns, rows, sort and visibility", () => {
  const panel = tablePanel();
  panel._tableState.overview.search = "garage";
  const table = { addEventListener() {}, querySelectorAll() { return []; }, dataset: {} };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );

  panel._hydrateDataTables();

  assert.equal(table.columns.status.title, "");
  assert.equal(table.columns.status.label, "Statut");
  assert.equal(table.columns.status.showNarrow, true);
  assert.equal(table.columns.entity.main, true);
  assert.equal(table.columns.entity.sortable, true);
  assert.equal(table.columns.integration.title, "Intégration");
  assert.equal(table.columns.integration.sortable, true);
  assert.equal(table.columns.integration.defaultHidden, false);
  assert.equal(table.columns.timeline.defaultHidden, false);
  assert.equal(table.columns.value.defaultHidden, true);
  assert.equal(table.columns.condition.defaultHidden, true);
  assert.equal(table.columns.entity.minWidth, "180px");
  assert.equal(table.columns.entity.maxWidth, undefined);
  assert.equal(table.columns.entity.flex, 1.4);
  assert.equal(table.columns.timeline.maxWidth, undefined);
  assert.equal(table.columns.timeline.flex, 1.2);
  assert.equal(table.columns.condition.showNarrow, false);
  assert.equal(table.data.length, 1);
  assert.equal(table.data[0].status, "active");
  assert.equal(table.filters, 1);
  assert.equal(table.filter, "garage");
  assert.equal(table.id, "id");
  assert.deepEqual(table.initialSorting, { column: "status", direction: "asc" });
  assert.equal(table.selectable, true);
  assert.equal(table.clickable, true);
  assert.deepEqual(
    table.columnOrder.slice(0, panel._tableState.overview.columns.length),
    panel._tableState.overview.columns,
  );
  assert.ok(table.hiddenColumns.includes("entity_id"));
  assert.equal(table.columns.device_group.groupable, true);
  assert.equal(table.columns.search_index.filterable, true);
  const historyColumns = panel._nativeTableColumns("history");
  assert.equal(historyColumns.detected.defaultHidden, false);
  assert.equal(historyColumns.resolved.defaultHidden, true);
  assert.equal(historyColumns.detected.maxWidth, undefined);
});

test("pending countdown is dynamic only while monitoring is enabled", () => {
  const panel = tablePanel();
  const pending = panel._tableRows("overview").find((row) => row.status === "pending");
  const enabled = panel._nativeTimelineCell(pending);
  assert.equal(enabled.children[1].dataset.due, "2099-08-26T12:15:00Z");
  panel._monitoringEnabled = false;
  const suspended = panel._nativeTimelineCell(pending);
  assert.equal(suspended.children[1].dataset.due, undefined);
  assert.equal(suspended.children[1].textContent, "Délai suspendu — surveillance désactivée");

  const node = { dataset: { due: "2099-08-26T12:15:00Z" }, textContent: "stable" };
  panel.shadowRoot.querySelectorAll = () => [node];
  panel._updateCountdowns();
  assert.equal(node.textContent, "stable");

  const nestedNode = { dataset: { due: "2099-08-26T12:15:00Z" }, textContent: "stable" };
  const nativeTable = {
    shadowRoot: {
      querySelectorAll(selector) { return selector === "[data-due]" ? [nestedNode] : []; },
    },
  };
  const tablePage = {
    shadowRoot: {
      querySelector(selector) { return selector === "ha-data-table" ? nativeTable : null; },
    },
  };
  panel._monitoringEnabled = true;
  panel._remaining = (due) => `updated:${due}`;
  panel.shadowRoot.querySelectorAll = (selector) => {
    if (selector === "[data-alert-table-page]") return [tablePage];
    return [];
  };
  panel._updateCountdowns();
  assert.equal(nestedNode.textContent, "updated:2099-08-26T12:15:00Z");

  panel._render = () => {};
  panel.hass = {
    states: {
      "sensor.alert_manager_main_active": { state: "0", attributes: { alerts: [] } },
      "sensor.alert_manager_main_pending": { state: "0", attributes: { alerts: [] } },
      "sensor.alert_manager_main_acknowledge": { state: "0", attributes: { alerts: [] } },
      "switch.alert_manager_main_monitoring": { state: "off", attributes: {} },
    },
  };
  assert.equal(panel._alerts.pending.length, 1);
});

test("search covers alert fields and Home Assistant entity metadata", () => {
  const panel = tablePanel();
  const rows = panel._tableRows("overview");
  for (const query of [
    "Température baie", "sensor.rack", "Sonde rack", "Bureau", "Refroidir",
    "supérieur à 33", "34.5", "Alerte active", "mqtt", "Critique", "sensor",
  ]) {
    panel._tableState.overview.search = query;
    assert.ok(panel._filteredTableRows("overview", rows).some((row) => (
      row.id === "rule:temperature:sensor.rack"
    )));
  }
});

test("filters combine and can be reset without changing table data", () => {
  const panel = tablePanel();
  const rows = panel._tableRows("overview");
  panel._tableState.overview.filters.status = ["pending"];
  panel._tableState.overview.filters.area = ["Garage"];
  assert.deepEqual(panel._filteredTableRows("overview", rows).map((row) => row.id), [
    "battery:sensor.pending",
  ]);
  assert.equal(panel._filterCount("overview"), 2);
  panel._resetTableFilters("overview");
  assert.equal(panel._filterCount("overview"), 0);
  assert.equal(panel._filteredTableRows("overview", rows).length, 3);
});

test("individual facet and date filters target their exact fields", () => {
  const panel = tablePanel();
  const rows = panel._tableRows("overview");
  const cases = [
    ["device", "Sonde rack", ["rule:temperature:sensor.rack"]],
    ["area", "Garage", ["battery:sensor.pending"]],
    ["rule", "Température baie", ["rule:temperature:sensor.rack"]],
    ["integration", "mqtt", ["battery:sensor.pending", "rule:temperature:sensor.rack"]],
    ["labels", "critical", ["rule:temperature:sensor.rack"]],
    ["domain", "sensor", ["battery:sensor.pending", "rule:temperature:sensor.rack", "unavailable:sensor.acknowledged"]],
    ["entity", "sensor.acknowledged", ["unavailable:sensor.acknowledged"]],
  ];
  for (const [key, value, expected] of cases) {
    Object.keys(panel._tableState.overview.filters).forEach((filter) => {
      panel._tableState.overview.filters[filter] = ["detectedFrom", "detectedTo", "resolvedFrom", "resolvedTo"].includes(filter) ? "" : [];
    });
    panel._tableState.overview.filters[key] = [value];
    const matches = panel._filteredTableRows("overview", rows).map((row) => row.id);
    assert.deepEqual(matches.sort(), expected.sort());
  }
  panel._resetTableFilters("overview");
  panel._tableState.overview.filters.detectedFrom = "2026-08-26T08:00:00.000Z";
  panel._tableState.overview.filters.detectedTo = "2026-08-26T23:00:00.000Z";
  assert.equal(panel._filterCount("overview"), 1);
  assert.equal(panel._filteredTableRows("overview", rows).length, 3);
});

test("date range filtering preserves the selected start and end times", () => {
  const panel = tablePanel();
  assert.equal(panel._dateMatches(
    "2026-08-27T10:30:00.000Z",
    "2026-08-27T10:00:00.000Z",
    "2026-08-27T11:00:00.000Z",
  ), true);
  assert.equal(panel._dateMatches(
    "2026-08-27T11:30:00.000Z",
    "2026-08-27T10:00:00.000Z",
    "2026-08-27T11:00:00.000Z",
  ), false);
});

test("native grouping works for device, area, rule and status and remembers collapsed groups", () => {
  const panel = tablePanel();
  panel._resetTableFilters("overview");
  const rows = panel._filteredTableRows("overview", panel._tableRows("overview"));
  const data = panel._nativeTableData("overview", rows);
  assert.ok(new Set(data.map((row) => row.device_group)).size >= 2);
  assert.ok(new Set(data.map((row) => row.area_group)).size >= 2);
  assert.ok(new Set(data.map((row) => row.rule_group)).size >= 2);
  assert.ok(new Set(data.map((row) => row.status_group)).size >= 2);
  assert.equal(panel._nativeGroupColumn("device"), "device_group");
  assert.equal(panel._tableStateGroupColumn("status_group"), "status");
  panel._tableState.overview.groupBy = "device";
  const listeners = {};
  const table = {
    addEventListener(name, callback) { listeners[name] = callback; },
    querySelectorAll() { return []; },
    dataset: {},
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );
  panel._hydrateDataTables();
  const group = table.data[0].device_group;
  listeners["collapsed-changed"]({ detail: { value: [group] } });
  assert.equal(panel._collapsedTableGroups.has(`overview:${group}`), true);
  listeners["grouping-changed"]({ detail: { value: "area_group" } });
  assert.equal(panel._tableState.overview.groupBy, "area");
});

test("sorting handles dates, numeric values and text in both directions", () => {
  const panel = tablePanel();
  panel._resetTableFilters("overview");
  const rows = panel._tableRows("overview");
  assert.deepEqual(
    panel._filteredTableRows("overview", rows).map((row) => row.status),
    ["active", "pending", "acknowledged"],
  );
  panel._tableState.overview.sortBy = "value";
  panel._tableState.overview.sortDirection = "asc";
  assert.equal(panel._filteredTableRows("overview", rows)[0].rawValue, 10);
  panel._tableState.overview.sortDirection = "desc";
  assert.equal(panel._filteredTableRows("overview", rows)[0].rawValue, "unavailable");
  panel._tableState.overview.sortBy = "detected";
  assert.equal(panel._filteredTableRows("overview", rows)[0].entityId, "sensor.pending");
  panel._tableState.overview.sortBy = "entityName";
  panel._tableState.overview.sortDirection = "asc";
  assert.deepEqual(panel._filteredTableRows("overview", rows).map((row) => row.entityName), [
    "Batterie UPS", "NAS", "Température rack",
  ]);
});

test("column visibility, order and table preferences persist locally", () => {
  const panel = tablePanel();
  panel._tableState.overview.columns = ["status", "entity", "area", "value"];
  panel._tableState.overview.groupBy = "device";
  panel._tableState.overview.sortBy = "value";
  panel._tableState.overview.sortDirection = "asc";
  panel._saveTablePreferences();

  const Panel = customElements.get("alert-manager-panel");
  const restored = new Panel();
  assert.deepEqual(restored._tableState.overview.columns, ["status", "entity", "area", "value"]);
  assert.equal(restored._tableState.overview.groupBy, "device");
  assert.equal(restored._tableState.overview.sortBy, "value");
  assert.equal(restored._tableState.overview.sortDirection, "asc");

  const invalid = makeTableState("overview", { columns: ["value"] });
  assert.ok(invalid.columns.includes("status"));
  assert.ok(invalid.columns.includes("entity"));
  const migrated = makeTableState("overview", {
    columns: ["status", "device", "entity", "value", "condition", "detected", "timeline"],
  });
  assert.deepEqual(migrated.columns, [
    "status", "entity", "device", "rule", "integration", "timeline",
  ]);
  const migratedDev7 = makeTableState("overview", {
    columns: ["status", "entity", "device", "value", "condition", "detected", "timeline"],
  });
  assert.deepEqual(migratedDev7.columns, migrated.columns);
  const migratedPreviousSort = makeTableState("overview", {
    sortBy: "detected",
    sortDirection: "desc",
  });
  assert.equal(migratedPreviousSort.sortBy, "status");
  assert.equal(migratedPreviousSort.sortDirection, "asc");
});

test("malformed table preferences fall back without breaking panel startup", () => {
  assert.deepEqual(
    makeTableState("overview", null).columns,
    ["status", "entity", "device", "rule", "integration", "timeline"],
  );
  assert.deepEqual(
    makeTableState("history", "invalid").columns,
    ["status", "entity", "device", "rule", "integration", "detected"],
  );
});

test("native settings dialog events hide, reorder and restore optional columns", () => {
  const panel = tablePanel();
  const listeners = {};
  const historyListeners = {};
  const table = {
    addEventListener(name, callback) { listeners[name] = callback; },
    querySelectorAll() { return []; },
    dataset: {},
  };
  const historyTable = {
    addEventListener(name, callback) { historyListeners[name] = callback; },
    querySelectorAll() { return []; },
    dataset: {},
  };
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === '[data-alert-table-page="overview"]') return table;
    if (selector === '[data-alert-table-page="history"]') return historyTable;
    return null;
  };
  panel._hydrateDataTables();
  const order = ["status", "entity", "value", "area", "device", "condition", "detected", "timeline"];
  listeners["columns-changed"]({ detail: { columnOrder: order, hiddenColumns: ["device"] } });
  assert.equal(panel._tableState.overview.columns.includes("device"), false);
  assert.deepEqual(panel._tableState.overview.columns.slice(0, 4), ["status", "entity", "value", "area"]);
  listeners["columns-changed"]({ detail: { columnOrder: undefined, hiddenColumns: undefined } });
  assert.deepEqual(panel._tableState.overview.columns, [
    "status", "entity", "device", "rule", "integration", "timeline",
  ]);
  panel._tableState.history.columns = ["status", "entity", "resolved"];
  historyListeners["columns-changed"]({ detail: { columnOrder: undefined, hiddenColumns: undefined } });
  assert.deepEqual(panel._tableState.history.columns, [
    "status", "entity", "device", "rule", "integration", "detected",
  ]);
});

test("selection mode is delegated to the native subpage table toolbar", async () => {
  const panel = tablePanel();
  panel._selectionMode = true;
  panel._selectedAlertIds = new Set(["rule:temperature:sensor.rack"]);
  const listeners = {};
  let restoredSelection = [];
  const table = {
    addEventListener(name, callback) { listeners[name] = callback; },
    querySelectorAll() { return []; },
    dataset: {},
    updateComplete: Promise.resolve(),
    shadowRoot: {
      querySelector() {
        return { select(ids) { restoredSelection = ids; } };
      },
    },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );
  panel._hydrateDataTables();
  await new Promise((resolve) => setTimeout(resolve, 1));
  assert.equal(table.selectable, true);
  assert.match(panel._renderOverview(), /slot="selection-bar"/);
  assert.deepEqual(restoredSelection, ["rule:temperature:sensor.rack"]);
  listeners["selection-changed"]({ detail: { value: ["rule:temperature:sensor.rack"] } });
  assert.equal(panel._selectedAlertIds.has("rule:temperature:sensor.rack"), true);
  assert.equal(table.selected, 1);
});

test("selection mode selects visible rows and mixed bulk actions affect compatible alerts only", async () => {
  const panel = tablePanel();
  panel._selectionMode = true;
  panel._selectedAlertIds = new Set(panel._tableRows("overview").map((row) => row.id));
  const toolbar = panel._renderAlertTable(
    "overview",
    panel._tableRows("overview"),
  );
  assert.match(toolbar, /Acquitter \(1\)/);
  assert.match(toolbar, /Désacquitter \(1\)/);

  const calls = [];
  panel._hass.callService = async (...args) => { calls.push(args); };
  panel._render = () => {};
  await panel._bulkAlertAction("acknowledge");
  assert.deepEqual(calls, [[
    "alert_manager", "acknowledge", { alert_id: "rule:temperature:sensor.rack" },
  ]]);
  assert.equal(panel._alerts.active_count, 0);
  assert.equal(panel._alerts.acknowledge_count, 2);
  assert.match(panel._notice.text, /1 alerte/);

  await panel._bulkAlertAction("unacknowledge");
  assert.equal(calls.filter((call) => call[1] === "unacknowledge").length, 1);
  assert.equal(calls[1][2].alert_id, "unavailable:sensor.acknowledged");
  assert.equal(panel._selectedAlertIds.has("battery:sensor.pending"), true);
});

test("history uses the same table tools without selection or runtime actions", () => {
  const panel = tablePanel();
  panel._historyConfig = { retention_limit: 100, enabled: true };
  panel._history = {
    events: [historyEvent()],
  };
  const html = panel._renderHistory();
  assert.deepEqual(panel._tableState.history.columns, [
    "status", "entity", "device", "rule", "integration", "detected",
  ]);
  const rows = panel._nativeTableData("history", panel._tableRows("history", panel._history.events));
  assert.equal(rows[0].statusLabel, "Résolue après acquittement");
  assert.equal(rows[0].integration, "mqtt");
  assert.equal(rows[0].integrationLabel, "MQTT");
  assert.equal(rows[0].value, "34.5 °C");
  assert.match(html, /<hass-tabs-subpage-data-table[\s\S]*data-alert-table-page="history"/);
  assert.doesNotMatch(html, /selectable|slot="selection-bar"|bulk-acknowledge|bulk-unacknowledge|data-due=/);
  assert.doesNotMatch(html, /data-table-filter-option="status"/);
  assert.doesNotMatch(html, /data-table-filter-option="acknowledged"/);
  assert.doesNotMatch(html, /<button|<select|type="radio"|type="checkbox"/);
});

test("filter pane uses native Home Assistant filters with reset controls in headers", () => {
  const panel = tablePanel();
  panel._tableState.overview.filters.status = ["active"];
  panel._tableState.overview.filters.detectedFrom = "2026-08-26";
  const html = panel._renderOverview();
  assert.match(html, /data-table-filter-option="status"/);
  assert.match(html, /data-table-filter-option="device"/);
  assert.match(html, /data-table-filter-option="rule"/);
  assert.match(html, /data-table-filter-option="integration"/);
  assert.match(html, /data-table-filter-option="labels"/);
  assert.match(html, /data-table-filter-option="domain"/);
  assert.match(html, /data-table-filter-option="area"/);
  assert.doesNotMatch(html, /data-table-filter-option="acknowledged"/);
  assert.match(html, /filter-badge">1<\/span><ha-icon-button data-action="clear-filter-section"/);
  assert.match(html, /<ha-date-range-picker[\s\S]*data-table-date-range="detected"/);
  assert.match(html, /extended-presets[\s\S]*time-picker[\s\S]*backdrop/);
  assert.doesNotMatch(html, /data-table-date-filter|<ha-selector/);
  assert.doesNotMatch(html, /<ha-input type="date"/);
  assert.doesNotMatch(html, /native-filter-actions|data-action="reset-filters"|class="table-toolbar"/);
});

test("native facet filters support multiple values and global clearing", () => {
  const panel = tablePanel();
  panel._tableState.overview.filters.status = ["active"];
  panel._render = () => {};
  const pageListeners = {};
  const checkboxListeners = {};
  const checkbox = {
    dataset: {
      tableFilterOption: "status",
      filterValue: "pending",
    },
    checked: false,
    addEventListener(name, callback) { checkboxListeners[name] = callback; },
  };
  const table = {
    dataset: {},
    addEventListener(name, callback) { pageListeners[name] = callback; },
    querySelectorAll(selector) {
      return selector === "ha-checkbox[data-table-filter-option]" ? [checkbox] : [];
    },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );
  panel._hydrateDataTables();
  assert.equal(checkbox.checked, false);
  checkbox.checked = true;
  checkboxListeners.change({ stopPropagation() {} });
  assert.deepEqual(panel._tableState.overview.filters.status, ["active", "pending"]);
  pageListeners["clear-filter"]();
  assert.equal(panel._filterCount("overview"), 0);
});

test("date filters use the native Home Assistant date range picker", () => {
  const panel = tablePanel();
  panel._tableState.overview.filters.detectedFrom = "2026-08-26T08:00:00.000Z";
  panel._tableState.overview.filters.detectedTo = "2026-08-27T11:00:00.000Z";
  panel._render = () => {};
  const listeners = {};
  const datePicker = {
    dataset: {
      tableDateRange: "detected",
      tableRangeStart: "2026-08-26T08:00:00.000Z",
      tableRangeEnd: "2026-08-27T11:00:00.000Z",
    },
    isConnected: true,
    addEventListener(name, callback) { listeners[name] = callback; },
  };
  const table = {
    dataset: {},
    addEventListener() {},
    querySelectorAll(selector) {
      if (selector === "ha-date-range-picker[data-table-date-range]") return [datePicker];
      return [];
    },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );

  panel._hydrateDataTables();

  assert.equal(datePicker.startDate.toISOString(), "2026-08-26T08:00:00.000Z");
  assert.equal(datePicker.endDate.toISOString(), "2026-08-27T11:00:00.000Z");
  assert.equal(datePicker.extendedPresets, true);
  assert.equal(datePicker.timePicker, true);
  assert.equal(datePicker.backdrop, true);
  listeners["value-changed"]({ detail: { value: {
    startDate: new Date("2026-08-27T09:00:00.000Z"),
    endDate: new Date("2026-08-27T12:30:00.000Z"),
  } } });
  assert.equal(panel._tableState.overview.filters.detectedFrom, "2026-08-27T09:00:00.000Z");
  assert.equal(panel._tableState.overview.filters.detectedTo, "2026-08-27T12:30:00.000Z");
  listeners["value-changed"]({ detail: { value: {
    startDate: new Date("invalid"),
    endDate: new Date("2026-08-28T12:30:00.000Z"),
  } } });
  assert.equal(panel._tableState.overview.filters.detectedFrom, "2026-08-27T09:00:00.000Z");
  assert.equal(panel._tableState.overview.filters.detectedTo, "2026-08-27T12:30:00.000Z");
});

test("native wrapper events update search grouping sorting and columns", () => {
  const panel = tablePanel();
  const listeners = {};
  const table = {
    addEventListener(name, callback) { listeners[name] = callback; },
    querySelectorAll() { return []; },
    dataset: {},
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? table : null
  );
  panel._hydrateDataTables();
  listeners["search-changed"]({ detail: { value: "garage" } });
  assert.equal(panel._tableState.overview.search, "garage");
  listeners["grouping-changed"]({ detail: { value: "device_group" } });
  assert.equal(panel._tableState.overview.groupBy, "device");
  listeners["sorting-changed"]({ detail: { column: "value", direction: "asc" } });
  assert.equal(panel._tableState.overview.sortBy, "value");
  assert.equal(panel._tableState.overview.sortDirection, "asc");
  let editorSwitches = 0;
  panel._switchRuleEditor = () => { editorSwitches += 1; };
  panel._handleSelected({
    detail: { item: { value: "switch-editor" } },
    target: {},
    composedPath: () => [{ dataset: { ruleEditorMenu: "" } }],
  });
  assert.equal(editorSwitches, 1);
});

test("native Home Assistant table uses full width and all visible columns in compact mobile rows", () => {
  const panel = tablePanel();
  panel._narrow = true;
  const styles = compactCss(panel._styles());
  const columns = panel._nativeTableColumns("overview");
  const active = panel._nativeTableData("overview", panel._tableRows("overview"))[0];
  const entity = panel._nativeEntityCell(active, true);
  assert.match(styles, /main\{width:100%;max-width:none;margin:0;padding:24px\}/);
  assert.match(styles, /hass-tabs-subpage-data-table\{display:block;width:100%;height:100%;--data-table-row-height:60px\}/);
  assert.match(styles, /--data-table-row-height:72px/);
  assert.equal(columns.status.title, "");
  assert.equal(columns.status.showNarrow, true);
  assert.equal(columns.entity.main, true);
  assert.equal(entity.children[0].textContent, active.entityName);
  assert.deepEqual(entity.children[1].children.map((child) => (
    typeof child === "string" ? child : child.textContent
  )), [
    active.device,
    " · ",
    active.rule,
    " · ",
    active.integrationLabel,
    " · ",
    panel._date(active.activated),
  ]);
  assert.equal(entity.children.length, 2);

  panel._tableState.overview.columns = [
    "status", "entity", "value", "area", "condition", "detected",
  ];
  const customized = panel._nativeEntityCell(active, true, "overview");
  assert.deepEqual(customized.children[1].children.map((child) => (
    typeof child === "string" ? child : child.textContent
  )), [
    active.value,
    " · ",
    active.area,
    " · ",
    active.condition,
    " · ",
    panel._date(active.detected),
  ]);
});

test("table navigation delegates tabs and controls to hass-tabs-subpage-data-table", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._loading = false;
  panel._hass = { states: {} };
  const shell = {};
  panel.shadowRoot.querySelector = (selector) => selector === "#panel-shell" ? shell : null;

  panel._render();

  assert.match(panel.shadowRoot.innerHTML, /<hass-tabs-subpage-data-table[\s\S]*id="panel-shell"[\s\S]*data-alert-table-page="overview"/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /ha-icon-button-arrow-prev/);
  assert.match(panel.shadowRoot.innerHTML, /<hass-tabs-subpage-data-table[\s\S]*main-page/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /back-path=/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /ha-tab-group|ha-tab-group-tab|<ha-tab/);
  assert.equal(shell.hass, panel._hass);
  assert.equal(shell.mainPage, true);
  assert.equal(shell.backPath, undefined);
  assert.equal(shell.backCallback, undefined);
  assert.deepEqual(shell.route, { prefix: "", path: "/alert-manager/overview" });
  assert.deepEqual(shell.tabs.map(({ path, name }) => ({ path, name })), [
    { path: "/alert-manager/overview", name: "Vue d’ensemble" },
    { path: "/alert-manager/history", name: "Historique" },
    { path: "/alert-manager/coherence", name: "Cohérence" },
    { path: "/alert-manager/rules", name: "Règles personnalisées" },
    { path: "/alert-manager/automatic", name: "Surveillance automatique" },
    { path: "/alert-manager/settings", name: "Configuration" },
  ]);
  assert.ok(shell.tabs.every((tab) => typeof tab.iconPath === "string" && tab.iconPath.startsWith("M")));
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /<h1>Alertes<|class="header-count"|Détection centralisée des anomalies/);
  assert.doesNotMatch(compactCss(panel._styles()), /paper-font|font-family:var\(--ha-font-family-body/);
  assert.doesNotMatch(compactCss(panel._styles()), /ha-top-app-bar-fixed|ha-tab-group|\.native-tabs|\.tab-label/);
});

test("all native panel pages use the Home Assistant menu without back navigation", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._loading = false;
  panel._hass = { states: {} };
  const shell = {};
  panel.shadowRoot.querySelector = (selector) => selector === "#panel-shell" ? shell : null;

  panel._render();
  assert.equal(shell.mainPage, true);
  assert.equal(shell.backPath, undefined);
  assert.equal(shell.backCallback, undefined);

  panel._activeTab = "settings";
  panel._render();
  assert.match(panel.shadowRoot.innerHTML, /<hass-tabs-subpage id="panel-shell" main-page>/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /back-path=/);
});

test("native panel routes select the matching tab", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._loading = false;
  panel._render = () => {};

  panel.route = { prefix: "/alert-manager", path: "/rules" };
  assert.equal(panel._activeTab, "rules");
  panel.route = { prefix: "", path: "/alert-manager/settings" };
  assert.equal(panel._activeTab, "settings");
  panel.route = { prefix: "", path: "/alert-manager" };
  assert.equal(panel._activeTab, "overview");
});

test("forms use native Home Assistant inputs, switches and buttons", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._config.coherence_ignored_entity_references = ["toto.plop"];
  panel._packs = completePacks();
  const automatic = panel._renderAutomatic();
  panel._ensureSettingsDraft();
  const settings = panel._renderSettings();
  const styles = compactCss(panel._styles());

  assert.match(automatic, /<ha-input[^>]+id="auto-unavailable-delay"/);
  assert.match(automatic, /<ha-switch id="auto-unavailable-enabled"/);
  assert.match(automatic, /<ha-button appearance="accent" variant="brand" data-action="save-automatic"/);
  assert.match(automatic, /<div class="category-header">[\s\S]*<h2>Entités indisponibles<\/h2>[\s\S]*<ha-switch id="auto-unavailable-enabled"[\s\S]*<\/div>\s*<p>Surveille l’état unavailable/);
  assert.doesNotMatch(automatic, /Délai actuel/);
  assert.match(automatic, /<form id="automatic-form" class="automatic-grid">/);
  const batteryDelay = automatic.indexOf('id="auto-battery-delay"');
  const batteryDelayHelp = automatic.indexOf(
    "Laisser le délai vide pour utiliser le délai global.",
    batteryDelay,
  );
  const batteryThreshold = automatic.indexOf('id="auto-battery-threshold"');
  assert.ok(batteryDelay < batteryDelayHelp);
  assert.ok(batteryDelayHelp < batteryThreshold);
  assert.doesNotMatch(automatic, /low_battery_level/);
  assert.match(settings, /<ha-input[^>]+id="global-delay"/);
  assert.match(settings, /<ha-select id="coherence-schedule"/);
  assert.match(settings, /<ha-switch id="coherence-scan-esphome"[^>]+checked/);
  assert.match(settings, /<form id="settings-form" class="stack settings-form"/);
  assert.match(settings, /<h2>Affichage des alertes<\/h2>/);
  assert.match(settings, /<h2>Analyse de cohérence<\/h2>/);
  assert.match(settings, /<h2>Exclusions de la surveillance<\/h2>/);
  assert.match(settings, /<h2>Historique<\/h2>/);
  assert.match(settings, /<ha-chip-set class="ignored-reference-chips">[\s\S]*<ha-input-chip[^>]+data-ignored-reference="toto\.plop"/);
  assert.match(settings, /<ha-input id="ignored-reference-input"[^>]+placeholder="Exemple : toto\.plop"/);
  assert.match(settings, /data-action="add-ignored-reference"/);
  assert.doesNotMatch(settings, /coherence-ignored-entity-references[^>]*><\/ha-selector>/);
  assert.match(settings, /Références ignorées par l’analyse de cohérence/);
  assert.match(settings, /class="history-settings-row">[\s\S]*id="history-limit"[\s\S]*data-action="clear-history"/);
  assert.doesNotMatch(settings, /<section class="panel history-settings"/);
  assert.doesNotMatch(settings, /data-action="save-history-settings"|<h3>Historique<\/h3>|Les alertes actives résolues sont conservées séparément/);
  assert.match(settings, /<ha-selector id="excluded-labels"/);
  assert.match(settings, /<div class="field settings-wide"><span class="field-label">Labels exclus des surveillances automatiques<\/span><ha-selector id="excluded-labels"/);
  assert.ok(settings.indexOf('id="excluded-labels"') < settings.indexOf('id="excluded-entities"'));
  assert.ok(settings.indexOf('id="excluded-entities"') < settings.indexOf('id="excluded-devices"'));
  assert.match(settings, /<ha-button appearance="accent" variant="brand" data-action="add-entity-delay"><ha-svg-icon slot="start"/);
  assert.match(settings, /class="actions settings-save-actions"><ha-button appearance="accent" variant="brand" data-action="save-settings"/);
  assert.ok(settings.indexOf('class="delay-list"') < settings.indexOf('data-action="add-entity-delay"'));
  assert.ok(settings.indexOf('id="global-delay"') < settings.indexOf('id="excluded-labels"'));
  assert.ok(settings.indexOf('id="global-delay"') < settings.indexOf("Ce délai est utilisé lorsqu’aucun délai particulier d’entité ou de pack n’est défini."));
  assert.ok(settings.indexOf("Ce délai est utilisé lorsqu’aucun délai particulier d’entité ou de pack n’est défini.") < settings.indexOf('id="excluded-labels"'));
  assert.ok(settings.indexOf('id="excluded-labels"') < settings.indexOf('class="history-settings"'));
  assert.ok(settings.indexOf('data-action="clear-history"') < settings.indexOf('class="actions settings-save-actions"'));
  assert.doesNotMatch(automatic + settings, /class="input-suffix"|class="switch"/);
  assert.match(styles, /ha-input\{--ha-input-padding-bottom:0\}/);
  assert.match(styles, /\.automatic-grid\{[^}]*grid-template-columns:repeat\(2/);
  assert.match(styles, /\.category-header\{[^}]*grid-template-columns:minmax\(0,1fr\) auto/);
  assert.match(styles, /\.category-header ha-switch\{align-self:start\}/);
  assert.match(styles, /\.switch-field-row\{[^}]*grid-template-columns:minmax\(0,1fr\) auto/);
  assert.match(styles, /\.settings-form\{[^}]*max-width:1120px[^}]*margin-inline:auto/);
  assert.match(styles, /\.settings-grid\{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)[^}]*max-width:920px/);
  assert.match(styles, /\.ignored-reference-chips\{[^}]*flex-wrap:wrap/);
  assert.match(styles, /\.ignored-reference-add\{display:flex;align-items:flex-start;gap:8px\}/);
  assert.match(styles, /\.ignored-reference-add ha-input\{flex:0 1 420px\}/);
  assert.match(styles, /\.delay-add-action\{justify-content:flex-start;margin-top:16px\}/);
  assert.match(styles, /\.history-settings-row\{[^}]*grid-template-areas:"label \." "input action"[^}]*align-items:center/);
  assert.match(styles, /\.history-actions\{grid-area:action;align-self:start;min-height:56px;align-items:center/);
  assert.match(styles, /\.settings-save-actions\{justify-content:flex-end;margin-top:4px\}/);
  assert.match(styles, /\.field-label\{[^}]*font-weight:var\(--ha-font-weight-normal/);
  assert.doesNotMatch(styles, /input:not\(\[type="checkbox"\]\)|\.input-suffix\{/);
});

test("rule edit, toggle and delete actions call their dedicated APIs", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const existing = {
    ...ruleValues({ id: "rule-id", duration: 900 }),
    version: 1,
  };
  panel._config = { ...completeConfig(), rules: [existing] };
  panel._editingRule = { ...existing };
  panel._render = () => {};
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      if (message.type === "alert_manager/rules/delete") return { deleted: true };
      return { ...existing, ...message.rule };
    },
  };

  await panel._saveRule(form(ruleValues({ id: "rule-id", name: "Modifiée" })));
  await panel._handleClick(actionEvent("toggle-rule", "rule-id"));
  panel._editingRule = { ...existing };
  await panel._handleClick(actionEvent("delete-rule", "rule-id"));

  assert.equal(calls[0].type, "alert_manager/rules/update");
  assert.equal(calls[0].rule_id, "rule-id");
  assert.equal(calls[0].rule.name, "Modifiée");
  assert.deepEqual(calls[1], {
    type: "alert_manager/rules/update",
    rule_id: "rule-id",
    rule: { enabled: false },
  });
  assert.deepEqual(calls[2], {
    type: "alert_manager/rules/delete",
    rule_id: "rule-id",
  });
  assert.deepEqual(panel._config.rules, []);
  assert.equal(panel._editingRule, null);
});

test("table toggle updates an open editor for the same rule", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const existing = {
    ...ruleValues({ id: "rule-id", enabled: true, duration: 900 }),
    version: 2,
  };
  panel._config = { ...completeConfig(), rules: [existing] };
  panel._editingRule = { ...existing };
  panel._render = () => {};
  panel._hass = {
    callWS: async (message) => ({ ...existing, ...message.rule }),
  };

  await panel._handleClick(actionEvent("toggle-rule", "rule-id"));

  assert.equal(panel._config.rules[0].enabled, false);
  assert.equal(panel._editingRule.enabled, false);
});

test("saving the editor preserves the activation controlled by the table", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...ruleValues({ id: "disabled-rule", enabled: false }),
  };
  let savedRule;
  panel._hass = {
    callWS: async (message) => {
      savedRule = message.rule;
      return { ...message.rule, id: "disabled-rule", version: 2 };
    },
  };
  panel._render = () => {};

  await panel._saveRule(form(ruleValues({ enabled: true })));

  assert.equal(savedRule.enabled, false);
});

test("rule rows and editor use native Home Assistant components", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = {
    ...completeConfig(),
    rules: [
      { ...ruleValues({ id: "enabled", enabled: true }), entity_ids: ["sensor.one"] },
      { ...ruleValues({ id: "disabled", enabled: false }), entity_ids: ["sensor.two"] },
    ],
  };

  const rules = panel._renderRules();
  const listeners = {};
  const table = {
    addEventListener(name, callback) { listeners[name] = callback; },
    querySelectorAll() { return []; },
  };
  panel._hass = { states: {} };
  panel.shadowRoot.querySelector = (selector) => selector === "[data-rules-table-page]" ? table : null;
  panel._hydrateRuleTable();
  panel._editingRule = { ...panel._config.rules[0] };
  const editor = panel._renderRuleEditor();
  panel._ensureSettingsDraft();
  panel._entityDelayDraft = [{ entity_id: "sensor.one", delay: 30 }];
  const settings = panel._renderSettings();

  assert.match(rules, /<hass-tabs-subpage-data-table[\s\S]*data-rules-table-page/);
  assert.doesNotMatch(rules, /<table|<thead|<tbody|<tr|<td|<th/);
  assert.deepEqual(table.columnOrder, ["name", "entities", "condition", "duration", "enabled"]);
  assert.deepEqual(table.data.map((row) => row.id), ["enabled", "disabled"]);
  assert.equal(table.columns.name.main, true);
  assert.equal(table.columns.name.sortable, true);
  assert.equal(table.columns.enabled.template(table.data[0]).checked, true);
  assert.equal(table.columns.enabled.template(table.data[1]).checked, false);
  assert.deepEqual(
    table.columns.entities.template(table.data[0]).children.map((child) => child.textContent),
    ["sensor.one"],
  );
  assert.doesNotMatch(rules, /data-action="delete-rule"/);
  assert.match(rules, /<ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start"/);
  assert.ok(rules.indexOf("</ha-data-table>") < rules.indexOf('data-action="new-rule"'));
  assert.match(editor, /<ha-card outlined class="rule-editor-drawer"[\s\S]*<ha-dialog-header show-border>[\s\S]*<ha-icon-button id="rule-editor-close"/);
  assert.match(editor, /<ha-dropdown slot="actionItems" data-rule-editor-menu/);
  assert.match(editor, /<ha-icon-button slot="trigger"/);
  assert.match(editor, /<ha-dropdown-item value="switch-editor">[\s\S]*Modifier en YAML/);
  assert.doesNotMatch(editor, /slot="subtitle"/);
  assert.match(editor, /class="rule-editor-resize" role="separator"/);
  assert.match(editor, /class="field full"[\s\S]*data-field="name"/);
  assert.match(editor, /class="field full rule-message-field"[\s\S]*<ha-selector id="rule-message-template"><\/ha-selector>/);
  assert.match(editor, /Condition Jinja supplémentaire/);
  assert.match(editor, /Toutes les fonctions Jinja et entités de Home Assistant sont accessibles/);
  assert.match(editor, /le message reste figé à l’activation/);
  assert.match(editor, /id="rule-update-message-when-active"/);
  assert.doesNotMatch(editor, /component\.alert_manager\.config_panel\.rules\.condition_template/);
  assert.match(editor, /class="field rule-attribute-field" hidden/);
  assert.doesNotMatch(editor, /rule-enabled|id="rule-enabled"|Activer la règle/);
  assert.match(editor, /<section class="rule-editor-section">[\s\S]*<h3>Condition<\/h3>/);
  assert.match(editor, /data-action="add-rule-value"/);
  assert.match(editor, /<ha-dropdown-item value="delete-rule" variant="danger">[\s\S]*Supprimer<\/ha-dropdown-item>/);
  assert.match(editor, /<ha-button appearance="accent" variant="brand" data-action="save-rule"[^>]*>Enregistrer<\/ha-button>/);
  assert.doesNotMatch(editor, /<ha-button[^>]*data-action="cancel-rule"[^>]*>Annuler<\/ha-button>/);
  assert.doesNotMatch(editor, /<aside|<input/);
  assert.match(settings, /appearance="plain" variant="danger" data-action="remove-entity-delay"/);
  const styles = compactCss(panel._styles());
  assert.match(styles, /\.delay-row\{[^}]*align-items:start/);
  assert.match(styles, /\.delay-row>ha-button\{margin-top:8px\}/);
  assert.doesNotMatch(
    styles,
    /#rules-table\{[^}]*--data-table-row-height/,
  );
  assert.match(styles, /ha-card\.rule-editor-drawer\{position:fixed/);
  assert.doesNotMatch(styles, /main\.rules-page/);
  assert.match(styles, /main\{width:100%;max-width:none/);
  assert.match(styles, /\.rules-layout\.has-editor \[data-rules-table-page\]\{--alert-manager-rule-table-width:calc\(\s*100% - var\(--rule-editor-width\) - var\(--rule-editor-inline-end\) - var\(--rule-editor-content-gap\)\s*\)\}/);
  assert.match(styles, /ha-card\.rule-editor-drawer\{[^}]*inset-inline-end:var\(--rule-editor-inline-end\)/);
  assert.match(styles, /\.rule-editor-form\{[^}]*overflow:auto/);
  assert.match(styles, /\.rule-editor-resize\{[^}]*cursor:ew-resize/);
  let fullRenders = 0;
  let editorRefreshes = 0;
  panel._render = () => { fullRenders += 1; };
  panel._refreshRuleEditor = () => { editorRefreshes += 1; };
  listeners["row-click"]({ detail: { id: "enabled" } });
  assert.equal(editorRefreshes, 1);
  assert.equal(fullRenders, 0);
});

test("attribute input follows the selected rule source without rerendering", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = { ...ruleValues(), source: "state" };
  panel._hass = { states: {} };
  const source = {
    addEventListener(type, listener) { if (type === "selected") this.listener = listener; },
  };
  const operator = { addEventListener() {} };
  const entity = { addEventListener() {} };
  const attribute = { hidden: true };
  panel.shadowRoot.querySelector = (query) => ({
    "#rule-source": source,
    "#rule-operator": operator,
    "#rule-entity-ids": entity,
    ".rule-attribute-field": attribute,
  })[query] ?? null;

  panel._hydrateSelectors();
  source.listener({ detail: { value: "attribute" } });
  assert.equal(panel._editingRule.source, "attribute");
  assert.equal(attribute.hidden, false);
  source.listener({ detail: { value: "state" } });
  assert.equal(attribute.hidden, true);
});

test("rule editor width is adjustable and clamped", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  window.innerWidth = 1200;

  panel._setRuleEditorWidth(100);
  assert.equal(panel._ruleEditorWidth, 360);
  panel._setRuleEditorWidth(2000);
  assert.equal(panel._ruleEditorWidth, 800);
});

test("overview status summaries filter the table directly", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._alerts = {
    active_count: 2,
    acknowledge_count: 4,
    pending_count: 3,
    tracked_count: 47,
    alerts: [],
    pending: [],
    acknowledge: [],
  };

  const html = panel._renderOverview();
  assert.match(html, /Total suivi<\/span><strong>47<\/strong>/);
  assert.match(html, /Alertes à venir<\/span><strong class="pending">3<\/strong>/);
  assert.match(html, /Alertes acquittées<\/span><strong class="acknowledged">4<\/strong>/);
  assert.ok(html.indexOf("Alertes à venir") < html.indexOf("Alertes acquittées"));
  assert.match(html, /data-action="filter-summary-status" data-status="active"[^>]*aria-pressed="true"/);
  assert.match(html, /data-action="filter-summary-status" data-status="pending"/);
  panel._render = () => {};
  await panel._handleClick(actionEvent("filter-summary-status", undefined, { status: "pending" }));
  assert.deepEqual(panel._tableState.overview.filters.status, ["pending"]);
  panel._alerts.pending = [currentAlert({ id: "pending:test", entity_id: "sensor.pending" })];
  assert.deepEqual(panel._filteredTableRows("overview", panel._tableRows("overview")).map((row) => row.status), ["pending"]);
  const styles = compactCss(panel._styles());
  assert.match(styles, /\.acknowledged\{color:var\(--blue-color/);
  assert.match(styles, /\.summary\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(styles, /@media\(max-width:1000px\)\{\.summary\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});

test("rule editor navigation actions open, edit and cancel predictably", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const existing = {
    ...ruleValues({ id: "rule-id", duration: 900 }),
    version: 1,
  };
  panel._config = { ...completeConfig(), rules: [existing] };
  panel._render = () => {};

  await panel._handleClick({
    target: {
      closest: () => ({ dataset: { action: "tab", tab: "rules" } }),
    },
  });
  assert.equal(panel._activeTab, "rules");
  await panel._handleClick(actionEvent("new-rule"));
  assert.deepEqual(panel._editingRule, {});

  await panel._handleClick(actionEvent("edit-rule", "rule-id"));
  assert.deepEqual(panel._editingRule, existing);
  assert.notEqual(panel._editingRule, existing);

  await panel._handleClick(actionEvent("cancel-rule"));
  assert.equal(panel._editingRule, null);
});

test("automatic monitoring action serializes all category controls", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._render = () => {};
  const controls = {
    "#auto-unavailable-enabled": { checked: true },
    "#auto-unavailable-delay": { value: "60" },
    "#auto-connectivity-enabled": { checked: false },
    "#auto-connectivity-delay": { value: "120" },
    "#auto-unifi-enabled": { checked: true },
    "#auto-unifi-delay": { value: "180" },
    "#auto-battery-enabled": { checked: true },
    "#auto-battery-delay": { value: "240" },
    "#auto-battery-threshold": { value: "12" },
  };
  panel.shadowRoot.querySelector = (selector) => controls[selector];
  let call;
  panel._hass = { callWS: async (message) => { call = message; return panel._config; } };

  await panel._saveAutomatic();

  assert.deepEqual(call.config.automatic, {
    unavailable: { enabled: true, delay: 60 },
    connectivity: { enabled: false, delay: 120 },
    unifi: { enabled: true, delay: 180 },
    battery: { enabled: true, delay: 240, threshold: 12, device_thresholds: {} },
  });
});

test("automatic packs are rendered only from available backend metadata", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks().map((pack) => (
    pack.id === "unifi" ? { ...pack, available: false } : pack
  ));

  const html = panel._renderAutomatic();

  assert.match(html, /auto-unavailable-enabled/);
  assert.match(html, /auto-connectivity-enabled/);
  assert.match(html, /auto-battery-enabled/);
  assert.doesNotMatch(html, /auto-unifi-enabled|Équipements UniFi/);
  assert.doesNotMatch(html, /CATEGORIES|État unavailable sur toutes les entités/);
});

test("an empty pack delay serializes as the global fallback", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks().filter((pack) => pack.id === "unavailable");
  panel._render = () => {};
  const controls = {
    "#auto-unavailable-enabled": { checked: true },
    "#auto-unavailable-delay": { value: "" },
  };
  panel.shadowRoot.querySelector = (selector) => controls[selector];
  let call;
  panel._hass = { callWS: async (message) => { call = message; return panel._config; } };

  await panel._saveAutomatic();

  assert.deepEqual(call.config.automatic, {
    unavailable: { enabled: true, delay: null },
  });
});

test("submit keeps the form identity across an asynchronous rerender", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  let target = { id: "automatic-form" };
  let automaticSaves = 0;
  let settingsSaves = 0;
  panel._saveAutomatic = async () => {
    automaticSaves += 1;
    target = null;
  };
  panel._saveSettings = async () => {
    settingsSaves += 1;
  };

  await panel._handleSubmit({
    preventDefault() {},
    get target() { return target; },
  });

  assert.equal(automaticSaves, 1);
  assert.equal(settingsSaves, 0);
});

test("keyboard form submission respects native Home Assistant validation", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  let saves = 0;
  panel._saveAutomatic = async () => { saves += 1; };
  const invalidForm = {
    id: "automatic-form",
    reportValidity: () => false,
    querySelectorAll: () => [],
  };

  await panel._handleSubmit({ preventDefault() {}, target: invalidForm });

  assert.equal(saves, 0);
});

test("settings action serializes exclusions and entity delays", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._render = () => {};
  panel._settingsDraft = {
    coherence_scan_esphome: false,
    coherence_ignored_entity_references: ["toto.plop"],
    excluded_labels: ["sans_alerte"],
    excluded_entities: ["sensor.skip", "light.skip"],
    excluded_devices: ["a".repeat(32), "b".repeat(32)],
  };
  panel._entityDelayDraft = [
    { entity_id: "sensor.one", delay: 30 },
    { entity_id: "light.two", delay: 60 },
  ];
  const controls = {
    "#global-delay": { value: "300" },
    "#pending-display-delay": { value: "15" },
    "#coherence-schedule": { value: "weekly" },
    "#coherence-scan-esphome": { checked: false },
    "#ignored-reference-input": { value: " Another.Ref " },
    "#history-limit": { value: "250" },
  };
  panel.shadowRoot.querySelector = (selector) => controls[selector];
  panel.shadowRoot.querySelectorAll = () => [];
  const calls = [];
  panel._refreshHistory = async () => panel._history;
  panel._hass = { callWS: async (message) => {
    calls.push(message);
    if (message.type === "alert_manager/history/config/update") {
      return { retention_limit: 250, enabled: true };
    }
    return panel._config;
  } };

  await panel._saveSettings();

  assert.deepEqual(calls, [{
    type: "alert_manager/config/update",
    config: {
      global_delay: 300,
      pending_display_delay: 15,
      coherence_schedule: "weekly",
      coherence_scan_esphome: false,
      coherence_ignored_entity_references: ["toto.plop", "another.ref"],
      excluded_labels: ["sans_alerte"],
      excluded_entities: ["sensor.skip", "light.skip"],
      excluded_devices: ["a".repeat(32), "b".repeat(32)],
      entity_delays: { "sensor.one": 30, "light.two": 60 },
    },
  }, {
    type: "alert_manager/history/config/update",
    retention_limit: 250,
  }]);
  assert.deepEqual(panel._historyConfig, { retention_limit: 250, enabled: true });
});

test("native Home Assistant selectors are configured for multiple values", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "settings";
  panel._hass = { states: {} };
  const selectors = Object.fromEntries(
    [
      "#excluded-labels",
      "#excluded-entities",
      "#excluded-devices",
    ].map((id) => [
      id,
      { addEventListener() {} },
    ]),
  );
  selectors["#coherence-schedule"] = { addEventListener() {} };
  panel.shadowRoot.querySelector = (selector) => selectors[selector] ?? null;

  panel._hydrateSelectors();

  assert.deepEqual(selectors["#excluded-labels"].selector, { label: { multiple: true } });
  assert.equal(selectors["#coherence-schedule"].value, "none");
  assert.deepEqual(
    selectors["#coherence-schedule"].options.map((option) => option.value),
    ["none", "daily", "weekly", "monthly"],
  );
  assert.deepEqual(selectors["#excluded-entities"].selector, {
    entity: {
      multiple: true,
      exclude_entities: [
        "button.alert_manager_check_coherence",
        "sensor.alert_manager_coherence_issue",
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "sensor.alert_manager_device_main_active",
        "switch.alert_manager_main_monitoring",
      ],
    },
  });
  assert.deepEqual(selectors["#excluded-devices"].selector, { device: { multiple: true } });
});

test("ESPHome scan switch keeps its draft value before saving", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();

  panel._handleChange({ target: { id: "coherence-scan-esphome", checked: false } });

  assert.equal(panel._settingsDraft.coherence_scan_esphome, false);
  const settings = panel._renderSettings();
  assert.match(settings, /id="coherence-scan-esphome"/);
  assert.doesNotMatch(settings, /id="coherence-scan-esphome"[^>]+checked/);
});

test("ignored coherence references use compact chips with safe add and remove behavior", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._ensureSettingsDraft();
  let renders = 0;
  const input = {
    value: " Toto.Plop ",
  };
  panel.shadowRoot.querySelector = (selector) =>
    selector === "#ignored-reference-input" ? input : null;
  panel._render = () => { renders += 1; };

  await panel._handleClick(actionEvent("add-ignored-reference"));
  assert.deepEqual(panel._settingsDraft.coherence_ignored_entity_references, ["toto.plop"]);
  assert.equal(input.value, "");
  assert.equal(renders, 1);

  input.value = "toto.plop";
  await panel._handleClick(actionEvent("add-ignored-reference"));
  assert.deepEqual(panel._settingsDraft.coherence_ignored_entity_references, ["toto.plop"]);

  input.value = "not a reference";
  assert.equal(panel._commitIgnoredReferenceInput(), false);
  assert.equal(panel._notice.kind, "error");
  assert.equal(panel._ignoredReferenceDraft, "not a reference");

  panel._removeIgnoredReference("toto.plop");
  assert.deepEqual(panel._settingsDraft.coherence_ignored_entity_references, []);
});

test("native ignored-reference chip removal updates the settings draft", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = {
    ...completeConfig(),
    coherence_ignored_entity_references: ["toto.plop"],
  };
  panel._activeTab = "settings";
  panel._hass = { states: {} };
  panel._ensureSettingsDraft();
  const chip = {
    dataset: { ignoredReference: "toto.plop" },
    addEventListener(name, callback) {
      if (name === "remove") this.removeListener = callback;
    },
  };
  panel.shadowRoot.querySelector = () => null;
  panel.shadowRoot.querySelectorAll = (selector) =>
    selector === "ha-input-chip[data-ignored-reference]" ? [chip] : [];
  panel._render = () => {};

  panel._hydrateSelectors();
  assert.equal(chip.label, "toto.plop");
  assert.equal(chip.selected, true);
  let stopped = false;
  chip.removeListener({ stopPropagation() { stopped = true; } });

  assert.equal(stopped, true);
  assert.deepEqual(panel._settingsDraft.coherence_ignored_entity_references, []);
});

test("entity delay selector refuses a duplicate entity", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._entityDelayDraft = [
    { entity_id: "sensor.one", delay: 30 },
    { entity_id: "", delay: 60 },
  ];
  panel._render = () => {};

  panel._setEntityDelayEntity(1, "sensor.one");

  assert.equal(panel._entityDelayDraft[1].entity_id, "");
  assert.equal(panel._notice.kind, "error");
  assert.match(panel._notice.text, /possède déjà un délai/);
});

test("custom rule sources use the native multiple entity selector", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "rules";
  panel._editingRule = { entity_ids: ["sensor.one", "sensor.two"] };
  panel._hass = { states: {} };
  const selector = { addEventListener() {} };
  panel.shadowRoot.querySelector = (query) =>
    query === "#rule-entity-ids" ? selector : null;

  panel._hydrateSelectors();

  assert.deepEqual(selector.selector, {
    entity: {
      multiple: true,
      exclude_entities: [
        "button.alert_manager_check_coherence",
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "sensor.alert_manager_device_main_active",
        "switch.alert_manager_main_monitoring",
      ],
    },
  });
  assert.deepEqual(selector.value, ["sensor.one", "sensor.two"]);
});

test("custom rule entity selector keeps single and multiple selections", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "rules";
  panel._editingRule = { entity_ids: ["sensor.previous"] };
  panel._hass = { states: {} };
  const selector = {
    addEventListener(type, listener) {
      if (type === "value-changed") this.listener = listener;
    },
  };
  panel.shadowRoot.querySelector = (query) =>
    query === "#rule-entity-ids" ? selector : null;

  panel._hydrateSelectors();
  selector.listener({ detail: { value: "binary_sensor.filtration_piscine" } });

  assert.deepEqual(panel._editingRule.entity_ids, ["binary_sensor.filtration_piscine"]);
  assert.equal(panel._ruleDirty, true);

  selector.listener({
    detail: {
      value: ["binary_sensor.filtration_piscine", "sensor.temperature_piscine"],
    },
  });
  assert.deepEqual(panel._editingRule.entity_ids, [
    "binary_sensor.filtration_piscine",
    "sensor.temperature_piscine",
  ]);
});

test("custom rule entity selector reads the control value when event detail omits it", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "rules";
  panel._editingRule = { entity_ids: ["sensor.previous"] };
  panel._hass = { states: {} };
  const selector = {
    addEventListener(type, listener) {
      if (type === "value-changed") this.listener = listener;
    },
  };
  panel.shadowRoot.querySelector = (query) =>
    query === "#rule-entity-ids" ? selector : null;

  panel._hydrateSelectors();
  selector.value = "binary_sensor.filtration_piscine";
  selector.listener({ detail: {} });

  assert.deepEqual(panel._editingRule.entity_ids, ["binary_sensor.filtration_piscine"]);
});

test("configured selectors do not receive every Home Assistant state refresh", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "rules";
  panel._editingRule = { entity_ids: ["binary_sensor.filtration_piscine"] };
  panel._hass = { states: {} };
  let hassAssignments = 0;
  const selector = {
    set hass(value) {
      this._hass = value;
      hassAssignments += 1;
    },
    addEventListener() {},
  };
  panel.shadowRoot.querySelector = (query) =>
    query === "#rule-entity-ids" ? selector : null;

  panel._hydrateSelectors();
  panel._hass = { states: { "sensor.unrelated": { state: "changed" } } };
  panel._hydrateSelectors();

  assert.equal(hassAssignments, 1);
  assert.deepEqual(selector.value, ["binary_sensor.filtration_piscine"]);
});

test("condition and message use multiline Home Assistant template selectors", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "rules";
  panel._editingRule = {
    ...ruleValues(),
    condition_template: "{{ true }}",
    message: "Ligne 1\n{{ value }}",
  };
  panel._hass = { states: {} };
  const condition = {
    addEventListener(type, listener) {
      if (type === "value-changed") this.listener = listener;
    },
  };
  const message = {
    addEventListener(type, listener) {
      if (type === "value-changed") this.listener = listener;
    },
  };
  panel.shadowRoot.querySelector = (query) => ({
    "#rule-condition-template": condition,
    "#rule-message-template": message,
  })[query] ?? null;

  panel._hydrateSelectors();

  assert.deepEqual(condition.selector, { template: {} });
  assert.equal(condition.value, "{{ true }}");
  assert.deepEqual(message.selector, { template: {} });
  assert.equal(message.value, "Ligne 1\n{{ value }}");

  message.listener({ detail: { value: "Nouvelle ligne 1\nNouvelle ligne 2" } });
  assert.equal(panel._editingRule.message, "Nouvelle ligne 1\nNouvelle ligne 2");
  assert.equal(panel._ruleDirty, true);
});

test("custom rule choices use native Home Assistant selects", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "rules";
  panel._editingRule = {
    entity_ids: ["sensor.one"],
    source: "attribute",
    operator: "above",
  };
  panel._hass = { states: {} };
  const source = { addEventListener() {} };
  const operator = { addEventListener() {} };
  const entity = { addEventListener() {} };
  panel.shadowRoot.querySelector = (query) => ({
    "#rule-source": source,
    "#rule-operator": operator,
    "#rule-entity-ids": entity,
  })[query] ?? null;

  panel._hydrateSelectors();

  assert.equal(source.value, "attribute");
  assert.deepEqual(source.options, [
    { value: "state", label: "État principal" },
    { value: "attribute", label: "Attribut" },
    { value: "state_variation", label: "Variation de l’état principal" },
    { value: "attribute_variation", label: "Variation d’un attribut" },
    { value: "unchanged", label: "Aucun changement" },
    { value: "jinja", label: "Jinja" },
  ]);
  assert.equal(operator.value, "above");
  assert.deepEqual(operator.options.map((option) => option.value), [
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "above",
    "below",
    "between",
    "outside",
    "unchanged",
  ]);
});

test("range operators render two numeric bounds and save both values", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    entity_ids: ["sensor.temperature"],
    operator: "between",
    value: ["10", "20"],
  };

  const editor = panel._renderRuleEditor();
  assert.match(editor, /data-field="lower-bound"[^>]*type="number"[^>]*value="10"/);
  assert.match(editor, /data-field="upper-bound"[^>]*type="number"[^>]*value="20"/);
  assert.doesNotMatch(editor, /data-rule-value-index/);

  const values = {
    name: "Temperature range",
    source: "state",
    operator: "between",
    "lower-bound": "10",
    "upper-bound": "20",
    duration: "60",
  };
  const ruleForm = {
    querySelector(selector) {
      const name = selector.match(/data-field="([^"]+)"/)?.[1];
      return name && name in values ? { value: values[name] } : null;
    },
    querySelectorAll() { return []; },
    elements: { namedItem() { return null; } },
  };
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "range-rule", version: 2 };
    },
  };
  panel._render = () => {};

  await panel._saveRule(ruleForm);

  assert.deepEqual(calls[0].rule.value, ["10", "20"]);
});

test("selected no-change operator hides comparison values and stays source-specific", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    entity_ids: ["sensor.pool"],
    source: "attribute",
    attribute: "data.*.key",
    operator: "unchanged",
    value: "",
  };

  const editor = panel._renderRuleEditor();
  assert.match(editor, /data\.\*\.key/);
  assert.doesNotMatch(editor, /data-rule-value-index|data-field="value"|data-field="lower-bound"/);
  assert.match(editor, /valeur ou de l’attribut sélectionné/);

  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "stable-rule", version: 2 };
    },
  };
  panel._render = () => {};
  await panel._saveRule(form(ruleValues({
    source: "attribute",
    attribute: "data.*.key",
    operator: "unchanged",
  })));

  assert.equal(calls[0].rule.source, "attribute");
  assert.equal(calls[0].rule.attribute, "data.*.key");
  assert.equal(calls[0].rule.operator, "unchanged");
  assert.equal(calls[0].rule.value, "");
});

test("Jinja-only rule editor hides comparison fields and requires its template", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    entity_ids: ["sensor.one"],
    source: "jinja",
    condition_template: "{{ value == 'ready' }}",
    update_message_when_active: true,
  };

  const editor = panel._renderRuleEditor();
  assert.doesNotMatch(editor, /id="rule-operator"/);
  assert.doesNotMatch(editor, /data-rule-value-index|data-field="value"/);
  assert.match(editor, /<span class="field-label">Condition Jinja<\/span><ha-selector id="rule-condition-template" required aria-required="true">/);
  assert.match(editor, /aucune autre comparaison n’est évaluée/);
  assert.match(editor, /id="rule-update-message-when-active"[^>]+checked/);

  const calls = [];
  panel._hass = { callWS: async (message) => { calls.push(message); return message.rule; } };
  panel._render = () => {};
  panel._editingRule.condition_template = "";
  await panel._saveRule(form(ruleValues({ source: "jinja" })));
  assert.equal(calls.length, 0);
  assert.equal(panel._notice, null);
  assert.equal(
    panel._ruleEditorError,
    "La condition Jinja est obligatoire lorsque la source est « Jinja ».",
  );
});

test("normal comparison rules still save without a Jinja condition", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = { entity_ids: ["sensor.one"], condition_template: "" };
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "normal-rule", version: 2 };
    },
  };
  panel._render = () => {};

  await panel._saveRule(form(ruleValues({ entity_ids: ["sensor.one"] })));

  assert.equal(calls.length, 1);
  assert.equal(calls[0].rule.source, "state");
  assert.equal(calls[0].rule.condition_template, null);
});

test("attribute variation requires its attribute and starting Jinja condition", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    entity_ids: ["sensor.one"],
    source: "attribute_variation",
    attribute: "metrics.power",
    operator: "above",
    value: "5",
    condition_template: "",
  };

  const editor = panel._renderRuleEditor();
  assert.match(editor, /Condition Jinja de début/);
  assert.match(editor, /rule-condition-template" required aria-required="true"/);
  assert.match(editor, /capturée lorsque cette condition passe à true/);
  assert.match(editor, /<ha-selector id="rule-attribute" data-field="attribute"><\/ha-selector>/);
  assert.match(editor, /pas les jokers/);

  const calls = [];
  panel._hass = { callWS: async (message) => { calls.push(message); return message.rule; } };
  panel._render = () => {};
  await panel._saveRule(form(ruleValues({
    source: "attribute_variation",
    attribute: "metrics.power",
    operator: "above",
    value: "5",
  })));

  assert.equal(calls.length, 0);
  assert.equal(panel._notice, null);
  assert.equal(
    panel._ruleEditorError,
    "La condition Jinja de début est obligatoire avec une source de variation.",
  );

  panel._editingRule.condition_template = "{{ true }}";
  await panel._saveRule(form(ruleValues({
    source: "attribute_variation",
    attribute: "metrics.power",
    operator: "above",
    value: "5",
  })));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].rule.source, "attribute_variation");
  assert.equal(calls[0].rule.attribute, "metrics.power");
});

test("rule editor saves the opt-in active message update option", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    entity_ids: ["sensor.one"],
    message: "Live {{ value }}",
    update_message_when_active: true,
  };
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "live-message-rule", version: 2 };
    },
  };
  panel._render = () => {};

  await panel._saveRule(form(ruleValues({
    entity_ids: ["sensor.one"],
    update_message_when_active: true,
  })));

  assert.equal(calls.length, 1);
  assert.equal(calls[0].rule.update_message_when_active, true);
});

test("unchanged rule hides comparison fields and keeps Jinja optional", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    entity_ids: ["sensor.one"],
    source: "unchanged",
    condition_template: "",
  };

  const editor = panel._renderRuleEditor();
  assert.doesNotMatch(editor, /id="rule-operator"/);
  assert.doesNotMatch(editor, /data-rule-value-index|data-field="value"/);
  assert.match(editor, /Condition Jinja supplémentaire/);
  assert.match(editor, /absence de changement de l’état et des attributs/);
  assert.doesNotMatch(editor, /rule-condition-template" required/);

  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "unchanged-rule", version: 2 };
    },
  };
  panel._render = () => {};
  await panel._saveRule(form(ruleValues({ source: "unchanged" })));

  assert.equal(calls.length, 1);
  assert.equal(calls[0].rule.source, "unchanged");
  assert.equal(calls[0].rule.operator, "equals");
  assert.equal(calls[0].rule.value, "");
  assert.equal(calls[0].rule.condition_template, null);
});

test("rule editor renders multiple native value inputs with compact actions", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._editingRule = {
    ...ruleValues(),
    operator: "not_contains",
    value: ["ERROR", "WARN"],
  };

  const editor = panel._renderRuleEditor();

  assert.match(editor, /data-rule-value-index="0"[^>]*value="ERROR"/);
  assert.match(editor, /data-rule-value-index="1"[^>]*value="WARN"/);
  assert.equal((editor.match(/data-action="remove-rule-value"/g) ?? []).length, 2);
  assert.match(editor, /seulement lorsqu’aucune valeur ne correspond/);
});

test("native save buttons call their matching form action", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const formElement = {};
  panel.shadowRoot.querySelector = (selector) =>
    selector === "#automatic-form" ? formElement : null;
  panel._reportFormValidity = () => true;
  let saves = 0;
  panel._saveAutomatic = async () => { saves += 1; };

  await panel._handleClick(actionEvent("save-automatic"));

  assert.equal(saves, 1);
});

test("clicking an existing alert source opens native more info", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: { "sensor.test": { state: "on" } } };
  await panel._handleClick({
    target: {
      closest: () => ({
        dataset: { action: "more-info", entityId: "sensor.test" },
      }),
    },
  });
  assert.equal(panel.dispatchedEvent.type, "hass-more-info");
  assert.deepEqual(panel.dispatchedEvent.detail, { entityId: "sensor.test" });
  assert.equal(panel.dispatchedEvent.bubbles, true);
  assert.equal(panel.dispatchedEvent.composed, true);
});

test("panel renders French and English from backend translation resources", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._alerts = {
    active_count: 1,
    pending_count: 0,
    tracked_count: 1,
    alerts: [],
    pending: [],
  };

  panel._language = "fr";
  panel._translations = TRANSLATIONS.fr;
  assert.match(panel._renderOverview(), /Alertes actives/);
  assert.equal(panel._t("overview.status_pending"), "À venir");
  assert.match(panel._renderAutomatic(), /Entités indisponibles/);

  panel._language = "en";
  panel._translations = TRANSLATIONS.en;
  assert.match(panel._renderOverview(), /Active alerts/);
  assert.equal(panel._t("overview.status_pending"), "Upcoming");
  assert.match(panel._renderAutomatic(), /Unavailable entities/);
  assert.deepEqual(panel._tabs().map((tab) => tab.name), [
    "Overview",
    "History",
    "Coherence",
    "Custom rules",
    "Automatic monitoring",
    "Configuration",
  ]);
});

const historyEvent = (changes = {}) => ({
  event_id: "event-1",
  id: "rule:stable:sensor.rack_temperature",
  type: "rule",
  rule_id: "stable",
  rule_name: "Température baie élevée",
  entity_id: "sensor.rack_temperature",
  entity_name: "Température baie",
  device_id: "device-1",
  device_name: "Sonde baie",
  area: "Bureau",
  integration: "mqtt",
  message: "Refroidir la baie",
  trigger_value: 34.5,
  source: "state",
  operator: "above",
  comparison_value: 33,
  attribute: null,
  condition: "État supérieur à 33 °C",
  condition_key: "rule.generated",
  condition_params: {
    source: "state", operator: "above", expected: "33", unit: "°C", duration: 0,
  },
  unit: "°C",
  detected_at: "2026-08-26T12:00:00+00:00",
  active_at: "2026-08-26T12:00:00+00:00",
  resolved_at: "2026-08-26T12:01:15+00:00",
  pending_duration_seconds: 0,
  active_duration_seconds: 75,
  total_duration_seconds: 75,
  final_status: "resolved",
  acknowledged: true,
  acknowledged_at: "2026-08-26T12:00:30+00:00",
  acknowledged_by: "Loïc",
  ...changes,
});

test("history empty and disabled states are explicit and translated", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._history = { events: [], count: 0, retention_limit: 100, enabled: true };
  panel._historyConfig = { retention_limit: 100, enabled: true };
  assert.match(panel._renderHistory(), /data-alert-table-page="history"/);
  const table = { addEventListener() {}, querySelectorAll() { return []; }, dataset: {} };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="history"]' ? table : null
  );
  panel._hydrateDataTables();
  assert.equal(table.noDataText, "Aucune alerte dans l’historique.");
  panel._historyConfig = { retention_limit: 0, enabled: false };
  const disabled = panel._renderHistory();
  assert.match(disabled, /L’historique est désactivé/);
  assert.match(disabled, /open-history-settings/);
});

test("clearing history requires confirmation and sends the explicit marker", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._history = { events: [historyEvent()], count: 1, retention_limit: 100, enabled: true };
  panel._render = () => {};
  const calls = [];
  panel._call = async (message) => {
    calls.push(message);
    return { events: [], count: 0, retention_limit: 100, enabled: true };
  };
  const previousConfirm = window.confirm;
  window.confirm = () => false;
  await panel._handleClick(actionEvent("clear-history"));
  assert.deepEqual(calls, []);
  window.confirm = (message) => {
    assert.match(message, /irréversible/);
    return true;
  };
  try {
    await panel._handleClick(actionEvent("clear-history"));
  } finally {
    window.confirm = previousConfirm;
  }
  assert.deepEqual(calls, [{ type: "alert_manager/history/clear", confirmed: true }]);
  assert.deepEqual(panel._history.events, []);
});

test("common settings save accepts a zero history retention limit", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._history = { events: [], count: 0, retention_limit: 100, enabled: true };
  panel._historyConfig = { retention_limit: 100, enabled: true };
  panel._settingsDraft = {
    coherence_scan_esphome: true,
    coherence_ignored_entity_references: [],
    excluded_labels: [],
    excluded_entities: [],
    excluded_devices: [],
  };
  panel._entityDelayDraft = [];
  panel._render = () => {};
  const controls = {
    "#global-delay": { value: "900" },
    "#pending-display-delay": { value: "10" },
    "#coherence-schedule": { value: "none" },
    "#coherence-scan-esphome": { checked: true },
    "#history-limit": { value: "0", reportValidity: () => true },
  };
  panel.shadowRoot.querySelector = (selector) => controls[selector];
  panel.shadowRoot.querySelectorAll = () => [];
  const requests = [];
  panel._hass = { callWS: async (message) => {
    requests.push(message);
    return message.type === "alert_manager/history/config/update"
      ? { retention_limit: 0, enabled: false }
      : panel._config;
  } };
  panel._refreshHistory = async () => panel._history;
  await panel._saveSettings();
  assert.deepEqual(requests[1], {
    type: "alert_manager/history/config/update",
    retention_limit: 0,
  });
  assert.deepEqual(panel._historyConfig, { retention_limit: 0, enabled: false });
});

test("a runtime sensor update refreshes the open history tab immediately", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "history";
  panel._render = () => {};
  let refreshes = 0;
  panel._refreshHistory = () => { refreshes += 1; };
  panel.hass = {
    locale: { language: "fr" },
    states: {
      "sensor.alert_manager_main_active": { state: "0", attributes: { alerts: [] } },
      "sensor.alert_manager_main_pending": { state: "0", attributes: { alerts: [] } },
      "sensor.alert_manager_main_acknowledge": { state: "0", attributes: { alerts: [] } },
      "switch.alert_manager_main_monitoring": { state: "on", attributes: {} },
    },
  };
  assert.equal(refreshes, 1);
});

test("missing localized keys fall back to English backend resources", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._translations = {};
  panel._englishTranslations = TRANSLATIONS.en;
  assert.equal(panel._t("overview.summary_tracked"), "Total monitored");
});

test("changing the Home Assistant locale reloads backend translations", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._loading = false;
  panel._render = () => {};
  const calls = [];
  panel.hass = {
    locale: { language: "en" },
    states: {},
    callWS: async (message) => {
      calls.push(message);
      return { resources: TRANSLATIONS[message.language] };
    },
  };
  await panel._translationPromise;

  assert.equal(panel._language, "en");
  assert.equal(panel._t("tabs.overview"), "Overview");
  assert.deepEqual(calls, [{
    type: "frontend/get_translations",
    language: "en",
    category: "config_panel",
    integration: "alert_manager",
  }]);
});

test("a locale change is not lost while translations are loading", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._loading = false;
  panel._render = () => {};
  const calls = [];
  let releaseFirstRequests;
  const firstRequests = new Promise((resolve) => { releaseFirstRequests = resolve; });
  panel._hass = {
    callWS: async (message) => {
      calls.push(message.language);
      if (calls.length <= 2) await firstRequests;
      return { resources: TRANSLATIONS[message.language] };
    },
  };
  panel._language = "fr";
  const firstReload = panel._reloadTranslations();
  panel._language = "en";
  releaseFirstRequests();
  await firstReload;
  while (panel._translationPromise) await panel._translationPromise;

  assert.deepEqual(calls, ["fr", "en", "en"]);
  assert.equal(panel._t("tabs.overview"), "Overview");
});

test("structured automatic and generated rule conditions are localized", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._language = "en";
  panel._translations = TRANSLATIONS.en;

  assert.equal(panel._conditionText({
    condition: "Batterie inférieure ou égale à 15 %",
    condition_key: "automatic.battery",
    condition_params: { threshold: "15" },
  }), "Battery less than or equal to 15%");
  assert.equal(panel._conditionText({
    condition: "État supérieur à 9 pendant 900 s",
    condition_key: "rule.generated",
    condition_params: {
      source: "state",
      attribute: null,
      operator: "above",
      expected: "9",
      unit: "°C",
      duration: 900,
    },
  }), "State greater than 9 °C for 15 min");
  assert.equal(panel._conditionText({
    condition: "État et attributs inchangés pendant 900 s",
    condition_key: "rule.unchanged",
    condition_params: { duration: 900 },
  }), "State and attributes unchanged for 15 min");
  assert.equal(panel._conditionText({ condition: "User text" }), "User text");

  const table = tablePanel();
  table._language = "en";
  table._translations = TRANSLATIONS.en;
  const automatic = table._tableRows("overview").find((row) => row.source.type === "battery");
  assert.equal(automatic.condition, "Battery less than or equal to 15%");
  assert.equal(automatic.message, "Battery less than or equal to 15%");
});


test("new rule preserves Jinja condition from selector draft when selector value is unavailable", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    ...ruleValues(),
    condition_template: "{{ states('sensor.example') == 'on' }}",
  };
  const ruleForm = form(ruleValues());
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "#rule-condition-template") return { value: undefined };
    if (selector === "#rule-message-template") return { value: "" };
    return null;
  };
  panel._render = () => {};
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "created-rule" };
    },
  };

  await panel._saveRule(ruleForm);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].type, "alert_manager/rules/create");
  assert.equal(
    calls[0].rule.condition_template,
    "{{ states('sensor.example') == 'on' }}",
  );
});


test("controlled selectors mirror emitted values back to their host", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = {};
  const selector = {
    value: "",
    addEventListener(type, listener) {
      if (type === "value-changed") this.listener = listener;
    },
  };
  panel.shadowRoot.querySelector = (query) => query === "#template-test" ? selector : null;
  let changed;

  panel._configureSelector(
    "template-test",
    { template: {} },
    "",
    (value) => { changed = value; },
  );
  selector.listener({ detail: { value: "{{ true }}" } });

  assert.equal(selector.value, "{{ true }}");
  assert.equal(changed, "{{ true }}");
});

test("new rule saves message and condition drafts when selector hosts still expose empty initial values", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._editingRule = {
    ...newRuleDefaults(),
    ...ruleValues(),
    message: "Alerte {{ states('sensor.example') }}",
    condition_template: "{{ is_state('binary_sensor.example', 'on') }}",
  };
  const ruleForm = form(ruleValues());
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "#rule-message-template") return { value: "" };
    if (selector === "#rule-condition-template") return { value: "" };
    return null;
  };
  panel._render = () => {};
  const calls = [];
  panel._hass = {
    callWS: async (message) => {
      calls.push(message);
      return { ...message.rule, id: "created-rule", version: 2 };
    },
  };

  await panel._saveRule(ruleForm);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].rule.message, "Alerte {{ states('sensor.example') }}");
  assert.equal(
    calls[0].rule.condition_template,
    "{{ is_state('binary_sensor.example', 'on') }}",
  );
});

test("rule editor keeps only save in the footer", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();

  panel._editingRule = {};
  const createHtml = panel._renderRuleEditor();
  const createFooter = createHtml.match(/<div class="actions rule-editor-actions">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(createFooter, /data-action="save-rule"/);
  assert.doesNotMatch(createFooter, /data-action="cancel-rule"/);
  assert.doesNotMatch(createFooter, /data-action="delete-rule"/);
  assert.doesNotMatch(createHtml, /<ha-dropdown-item value="delete-rule">/);

  panel._editingRule = { ...newRuleDefaults(), id: "rule-1", name: "Test" };
  const editHtml = panel._renderRuleEditor();
  const editFooter = editHtml.match(/<div class="actions rule-editor-actions">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(editFooter, /data-action="save-rule"/);
  assert.doesNotMatch(editFooter, /data-action="cancel-rule"/);
  assert.doesNotMatch(editFooter, /data-action="delete-rule"/);
  assert.match(editHtml, /<ha-dropdown-item value="delete-rule" variant="danger">[\s\S]*Supprimer<\/ha-dropdown-item>/);
});

test("rule editor delete menu uses the existing delete flow", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = { rules: [{ id: "rule-1", name: "Test", enabled: true }] };
  panel._editingRule = { id: "rule-1", name: "Modified draft" };
  panel._render = () => {};
  const calls = [];
  panel._call = async (message) => {
    calls.push(message);
    return {};
  };

  await panel._handleSelected({
    composedPath: () => [{ dataset: { ruleEditorMenu: "" } }],
    detail: { value: "delete-rule" },
  });

  assert.deepEqual(calls, [{ type: "alert_manager/rules/delete", rule_id: "rule-1" }]);
  assert.deepEqual(panel._config.rules, []);
  assert.equal(panel._editingRule, null);
});
