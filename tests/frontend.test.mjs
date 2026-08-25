import assert from "node:assert/strict";
import test from "node:test";

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
  define(name, value) { this._items.set(name, value); },
  get(name) { return this._items.get(name); },
};
globalThis.window = {
  confirm: () => true,
};

const { durationText, lines, newRuleDefaults } = await import(
  "../frontend-src/alert-manager-panel.js"
);

test("human duration formatter", () => {
  assert.equal(durationText(45), "45 s");
  assert.equal(durationText(900), "15 min");
  assert.equal(durationText(7200), "2 h");
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

test("new rules start enabled with safe defaults", () => {
  assert.deepEqual(newRuleDefaults(), {
    name: "",
    entity_ids: [],
    enabled: true,
    source: "state",
    attribute: "",
    operator: "equals",
    value: "",
    duration: 900,
    message: "",
  });
});

test("unrelated Home Assistant updates do not rerender the overview", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = { rules: [] };
  let renders = 0;
  panel._render = () => { renders += 1; };
  const sensor = {
    state: "0",
    attributes: { active_count: 0, pending_count: 0, alerts: [], pending: [] },
  };
  panel.hass = { states: { "sensor.alert_manager": sensor } };
  panel.hass = {
    states: { "sensor.alert_manager": sensor, "sensor.other": { state: "1" } },
  };
  assert.equal(renders, 1);
});

const completeConfig = () => ({
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
        value: "0",
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
  assert.equal(panel._notice.text, "Règle refusée");
  assert.deepEqual(panel._editingRule.entity_ids, ["todo.liste_d_achats"]);
  assert.equal(panel._editingRule.value, "0");
});

test("active alerts are red while pending alerts stay orange", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: { "sensor.test": { state: "on" } } };
  const alert = {
    entity_id: "sensor.test",
    name: "Test",
    condition: "État indisponible",
  };

  assert.match(panel._renderAlert(alert, true), /class="alert-card is-active"/);
  assert.match(panel._renderAlert(alert, false), /class="alert-card is-pending"/);
  assert.doesNotMatch(panel._renderAlert(alert, true), /severity|warning|critical/);
  assert.match(panel._styles(), /\.alert-card\.is-active\{border-left-color:var\(--error-color/);
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
  assert.match(styles, /grid-template-columns:minmax\(0,\.85fr\) minmax\(0,1\.15fr\)/);
  assert.match(styles, /\.alert-condition dd\{[^}]*white-space:nowrap/);
});

test("tabs use Home Assistant dimensions, typography and icons", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
  panel._loading = false;

  panel._render();

  assert.match(panel.shadowRoot.innerHTML, /role="tablist"/);
  assert.match(panel.shadowRoot.innerHTML, /<ha-icon icon="mdi:view-dashboard-outline"/);
  assert.match(panel.shadowRoot.innerHTML, /<ha-icon icon="mdi:radar"/);
  assert.match(panel.shadowRoot.innerHTML, /<ha-icon icon="mdi:format-list-checks"/);
  assert.match(panel.shadowRoot.innerHTML, /<ha-icon icon="mdi:tune-variant"/);
  assert.match(panel.shadowRoot.innerHTML, /role="tab" aria-selected="true"/);
  assert.match(panel._styles(), /font-family:var\(--ha-font-family-body/);
  assert.match(panel._styles(), /nav\{[^}]*min-height:56px/);
  assert.match(panel._styles(), /\.tab\{[^}]*font-size:var\(--ha-font-size-m,14px\)/);
});

test("legacy form controls follow the native Home Assistant field style", () => {
  const Panel = customElements.get("alert-manager-panel");
  const styles = new Panel()._styles();

  assert.match(styles, /--alert-manager-control-height:56px/);
  assert.match(styles, /input:not\(\[type="checkbox"\]\),select,textarea\{[^}]*background:var\(--input-fill-color/);
  assert.match(styles, /border-bottom:1px solid var\(--input-idle-line-color/);
  assert.match(styles, /ha-selector\{[^}]*min-height:var\(--alert-manager-control-height\)/);
  assert.match(styles, /\.input-suffix\{[^}]*min-height:var\(--alert-manager-control-height\)/);
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
  assert.deepEqual(selectors["#excluded-entities"].selector, { entity: { multiple: true } });
  assert.deepEqual(selectors["#excluded-devices"].selector, { device: { multiple: true } });
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

  assert.deepEqual(selector.selector, { entity: { multiple: true } });
  assert.deepEqual(selector.value, ["sensor.one", "sensor.two"]);
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
