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

const coherenceResult = () => ({
  results: [{
    entity_id: "sensor.missing_entity",
    source_type: "automation",
    source_name: "Thermostat : bureau",
    file: "automations.yaml",
    line: 42,
    link: { type: "navigate", path: "/config/automation/edit/123" },
  }],
  missing_count: 1,
  files_scanned: 4,
  files_skipped: 0,
  references_checked: 12,
  duration_ms: 8,
  scanned_at: "2026-08-28T12:00:00+00:00",
});

test("coherence narrow cell keeps entity primary and metadata secondary in selected order", () => {
  const panel = new Panel();
  panel._coherenceTableState = {
    search: "",
    columnOrder: ["entity", "file", "type", "source", "line", "action"],
    hiddenColumns: ["source"],
    sortBy: "entity",
    sortDirection: "asc",
    groupBy: "",
  };
  const cell = panel._nativeCoherenceEntityCell({
    entity: "sensor.missing_entity",
    type: "Automatisation",
    source: "Thermostat : bureau",
    file: "automations.yaml",
    line: "42",
  }, true);

  assert.equal(cell.children[0].textContent, "sensor.missing_entity");
  assert.equal(
    cell.children[1].textContent,
    "automations.yaml · Automatisation · 42",
  );
});

test("coherence result uses the native Home Assistant data-table toolbar without filters", () => {
  const panel = new Panel();
  panel._coherence = coherenceResult();
  const rendered = panel._renderCoherence();

  assert.match(rendered, /hass-tabs-subpage-data-table/);
  assert.match(rendered, /data-coherence-table-page/);
  assert.doesNotMatch(rendered, /has-filters/);
});

test("coherence table exposes search, sorting, grouping and column settings", () => {
  const panel = new Panel();
  const tablePage = {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-coherence-table-page]" ? tablePage : null
  );
  panel._hass = {};
  panel._coherence = coherenceResult();
  panel.narrow = true;
  panel._hydrateCoherenceTable();

  assert.equal(tablePage.narrow, true);
  assert.equal(tablePage.clickable, true);
  assert.equal(tablePage.columns.entity.main, true);
  assert.equal(tablePage.columns.entity.groupable, true);
  assert.equal(tablePage.columns.entity.hideable, false);
  assert.equal(tablePage.columns.type.groupable, undefined);
  assert.equal(tablePage.columns.search_index.filterable, true);
  assert.deepEqual(
    tablePage.columnOrder,
    ["entity", "type", "source", "file", "line", "action"],
  );
  assert.equal(tablePage.initialSorting.column, "entity");
  assert.equal(tablePage.initialSorting.direction, "asc");
  assert.equal(tablePage.initialGroupColumn, undefined);
  assert.equal(typeof tablePage.listeners["search-changed"], "function");
  assert.equal(typeof tablePage.listeners["sorting-changed"], "function");
  assert.equal(typeof tablePage.listeners["grouping-changed"], "function");
  assert.equal(typeof tablePage.listeners["columns-changed"], "function");

  tablePage.listeners["search-changed"]({ detail: { value: "thermostat" } });
  assert.equal(panel._coherenceTableState.search, "thermostat");

  tablePage.listeners["sorting-changed"]({
    detail: { column: "file", direction: "desc" },
  });
  assert.equal(panel._coherenceTableState.sortBy, "file");
  assert.equal(panel._coherenceTableState.sortDirection, "desc");

  tablePage.listeners["grouping-changed"]({ detail: { value: "entity" } });
  assert.equal(panel._coherenceTableState.groupBy, "entity");

  tablePage.listeners["columns-changed"]({
    detail: {
      columnOrder: ["entity", "line", "file", "type", "source", "action"],
      hiddenColumns: ["source"],
    },
  });
  assert.deepEqual(
    panel._coherenceTableState.columnOrder,
    ["entity", "line", "file", "type", "source", "action"],
  );
  assert.deepEqual(panel._coherenceTableState.hiddenColumns, ["source"]);
});

test("coherence row click opens the exact Home Assistant target", () => {
  const panel = new Panel();
  const tablePage = {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-coherence-table-page]" ? tablePage : null
  );
  panel._hass = {};
  panel._coherence = coherenceResult();
  panel._hydrateCoherenceTable();

  let navigated = null;
  panel._navigate = (path, newTab) => { navigated = [path, newTab]; };
  tablePage.listeners["row-click"]({ detail: { id: tablePage.data[0].id } });
  assert.deepEqual(navigated, ["/config/automation/edit/123", true]);

  let moreInfo = null;
  panel._openMoreInfo = (entityId) => { moreInfo = entityId; };
  tablePage.data[0].link = { type: "more_info", entity_id: "sensor.template_result" };
  tablePage.listeners["row-click"]({ detail: { id: tablePage.data[0].id } });
  assert.equal(moreInfo, "sensor.template_result");
});
