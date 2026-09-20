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

  dispatchEvent() {
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
  define(name, value) { this._items.set(name, value); },
  get(name) { return this._items.get(name); },
};

const storage = new Map();
globalThis.window = {
  localStorage: {
    getItem(key) { return storage.get(key) ?? null; },
    setItem(key, value) { storage.set(key, value); },
    clear() { storage.clear(); },
  },
};

await import("../frontend-src/alert-manager-panel.js");

const Panel = customElements.get("alert-manager-panel");

const rules = () => [
  {
    id: "active-rule",
    name: "Temperature",
    entity_ids: ["sensor.temperature"],
    enabled: true,
    source: "value",
    operator: "above",
    value: 25,
    duration: 900,
  },
  {
    id: "inactive-rule",
    name: "Humidity",
    entity_ids: ["sensor.humidity"],
    enabled: false,
    source: "value",
    operator: "above",
    value: 70,
    duration: 300,
  },
];

const tablePage = () => ({
  listeners: {},
  shadowRoot: {
    nativeTable: {
      style: {
        values: {},
        setProperty(name, value) { this.values[name] = value; },
      },
    },
    querySelector(selector) { return selector === "ha-data-table" ? this.nativeTable : null; },
  },
  addEventListener(name, callback) { this.listeners[name] = callback; },
  querySelectorAll() { return []; },
});

test("custom rules use the native Home Assistant table toolbar without grouping", () => {
  const panel = new Panel();
  panel._config = { rules: rules() };
  const rendered = panel._renderRules();

  assert.match(rendered, /hass-tabs-subpage-data-table/);
  assert.match(rendered, /data-rules-table-page/);
  assert.match(rendered, /has-filters/);
  assert.match(rendered, /slot="filter-pane"/);
  assert.doesNotMatch(rendered, /grouping-changed/);
});

test("custom rules render without a second tabs subpage wrapper", () => {
  const panel = new Panel();
  panel._hass = {};
  panel._config = { rules: rules() };
  panel._loading = false;
  panel._activeTab = "rules";
  panel._render();

  assert.match(panel.shadowRoot.innerHTML, /<hass-tabs-subpage-data-table/);
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /<hass-tabs-subpage id="panel-shell"/);
});

test("rules table keeps name and activation visible and wires native controls", () => {
  const panel = new Panel();
  const table = tablePage();
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-rules-table-page]" ? table : null
  );
  panel._hass = {};
  panel._config = { rules: rules() };
  panel._narrow = true;
  panel._hydrateRuleTable();

  assert.equal(table.narrow, true);
  assert.equal(table.clickable, true);
  assert.equal(table.columns.name.main, true);
  assert.equal(table.columns.name.hideable, false);
  assert.equal(table.columns.name.moveable, false);
  assert.equal(table.columns.enabled.showNarrow, true);
  assert.equal(table.columns.enabled.hideable, false);
  assert.equal(table.columns.enabled.moveable, false);
  assert.equal(table.columns.enabled.valueColumn, "enabledSort");
  assert.equal(table.columns.search_index.filterable, true);
  assert.equal(
    Object.values(table.columns).some((column) => column.groupable === true),
    false,
  );
  assert.deepEqual(table.columnOrder, ["name", "entities", "condition", "duration", "enabled"]);
  assert.deepEqual(table.data.map((row) => row.enabledSort), [1, 0]);
  assert.equal(typeof table.listeners["search-changed"], "function");
  assert.equal(typeof table.listeners["clear-filter"], "function");
  assert.equal(typeof table.listeners["sorting-changed"], "function");
  assert.equal(typeof table.listeners["columns-changed"], "function");
  assert.equal(typeof table.listeners["row-click"], "function");
  assert.equal(
    table.shadowRoot.nativeTable.style.values.width,
    "var(--alert-manager-rule-table-width, 100%)",
  );

  table.listeners["search-changed"]({ detail: { value: "humidity" } });
  assert.equal(panel._tableState.rules.search, "humidity");

  table.listeners["sorting-changed"]({
    detail: { column: "enabled", direction: "desc" },
  });
  assert.equal(panel._tableState.rules.sortBy, "enabled");
  assert.equal(panel._tableState.rules.sortDirection, "desc");

  table.listeners["columns-changed"]({
    detail: {
      columnOrder: ["enabled", "name", "duration", "entities", "condition"],
      hiddenColumns: ["entities", "name", "enabled"],
    },
  });
  assert.deepEqual(
    panel._tableState.rules.columnOrder,
    ["name", "duration", "entities", "condition", "enabled"],
  );
  assert.deepEqual(panel._tableState.rules.hiddenColumns, ["entities"]);

  panel._refreshRuleEditor = () => {};
  table.listeners["row-click"]({ detail: { id: "inactive-rule" } });
  assert.equal(panel._editingRule.id, "inactive-rule");
});

