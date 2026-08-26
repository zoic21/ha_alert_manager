import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

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

const { buildOverviewItems, lines, newRuleDefaults } = await import(
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
  automatic: {
    unavailable: { enabled: true, delay: 900 },
    connectivity: { enabled: true, delay: 900 },
    unifi: { enabled: true, delay: 900 },
    battery: { enabled: true, delay: 900, threshold: 15 },
  },
  rules: [],
  global_delay: 900,
  excluded_labels: [],
  excluded_entities: [],
  excluded_devices: [],
  entity_delays: {},
});

test("partitioned entities update their matching overview lists", () => {
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
  assert.deepEqual(panel._alerts.alerts, [{ id: "active" }]);
  assert.deepEqual(panel._alerts.pending.map((alert) => alert.id), ["pending-1", "pending-2"]);
  assert.deepEqual(panel._alerts.acknowledge, [{ id: "acknowledged" }]);
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
  assert.match(panel.shadowRoot.innerHTML, /<div class="monitoring-warning"/);
  assert.match(panel.shadowRoot.innerHTML, /La surveillance Alert Manager est désactivée/);

  await panel._handleClick(actionEvent("enable-monitoring"));
  assert.deepEqual(calls, [[
    "switch",
    "turn_on",
    { entity_id: "switch.alert_manager_main_monitoring" },
  ]]);
  assert.equal(panel._monitoringEnabled, true);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /<div class="monitoring-warning"/);
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
  },
];

const form = (values) => ({
  elements: {
    namedItem(name) {
      if (!(name in values)) return null;
      return name === "enabled"
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
  ...changes,
});

const actionEvent = (action, id) => ({
  target: {
    closest() {
      return { dataset: { action, ...(id ? { id } : {}) } };
    },
  },
});

test("initial load requests pack metadata from the backend", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._render = () => {};
  const calls = [];
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
    "frontend/get_translations",
    "frontend/get_translations",
  ]);
  assert.deepEqual(panel._packs, completePacks());
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
  panel.shadowRoot.querySelector = (selector) =>
    selector === "#rule-form" ? ruleForm : null;
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
        message: null,
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

  assert.equal(panel._notice.kind, "error");
  assert.equal(panel._notice.text, "Une erreur inattendue s’est produite.");
  assert.deepEqual(panel._editingRule.entity_ids, ["todo.liste_d_achats"]);
  assert.deepEqual(panel._editingRule.value, ["0"]);
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

test("active alerts are red while pending alerts stay orange", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: { "sensor.test": { state: "on" } } };
  const alert = {
    entity_id: "sensor.test",
    name: "Test",
    value: "unavailable",
    condition: "État indisponible",
  };

  assert.match(panel._renderAlert(alert, true), /<ha-card outlined class="alert-card is-active"/);
  assert.match(panel._renderAlert(alert, false), /<ha-card outlined class="alert-card is-pending"/);
  assert.doesNotMatch(panel._renderAlert(alert, true), /severity|warning|critical/);
  assert.match(panel._styles(), /\.alert-card\.is-active,\.device-alert-group\.is-active\{--alert-state-color:var\(--error-color/);
  assert.match(panel._renderAlert(alert, true), /class="alert-status-icon alert-state-action/);
  assert.match(panel._renderAlert(alert, true), /class="alert-current-value">unavailable<\/strong>/);
  assert.doesNotMatch(panel._renderAlert(alert, true), />Active<|>En attente<|class="alert-value"/);
});

test("alert conditions stay on one line in the wider detail column", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: { "todo.list": { state: "0" } } };

  const html = panel._renderAlert({
    entity_id: "todo.list",
    name: "Liste d’achats",
    condition: "État inférieur à 1 pendant 600 s",
  }, true);
  const styles = panel._styles();

  assert.match(html, /class="alert-condition"/);
  assert.match(styles, /\.alert-details\{[^}]*grid-template-columns:minmax\(0,\.85fr\) minmax\(0,1\.15fr\)/);
  assert.match(styles, /\.alert-condition dd\{[^}]*white-space:nowrap/);
});

