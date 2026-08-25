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
    attributes: {
      active_count: 0,
      pending_count: 0,
      tracked_count: 12,
      alerts: [],
      pending: [],
    },
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

  assert.match(panel._renderAlert(alert, true), /<ha-card outlined class="alert-card is-active"/);
  assert.match(panel._renderAlert(alert, false), /<ha-card outlined class="alert-card is-pending"/);
  assert.doesNotMatch(panel._renderAlert(alert, true), /severity|warning|critical/);
  assert.match(panel._styles(), /\.alert-card\.is-active\{--alert-state-color:var\(--error-color/);
  assert.match(panel._renderAlert(alert, true), /<ha-svg-icon path=/);
  assert.match(panel._renderAlert(alert, true), /class="alert-status">Active</);
  assert.match(panel._renderAlert(alert, false), /class="alert-status">En attente</);
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

test("alert groups use native Home Assistant cards without nested panels", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._hass = { states: {} };
  const alert = { entity_id: "sensor.test", name: "Test", condition: "Test" };

  const populated = panel._renderAlertGroup("Alertes actives", [alert], true);
  const empty = panel._renderAlertGroup("Alertes en attente", [], false);

  assert.match(populated, /<section class="alert-group">/);
  assert.match(populated, /<ha-card outlined class="alert-card is-active"/);
  assert.doesNotMatch(populated, /<section class="panel">/);
  assert.match(empty, /<ha-card outlined class="alert-empty">/);
});

test("navigation delegates the toolbar and tabs to hass-tabs-subpage", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = completeConfig();
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
    { path: "/alert-manager/settings", name: "Exclusions et paramètres" },
  ]);
  assert.ok(shell.tabs.every((tab) => typeof tab.iconPath === "string" && tab.iconPath.startsWith("M")));
  assert.match(panel._styles(), /font-family:var\(--ha-font-family-body/);
  assert.doesNotMatch(panel._styles(), /ha-top-app-bar-fixed|ha-tab-group|\.native-tabs|\.tab-label/);
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
  const automatic = panel._renderAutomatic();
  panel._ensureSettingsDraft();
  const settings = panel._renderSettings();
  const styles = panel._styles();

  assert.match(automatic, /<ha-input[^>]+id="auto-unavailable-delay"/);
  assert.match(automatic, /<ha-switch id="auto-unavailable-enabled"/);
  assert.match(automatic, /<ha-button appearance="filled" data-action="save-automatic"/);
  assert.match(automatic, /<form id="automatic-form" class="automatic-grid">/);
  assert.match(settings, /<ha-input[^>]+id="global-delay"/);
  assert.match(settings, /<ha-selector id="excluded-labels"/);
  assert.match(settings, /<ha-button appearance="filled" data-action="add-entity-delay">Ajouter<\/ha-button>/);
  assert.match(settings, /<ha-button appearance="filled" data-action="save-settings"/);
  assert.doesNotMatch(automatic + settings, /class="input-suffix"|class="switch"/);
  assert.match(styles, /ha-input\{--ha-input-padding-bottom:0\}/);
  assert.match(styles, /\.automatic-grid\{[^}]*grid-template-columns:repeat\(2/);
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
  assert.match(editor, /<ha-card outlined class="rule-editor-drawer"[\s\S]*<ha-dialog-header show-border>[\s\S]*<ha-icon-button id="rule-editor-close"/);
  assert.match(editor, /<form id="rule-form" class="fields rule-editor-form">[\s\S]*data-field="name"[\s\S]*<div class="switch-field"><span class="field-label">Règle activée/);
  assert.match(editor, /<ha-switch id="rule-enabled" data-field="enabled" checked/);
  assert.match(editor, /<ha-button appearance="plain" variant="danger" data-action="delete-rule" data-id="enabled">Supprimer<\/ha-button>/);
  assert.match(editor, /appearance="plain" data-action="cancel-rule"/);
  assert.doesNotMatch(editor, /<aside|<input/);
  assert.match(settings, /appearance="plain" variant="danger" data-action="remove-entity-delay"/);
  assert.match(panel._styles(), /\.delay-row\{[^}]*align-items:start/);
  assert.match(panel._styles(), /\.delay-row>ha-button\{margin-top:8px\}/);
  assert.match(panel._styles(), /ha-card\.rule-editor-drawer\{position:fixed/);
});

test("overview displays the backend tracked total", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._alerts = {
    active_count: 2,
    pending_count: 3,
    tracked_count: 47,
    alerts: [],
    pending: [],
  };

  assert.match(panel._renderOverview(), /Total suivi<\/span><strong>47<\/strong>/);
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
  assert.equal(operator.options.length, 4);
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