test("rules content width is installed after the native table finishes rendering", async () => {
  const panel = new Panel();
  const table = tablePage();
  let finishNativeRender;
  table.updateComplete = new Promise((resolve) => { finishNativeRender = resolve; });
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-rules-table-page]" ? table : null
  );
  panel._hass = {};
  panel._config = { rules: rules() };

  panel._hydrateRuleTable();

  assert.equal(table.shadowRoot.nativeTable.style.values.width, undefined);
  finishNativeRender();
  await table.updateComplete;
  await Promise.resolve();
  assert.equal(
    table.shadowRoot.nativeTable.style.values.width,
    "var(--alert-manager-rule-table-width, 100%)",
  );
});

test("active filter and mobile secondary details follow the saved column choices", () => {
  const panel = new Panel();
  panel._hass = {};
  panel._config = { rules: rules() };
  panel._tableState.rules = {
    search: "",
    filters: { enabled: ["inactive"] },
    columnOrder: ["name", "duration", "condition", "entities", "enabled"],
    hiddenColumns: ["condition"],
    sortBy: "name",
    sortDirection: "asc",
  };
  const table = tablePage();
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-rules-table-page]" ? table : null
  );
  panel._hydrateRuleTable();

  assert.equal(table.filters, 1);
  assert.deepEqual(table.data.map((row) => row.id), ["inactive-rule"]);

  const cell = panel._nativeRuleNameCell({
    name: "Humidity",
    entities: "sensor.humidity",
    condition: "State above 70",
    duration: "5 min",
  }, true);
  assert.equal(cell.children[0].textContent, "Humidity");
  assert.equal(cell.children[1].textContent, "5 min · sensor.humidity");
});

test("rule table renders native label badges on desktop and mobile and indexes their names", () => {
  const panel = new Panel();
  panel._config = { rules: [{ ...rules()[0], label_ids: ["cold", "deleted"] }] };
  panel._labels = [{ label_id: "cold", name: "Freezer", color: "blue", description: "Food", icon: "mdi:snowflake" }];
  customElements._items.delete("ha-label");
  const row = panel._ruleTableRows()[0];
  assert.match(row.search_index, /cold Freezer deleted deleted/);
  for (const narrow of [false, true]) {
    const cell = panel._nativeRuleNameCell(row, narrow);
    const badges = cell.children[1].children;
    assert.equal(badges[0].tagName, "HA-LABEL");
    assert.equal(badges[0].textContent, "Freezer");
    assert.equal(badges[0].attributes.color, "blue");
    assert.equal(badges[0].attributes.description, "Food");
    assert.equal(badges[0].children[0].tagName, "HA-ICON");
    assert.equal(badges[0].children[0].attributes.slot, "icon");
    assert.equal(badges[0].children[0].attributes.icon, "mdi:snowflake");
    assert.equal(badges[1].textContent, "deleted");
  }
});


test("native labels load once through HA's entities route and retain pending badges", async () => {
  const { loadNativeLabels, nativeLabelBadges } = await import("../frontend-src/components/alert-table.js");
  const originalDocument = globalThis.document;
  let configLoads = 0;
  let entityLoads = 0;
  const hass = { panels: { config: { component_name: "config", url_path: "config" } } };
  const resolver = { routerOptions: { routes: { config: { load: async () => {
    configLoads += 1;
    customElements.define("ha-panel-config", class {});
  } } } } };
  const main = { shadowRoot: { querySelector: () => resolver } };
  const homeAssistant = { shadowRoot: { querySelector: () => main } };
  customElements._items.delete("ha-label");
  globalThis.document = {
    querySelector: () => homeAssistant,
    createElement: (tag) => tag === "ha-panel-config"
      ? { routerOptions: { routes: { entities: { load: async () => {
        entityLoads += 1;
        customElements.define("ha-label", class {});
      } } } } }
      : fakeDomElement(tag),
  };
  try {
    const badges = nativeLabelBadges([{ name: "Cold", color: "blue", icon: "mdi:snowflake" }], hass);
    await Promise.all([loadNativeLabels(hass), loadNativeLabels(hass)]);
    assert.equal(configLoads, 1);
    assert.equal(entityLoads, 1);
    assert.equal(badges.children[0].tagName, "HA-LABEL");
    assert.equal(badges.children[0].attributes.color, "blue");
    await loadNativeLabels(hass);
    assert.equal(entityLoads, 1);
  } finally {
    globalThis.document = originalDocument;
    customElements._items.delete("ha-label");
    customElements._items.delete("ha-panel-config");
  }
});