test("overview cards hide entity IDs and keep grouped details vertically aligned", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = {
    states: {
      "zone.home": { state: "0" },
      "sensor.cloudflare": { state: "0.11" },
    },
  };

  const standalone = panel._renderAlert({
    entity_id: "zone.home",
    name: "Maison",
    condition: "État contient 0 pendant 1 min",
  }, "active");
  const grouped = panel._renderDeviceAlertRow({
    entity_id: "sensor.cloudflare",
    name: "Cloudflared Pourcentage du processeur",
    condition: "État inférieur à 123 % pendant 30 s",
  }, "active");
  const styles = panel._styles();

  assert.doesNotMatch(standalone, /<code>zone\.home<\/code>/);
  assert.match(standalone, /data-entity-id="zone\.home"/);
  assert.doesNotMatch(grouped, /<code>sensor\.cloudflare<\/code>/);
  assert.match(grouped, /État inférieur à 123 % pendant 30 s/);
  assert.match(styles, /\.device-alert-condition,\.device-alert-time\{[^}]*grid-column:2\/-1[^}]*display:block/);
  assert.match(styles, /\.device-alert-condition small,\.device-alert-time small\{[^}]*margin-top:0/);
  assert.match(styles, /\.device-alert-condition span,\.device-alert-time span\{[^}]*text-overflow:ellipsis[^}]*white-space:nowrap/);
  assert.match(grouped, /<span title="État inférieur à 123 % pendant 30 s">État inférieur à 123 % pendant 30 s<\/span>/);
});

test("alert overview uses native Home Assistant cards without nested panels", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const alert = { entity_id: "sensor.test", name: "Test", condition: "Test" };

  panel._alerts = {
    active_count: 1,
    acknowledge_count: 0,
    pending_count: 0,
    tracked_count: 1,
    alerts: [alert],
    pending: [],
    acknowledge: [],
  };
  const populated = panel._renderOverviewAlerts(buildOverviewItems([alert], []));
  panel._alerts.active_count = 0;
  panel._alerts.alerts = [];
  const empty = panel._renderOverviewAlerts([]);

  assert.match(populated, /<section class="alert-group alert-group-active">/);
  assert.match(populated, /<section class="alert-group alert-group-pending">/);
  assert.match(populated, /<section class="alert-group alert-group-acknowledged">/);
  assert.match(populated, /<ha-card outlined class="alert-card is-active"/);
  assert.doesNotMatch(populated, /<section class="panel">/);
  assert.match(empty, /<ha-card outlined class="alert-empty">/);
});

test("overview renders active, upcoming and acknowledged alerts in separate vertical sections", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  panel._alerts = {
    active_count: 2,
    acknowledge_count: 1,
    pending_count: 1,
    alerts: [{ entity_id: "zone.home", name: "Maison", condition: "Vide" }],
    pending: [{ entity_id: "media_player.tv", name: "TV", condition: "Indisponible" }],
    acknowledge: [{
      id: "unavailable:sensor.nas",
      entity_id: "sensor.nas",
      name: "NAS",
      condition: "Indisponible",
      acknowledged: true,
      acknowledged_at: "2026-08-25T14:30:00Z",
    }],
  };

  const html = panel._renderOverviewAlerts(
    buildOverviewItems(
      panel._alerts.alerts,
      panel._alerts.pending,
      panel._alerts.acknowledge,
    ),
  );

  assert.match(html, /class="alert-list alert-list-active"[\s\S]*is-active/);
  assert.match(html, /class="alert-list alert-list-pending"[\s\S]*is-pending/);
  assert.match(html, /class="alert-list alert-list-acknowledged"[\s\S]*is-acknowledged/);
  assert.match(html, /<h2>Alertes actives<\/h2>/);
  assert.match(html, /<h2>Alertes à venir<\/h2>/);
  assert.match(html, /<h2>Alertes acquittées<\/h2>/);
  assert.ok(html.indexOf("alert-group-active") < html.indexOf("alert-group-pending"));
  assert.ok(html.indexOf("alert-group-pending") < html.indexOf("alert-group-acknowledged"));
  assert.match(panel._styles(), /\.alert-group\+\.alert-group\{margin-top:28px\}/);
});

