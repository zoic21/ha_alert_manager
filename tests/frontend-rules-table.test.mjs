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
    source: "state",
    operator: "above",
    value: 25,
    duration: 900,
  },
  {
    id: "inactive-rule",
    name: "Humidity",
    entity_ids: ["sensor.humidity"],
    enabled: false,
    source: "state",
    operator: "above",
    value: 70,
    duration: 300,
  },
];

const tablePage = () => ({
  listeners: {},
  shadowRoot: {
    styles: [],
    querySelector() { return null; },
    append(node) { this.styles.push(node); },
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
  assert.equal(table.shadowRoot.styles.length, 1);
  assert.match(
    table.shadowRoot.styles[0].textContent,
    /width: var\(--alert-manager-rule-table-width, 100%\)/,
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

  assert.equal(table.shadowRoot.styles.length, 0);
  finishNativeRender();
  await table.updateComplete;
  await Promise.resolve();
  assert.equal(table.shadowRoot.styles.length, 1);
  assert.match(
    table.shadowRoot.styles[0].textContent,
    /width: var\(--alert-manager-rule-table-width, 100%\)/,
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