test("opening custom rules does not request rule discovery or maintenance", async () => {
  const { refreshTabData } = await import("../frontend-src/api/alert-manager-api.js");
  const panel = {
    _hass: {}, _config: { rules: rules() },
    _api: { call() { assert.fail("opening rules must use the loaded configuration"); } },
  };
  refreshTabData.call(panel, "rules");
  await new Promise((resolve) => setTimeout(resolve, 0));
});

test("rules display their title without a status icon on desktop and mobile", () => {
  const panel = new Panel();
  for (const narrow of [false, true]) {
    const cell = panel._nativeRuleNameCell({ name: "Updates" }, narrow);
    assert.equal(cell.children[0].textContent, "Updates");
    assert.equal(cell.children[0].tagName, "SPAN");
    assert.equal(cell.children[0].children.length, 0);
    assert.ok(cell.children.every((child) => child.tagName !== "HA-ICON"));
  }
});

test("sequence rows omit duration while simple rules retain zero delay", async () => {
  const { buildRuleTableRows } = await import("../frontend-src/views/rules.js");
  const rows = buildRuleTableRows([
    { id: "sequence", source: "value_sequence", duration: 0 },
    { id: "simple", source: "value", duration: 0 },
  ], { t: (key) => key, summarizeRule: () => "", formatDuration: (value) => `${value} s` });
  assert.equal(rows[0].duration, "");
  assert.equal(rows[0].durationSort, null);
  assert.equal(rows[1].duration, "0 s");
});

test("rule label filters combine with status and survive targeted data refreshes", () => {
  const panel = new Panel();
  const table = tablePage();
  panel._activeTab = "rules";
  panel._config = { rules: [
    { ...rules()[0], label_ids: ["cold", "shared"] },
    { ...rules()[1], label_ids: ["wet", "shared"] },
    { ...rules()[0], id: "unlabelled" },
  ] };
  panel._labels = [{ label_id: "cold", name: "Freezer" }];
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-rules-table-page]" ? table : null
  );
  panel._refreshUiState = () => {};
  const state = panel._ensureRulesTableState();
  assert.deepEqual(state.filters.labels, []);
  state.filters.labels = ["cold", "wet"];
  panel._hydrateRuleTable();
  assert.deepEqual(table.data.map((row) => row.id), ["active-rule", "inactive-rule"]);
  assert.equal(table.filters, 1);
  state.filters.enabled = ["inactive"];
  panel._refreshRulesData();
  assert.deepEqual(table.data.map((row) => row.id), ["inactive-rule"]);
  assert.equal(table.filters, 2);
  state.filters.labels = ["cold"];
  panel._refreshRulesData();
  assert.deepEqual(table.data, []);
  panel._config.rules[1].label_ids.push("cold");
  panel._refreshRulesData();
  assert.deepEqual(table.data.map((row) => row.id), ["inactive-rule"]);
  panel._render = () => {};
  table.listeners["clear-filter"]();
  assert.deepEqual(state.filters, { enabled: [], labels: [] });
  panel._hydrateRuleTable();
  assert.equal(table.data.length, 3);
  assert.equal(table.filters, 0);
});

test("rule label facets use rule labels and checkbox events update only their own filter", () => {
  const panel = new Panel();
  panel._config = { rules: [
    { ...rules()[0], label_ids: ["cold", "missing"] },
    { ...rules()[1], label_ids: ["cold"] },
  ] };
  panel._labels = [
    { label_id: "cold", name: "Freezer <1>" },
    { label_id: "unused", name: "Unused" },
  ];
  const rendered = panel._renderRules();
  assert.match(rendered, /Freezer &lt;1&gt;/);
  assert.equal((rendered.match(/data-table-filter-option="labels"/g) ?? []).length, 2);
  assert.doesNotMatch(rendered, /Unused/);
  const checkbox = fakeDomElement("ha-checkbox");
  checkbox.dataset = { tableFilterOption: "labels", filterValue: "cold" };
  const table = tablePage();
  table.querySelectorAll = () => [checkbox];
  panel.shadowRoot.querySelector = () => table;
  panel._render = () => {};
  const state = panel._ensureRulesTableState();
  state.filters.enabled = ["active"];
  panel._hydrateRuleTable();
  assert.equal(checkbox.checked, false);
  checkbox.checked = true;
  checkbox.listeners.change({ stopPropagation() {} });
  assert.deepEqual(state.filters, { enabled: ["active"], labels: ["cold"] });
  panel._hydrateRuleTable();
  assert.equal(checkbox.checked, true);
  checkbox.checked = false;
  checkbox.listeners.change({ stopPropagation() {} });
  assert.deepEqual(state.filters, { enabled: ["active"], labels: [] });
});