test("active and pending alerts from one device stay in separate sections", () => {
  const active = {
    id: "unavailable:sensor.ups_status",
    entity_id: "sensor.ups_status",
    name: "État UPS",
    device_id: "a".repeat(32),
    device_name: "Onduleur",
    area: "Bureau",
    value: "unavailable",
    condition: "État indisponible",
    active_since: "2026-08-25T12:00:00Z",
  };
  const pending = {
    id: "battery:sensor.ups_battery",
    entity_id: "sensor.ups_battery",
    name: "Batterie UPS",
    device_id: "a".repeat(32),
    device_name: "Onduleur",
    area: "Bureau",
    value: 10,
    unit: "%",
    condition: "Batterie faible",
    due_at: "2026-08-25T12:15:00Z",
  };
  const items = buildOverviewItems([active], [pending]);
  assert.equal(items.length, 2);
  assert.deepEqual(items.map((item) => item.kind), ["alert", "alert"]);
  assert.deepEqual(items.map((item) => item.status), ["active", "pending"]);

  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = {
    states: {
      "sensor.ups_status": { state: "unavailable" },
      "sensor.ups_battery": { state: "10" },
    },
  };
  panel._alerts = { active_count: 1, pending_count: 1 };
  const overview = panel._renderOverviewAlerts(items);
  assert.match(overview, /alert-group-active[\s\S]*sensor\.ups_status/);
  assert.match(overview, /alert-group-pending[\s\S]*sensor\.ups_battery/);
  assert.ok(overview.indexOf("sensor.ups_status") < overview.indexOf("sensor.ups_battery"));
  assert.match(overview, /alert-card is-active/);
  assert.match(overview, /alert-card is-pending/);
  assert.match(overview, /data-due=/);
  assert.equal((overview.match(/data-action="more-info"/g) ?? []).length, 2);
});

test("multiple alerts from one device still form a group within one section", () => {
  const deviceId = "a".repeat(32);
  const first = { entity_id: "sensor.ups_status", device_id: deviceId };
  const second = { entity_id: "sensor.ups_load", device_id: deviceId };
  const items = buildOverviewItems([first, second], []);

  assert.equal(items.length, 1);
  assert.equal(items[0].kind, "device");
  assert.deepEqual(items[0].alerts.map((item) => item.status), ["active", "active"]);
});

test("grouped alerts show the first alert and reveal the others on demand", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const deviceId = "a".repeat(32);
  const group = {
    device_id: deviceId,
    alerts: [
      { status: "active", alert: { entity_id: "sensor.first", name: "First alert" } },
      { status: "active", alert: { entity_id: "sensor.second", name: "Second alert" } },
      { status: "active", alert: { entity_id: "sensor.third", name: "Third alert" } },
    ],
  };

  const collapsed = panel._renderDeviceGroup(group);
  assert.match(collapsed, /First alert/);
  assert.doesNotMatch(collapsed, /Second alert/);
  assert.doesNotMatch(collapsed, /Third alert/);
  assert.match(collapsed, /data-action="toggle-device-alerts"/);
  assert.match(collapsed, /<button type="button" class="device-alert-toggle"/);
  assert.match(collapsed, /aria-expanded="false"/);
  assert.match(panel._styles(), /\.device-alert-toggle\{[^}]*border:0[^}]*background:transparent[^}]*font-size:var\(--ha-font-size-s,12px\)/);
  assert.match(panel._styles(), /\.device-alert-toggle:hover\{[^}]*border:0[^}]*background:transparent/);
  assert.match(panel._styles(), /\.device-alert-toggle:focus-visible\{[^}]*outline:/);

  panel._render = () => {};
  await panel._handleClick({
    target: {
      closest: () => ({
        dataset: {
          action: "toggle-device-alerts",
          deviceGroup: `is-active:${deviceId}`,
          alertCount: "3",
        },
      }),
    },
  });

  const partiallyExpanded = panel._renderDeviceGroup(group);
  assert.match(partiallyExpanded, /Second alert/);
  assert.doesNotMatch(partiallyExpanded, /Third alert/);
  assert.match(partiallyExpanded, /aria-expanded="false"/);

  await panel._handleClick({
    target: {
      closest: () => ({
        dataset: {
          action: "toggle-device-alerts",
          deviceGroup: `is-active:${deviceId}`,
          alertCount: "3",
        },
      }),
    },
  });
  const expanded = panel._renderDeviceGroup(group);
  assert.match(expanded, /Third alert/);
  assert.match(expanded, /aria-expanded="true"/);
});

test("acknowledged alerts stay compact and expose the real unacknowledge action", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: { "sensor.test": { state: "unavailable" } } };
  const alert = {
    id: "unavailable:sensor.test",
    entity_id: "sensor.test",
    name: "Test",
    value: "unavailable",
    condition: "État indisponible",
    active_since: "2026-08-25T14:00:00Z",
    acknowledged: true,
    acknowledged_at: "2026-08-25T14:30:00Z",
    acknowledged_by: "Loïc",
  };
  const html = panel._renderAlert(alert, "acknowledged");

  assert.match(html, /Acquittée/);
  assert.match(html, /Loïc/);
  assert.doesNotMatch(html, /Identifiant de l’alerte/);
  assert.doesNotMatch(html, /data-action="copy-alert-id"/);
  assert.doesNotMatch(html, /class="alert-controls/);
  assert.match(html, /data-action="unacknowledge-alert"/);
  assert.match(html, /aria-label="Retirer l’acquittement/);
  assert.doesNotMatch(html, /data-action="acknowledge-alert"/);
  assert.match(html, /class="alert-status-icon alert-state-action/);
  assert.doesNotMatch(html, /class="alert-header-actions"/);
  assert.match(panel._styles(), /\.alert-card\.is-acknowledged[^}]*--alert-state-color:var\(--blue-color/);
  assert.match(panel._styles(), /data-action="unacknowledge-alert"[^}]*--alert-hover-color:color-mix\(in srgb,var\(--error-color/);

  const calls = [];
  panel._hass.callService = async (...args) => { calls.push(args); };
  panel._render = () => {};
  await panel._handleClick({
    target: {
      closest: () => ({
        dataset: { action: "unacknowledge-alert", alertId: alert.id },
      }),
    },
  });
  assert.deepEqual(calls, [[
    "alert_manager",
    "unacknowledge",
    { alert_id: "unavailable:sensor.test" },
  ]]);
});

test("the left status icon becomes the acknowledgement action without growing the card", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const html = panel._renderAlert({
    id: "unavailable:sensor.test",
    entity_id: "sensor.test",
    condition: "État indisponible",
    active_since: "2026-08-25T14:00:00Z",
  }, "active");

  assert.match(html, /class="alert-status-icon alert-state-action[^>]*data-action="acknowledge-alert"/);
  assert.doesNotMatch(html, /class="alert-header-actions"/);
  assert.doesNotMatch(html, /alert-controls|copy-alert-id|Identifiant de l’alerte/);
  assert.match(panel._styles(), /\.alert-card-header\{[^}]*grid-template-columns:40px minmax\(0,1fr\) auto/);
  assert.match(panel._styles(), /data-action="acknowledge-alert"[^}]*--alert-hover-color:var\(--dark-primary-color/);
});

test("status action icons swap on hover and return on blur", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  const listeners = {};
  const button = {
    dataset: { action: "acknowledge-alert" },
    addEventListener(type, callback) { listeners[type] = callback; },
  };
  panel.shadowRoot.querySelectorAll = () => [button];

  panel._hydrateSelectors();
  const defaultPath = button.path;
  listeners.mouseenter();
  assert.notEqual(button.path, defaultPath);
  const hoverPath = button.path;
  listeners.mouseleave();
  assert.equal(button.path, defaultPath);
  listeners.focus();
  assert.equal(button.path, hoverPath);
  listeners.blur();
  assert.equal(button.path, defaultPath);
});

test("system acknowledgements use the translated fallback without an ID block", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: { "sensor.system": { state: "unavailable" } } };
  const alert = {
    id: "unavailable:sensor.system",
    entity_id: "sensor.system",
    acknowledged: true,
    acknowledged_at: "2026-08-25T14:30:00Z",
  };
  const html = panel._renderAlert(alert, "acknowledged");
  assert.match(html, /Automatisation ou système/);
  assert.doesNotMatch(html, /copy-alert-id|Identifiant de l’alerte/);
});

test("grouped alerts retain one compact acknowledgement action per row", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const deviceId = "a".repeat(32);
  const group = {
    kind: "device",
    device_id: deviceId,
    alerts: [
      {
        status: "active",
        alert: {
          id: "unavailable:sensor.one",
          entity_id: "sensor.one",
          device_id: deviceId,
          acknowledged: false,
        },
      },
      {
        status: "acknowledged",
        alert: {
          id: "battery:sensor.two",
          entity_id: "sensor.two",
          device_id: deviceId,
          acknowledged: true,
          acknowledged_at: "2026-08-25T14:30:00Z",
          acknowledged_by: "Loïc",
        },
      },
    ],
  };
  panel._expandedDeviceGroups.set(`is-active:${deviceId}`, group.alerts.length);
  const html = panel._renderDeviceGroup(group);

  assert.equal((html.match(/class="alert-status-icon alert-state-action is-compact"/g) ?? []).length, 2);
  assert.equal((html.match(/data-action="copy-alert-id"/g) ?? []).length, 0);
  assert.equal((html.match(/data-action="acknowledge-alert"/g) ?? []).length, 1);
  assert.equal((html.match(/data-action="unacknowledge-alert"/g) ?? []).length, 1);
  assert.doesNotMatch(html, /acknowledge-device|acknowledge-group/);
});

test("pending alerts have neither alert ID controls nor acknowledgement actions", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const html = panel._renderAlert({
    id: "battery:sensor.pending",
    entity_id: "sensor.pending",
    due_at: "2026-08-25T15:00:00Z",
  }, false);

  assert.doesNotMatch(html, /Identifiant de l’alerte|copy-alert-id/);
  assert.doesNotMatch(html, /data-action="(?:un)?acknowledge-alert"/);
});

test("single alerts and entities without a device stay compact and individual", () => {
  const deviceAlert = { entity_id: "sensor.one", device_id: "a".repeat(32) };
  const standalone = { entity_id: "sensor.two" };
  const items = buildOverviewItems([deviceAlert, standalone], []);

  assert.deepEqual(items.map((item) => item.kind), ["alert", "alert"]);
  assert.equal(items[0].alert, deviceAlert);
  assert.equal(items[1].alert, standalone);
});

test("navigation delegates the toolbar and tabs to hass-tabs-subpage", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._loading = false;
  panel._hass = { states: {} };
  const shell = {};
  panel.shadowRoot.querySelector = (selector) => selector === "#panel-shell" ? shell : null;

  panel._render();

  assert.match(panel.shadowRoot.innerHTML, /<hass-tabs-subpage id="panel-shell" back-path="\/config\/integrations">/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /ha-icon-button-arrow-prev/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /ha-tab-group|ha-tab-group-tab|<ha-tab/);
  assert.equal(shell.hass, panel._hass);
  assert.equal(shell.backPath, "/config/integrations");
  assert.deepEqual(shell.route, { prefix: "", path: "/alert-manager/overview" });
  assert.deepEqual(shell.tabs.map(({ path, name }) => ({ path, name })), [
    { path: "/alert-manager/overview", name: "Vue d’ensemble" },
    { path: "/alert-manager/automatic", name: "Surveillance automatique" },
    { path: "/alert-manager/rules", name: "Règles personnalisées" },
    { path: "/alert-manager/settings", name: "Configuration" },
  ]);
  assert.ok(shell.tabs.every((tab) => typeof tab.iconPath === "string" && tab.iconPath.startsWith("M")));
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /<h1>Alertes<|class="header-count"|Détection centralisée des anomalies/);
  assert.match(panel._styles(), /font-family:var\(--ha-font-family-body/);
  assert.doesNotMatch(panel._styles(), /ha-top-app-bar-fixed|ha-tab-group|\.native-tabs|\.tab-label/);
});

test("native toolbar back callback returns to the previous Home Assistant page", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._packs = completePacks();
  panel._loading = false;
  panel._hass = { states: {} };
  const shell = {};
  panel.shadowRoot.querySelector = (selector) => selector === "#panel-shell" ? shell : null;
  let backCalls = 0;
  window.history = {
    state: { from: "/lovelace/home" },
    back() { backCalls += 1; },
  };

  panel._render();
  shell.backCallback();

  assert.equal(backCalls, 1);
  assert.equal(shell.backPath, "/config/integrations");
  window.history = undefined;
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
  panel._packs = completePacks();
  const automatic = panel._renderAutomatic();
  panel._ensureSettingsDraft();
  const settings = panel._renderSettings();
  const styles = panel._styles();

  assert.match(automatic, /<ha-input[^>]+id="auto-unavailable-delay"/);
  assert.match(automatic, /<ha-switch id="auto-unavailable-enabled"/);
  assert.match(automatic, /<ha-button appearance="accent" variant="brand" data-action="save-automatic"/);
  assert.match(automatic, /<div class="category-header">[\s\S]*<h2>Entités indisponibles<\/h2>[\s\S]*<ha-switch id="auto-unavailable-enabled"[\s\S]*<\/div>\s*<p>Surveille l’état unavailable/);
  assert.doesNotMatch(automatic, /Délai actuel/);
  assert.match(automatic, /<form id="automatic-form" class="automatic-grid">/);
  assert.match(settings, /<ha-input[^>]+id="global-delay"/);
  assert.match(settings, /<ha-selector id="excluded-labels"/);
  assert.match(settings, /<ha-button appearance="accent" variant="brand" data-action="add-entity-delay"><ha-svg-icon slot="start"/);
  assert.match(settings, /<ha-button appearance="accent" variant="brand" data-action="save-settings"/);
  assert.ok(settings.indexOf('class="delay-list"') < settings.indexOf('data-action="add-entity-delay"'));
  assert.doesNotMatch(automatic + settings, /class="input-suffix"|class="switch"/);
  assert.match(styles, /ha-input\{--ha-input-padding-bottom:0\}/);
  assert.match(styles, /\.automatic-grid\{[^}]*grid-template-columns:repeat\(2/);
  assert.match(styles, /\.category-header\{[^}]*grid-template-columns:minmax\(0,1fr\) auto/);
  assert.match(styles, /\.category-header ha-switch\{align-self:start\}/);
  assert.match(styles, /\.delay-add-action\{justify-content:flex-start;margin-top:16px\}/);
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
  panel._editingRule = { ...panel._config.rules[0] };
  const editor = panel._renderRuleEditor();
  panel._ensureSettingsDraft();
  panel._entityDelayDraft = [{ entity_id: "sensor.one", delay: 30 }];
  const settings = panel._renderSettings();

  assert.match(rules, /<tr class="rule-row [^"]*" data-action="edit-rule" data-id="enabled"/);
  assert.match(rules, /<ha-switch haptic data-action="toggle-rule" data-id="enabled"[^>]* checked/);
  assert.match(rules, /<ha-switch haptic data-action="toggle-rule" data-id="disabled"(?![^>]* checked)/);
  assert.doesNotMatch(rules, /<ha-button[^>]+data-action="edit-rule"/);
  assert.doesNotMatch(rules, /data-action="delete-rule"/);
  assert.match(rules, /<ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start"/);
  assert.ok(rules.indexOf("</table>") < rules.indexOf('data-action="new-rule"'));
  assert.match(editor, /<ha-card outlined class="rule-editor-drawer"[\s\S]*<ha-dialog-header show-border>[\s\S]*<ha-icon-button id="rule-editor-close"/);
  assert.match(editor, /slot="actionItems" class="rule-menu-wrap"/);
  assert.doesNotMatch(editor, /slot="subtitle"/);
  assert.match(editor, /class="rule-editor-resize" role="separator"/);
  assert.match(editor, /class="field full rule-name-field"[\s\S]*data-field="name"/);
  assert.match(editor, /class="field full rule-message-field"[\s\S]*data-field="message"/);
  assert.match(editor, /class="field rule-attribute-field" hidden/);
  assert.doesNotMatch(editor, /rule-enabled|id="rule-enabled"|Activer la règle/);
  assert.match(editor, /<section class="rule-editor-section">[\s\S]*<h3>Condition<\/h3>/);
  assert.match(editor, /data-action="add-rule-value"/);
  assert.match(editor, /<ha-button appearance="plain" variant="danger" data-action="delete-rule" data-id="enabled">Supprimer<\/ha-button>/);
  assert.match(editor, /<ha-button appearance="accent" variant="brand" data-action="save-rule"[^>]*>Enregistrer<\/ha-button>/);
  assert.match(editor, />Annuler<\/ha-button>/);
  assert.doesNotMatch(editor, /<aside|<input/);
  assert.match(settings, /appearance="plain" variant="danger" data-action="remove-entity-delay"/);
  assert.match(panel._styles(), /\.delay-row\{[^}]*align-items:start/);
  assert.match(panel._styles(), /\.delay-row>ha-button\{margin-top:8px\}/);
  assert.match(panel._styles(), /ha-card\.rule-editor-drawer\{position:fixed/);
  assert.doesNotMatch(panel._styles(), /main\.rules-page|main\{[^}]*max-width:none/);
  assert.match(panel._styles(), /\.rules-layout\.has-editor \.rules-list-panel\{margin-inline-end:calc\(var\(--rule-editor-width\) \+ 8px\)\}/);
  assert.match(panel._styles(), /inset-inline-end:max\(24px,calc\(\(85vw - 1400px\)\/2 \+ 24px\)\)/);
  assert.match(panel._styles(), /\.rule-editor-form\{[^}]*overflow:auto/);
  assert.match(panel._styles(), /\.rule-editor-resize\{[^}]*cursor:ew-resize/);
});

test("alert cards omit unavailable device and area metadata", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const base = { entity_id: "sensor.test", name: "Test", condition: "Test" };

  const withoutMetadata = panel._renderAlert(base, true);
  const withDevice = panel._renderAlert({ ...base, device_name: "Pompe" }, true);
  const withArea = panel._renderAlert({ ...base, area: "Garage" }, true);

  assert.doesNotMatch(withoutMetadata, /<dt>Équipement<|<dt>Pièce</);
  assert.match(withDevice, /<dt>Équipement<\/dt><dd>Pompe<\/dd>/);
  assert.doesNotMatch(withDevice, /<dt>Pièce</);
  assert.match(withArea, /<dt>Pièce<\/dt><dd>Garage<\/dd>/);
  assert.doesNotMatch(withArea, /<dt>Équipement</);
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

test("overview displays the backend tracked total", () => {
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
  assert.match(panel._styles(), /\.acknowledged\{color:var\(--blue-color/);
  assert.match(panel._styles(), /\.summary\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(panel._styles(), /@media\(max-width:700px\)\{\.summary\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
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
    "#battery-threshold": { value: "12" },
  };
  panel.shadowRoot.querySelector = (selector) => controls[selector];
  let call;
  panel._hass = { callWS: async (message) => { call = message; return panel._config; } };

  await panel._saveAutomatic();

  assert.deepEqual(call.config.automatic, {
    unavailable: { enabled: true, delay: 60 },
    connectivity: { enabled: false, delay: 120 },
    unifi: { enabled: true, delay: 180 },
    battery: { enabled: true, delay: 240, threshold: 12 },
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

test("settings action serializes exclusions and entity delays", async () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._render = () => {};
  panel._settingsDraft = {
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
  };
  panel.shadowRoot.querySelector = (selector) => controls[selector];
  panel.shadowRoot.querySelectorAll = () => [];
  let call;
  panel._hass = { callWS: async (message) => { call = message; return panel._config; } };

  await panel._saveSettings();

  assert.deepEqual(call.config, {
    global_delay: 300,
    excluded_labels: ["sans_alerte"],
    excluded_entities: ["sensor.skip", "light.skip"],
    excluded_devices: ["a".repeat(32), "b".repeat(32)],
    entity_delays: { "sensor.one": 30, "light.two": 60 },
  });
});

test("native Home Assistant selectors are configured for multiple values", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._activeTab = "settings";
  panel._hass = { states: {} };
  const selectors = Object.fromEntries(
    ["#excluded-labels", "#excluded-entities", "#excluded-devices"].map((id) => [
      id,
      { addEventListener() {} },
    ]),
  );
  panel.shadowRoot.querySelector = (selector) => selectors[selector] ?? null;

  panel._hydrateSelectors();

  assert.deepEqual(selectors["#excluded-labels"].selector, { label: { multiple: true } });
  assert.deepEqual(selectors["#excluded-entities"].selector, {
    entity: {
      multiple: true,
      exclude_entities: [
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "switch.alert_manager_main_monitoring",
      ],
    },
  });
  assert.deepEqual(selectors["#excluded-devices"].selector, { device: { multiple: true } });
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
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "switch.alert_manager_main_monitoring",
      ],
    },
  });
  assert.deepEqual(selector.value, ["sensor.one", "sensor.two"]);
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
  ]);
  assert.equal(operator.value, "above");
  assert.deepEqual(operator.options.map((option) => option.value), [
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "above",
    "below",
  ]);
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

test("a missing alert source is not rendered as a clickable link", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const html = panel._renderAlert(
    { entity_id: "sensor.deleted", name: "Deleted", condition: "Test" },
    true,
  );
  assert.doesNotMatch(html, /data-action="more-info"/);
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
    "Automatic monitoring",
    "Custom rules",
    "Configuration",
  ]);
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
  assert.equal(panel._conditionText({ condition: "User text" }), "User text");
});
