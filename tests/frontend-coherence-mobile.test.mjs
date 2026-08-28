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
globalThis.window = {
  localStorage: {
    getItem() { return null; },
    setItem() {},
  },
};

await import("../frontend-src/alert-manager-panel-entry.js");

const Panel = customElements.get("alert-manager-panel");

test("coherence narrow cell keeps entity primary and requested metadata secondary", () => {
  const panel = new Panel();
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
    "Automatisation · Thermostat : bureau · automations.yaml · 42",
  );
});

test("coherence table follows Home Assistant narrow mode and opens row targets", () => {
  const panel = new Panel();
  const table = {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
  panel.shadowRoot.querySelector = (selector) => selector === "#coherence-table" ? table : null;
  panel._hass = {};
  panel._coherence = {
    results: [{
      entity_id: "sensor.missing_entity",
      source_type: "automation",
      source_name: "Thermostat : bureau",
      file: "automations.yaml",
      line: 42,
      link: { type: "navigate", path: "/config/automation/edit/123" },
    }],
  };
  panel.narrow = true;
  panel._hydrateCoherenceTable();

  assert.equal(table.narrow, true);
  assert.equal(table.clickable, true);
  assert.equal(typeof table.columns.entity.template, "function");
  assert.equal(table._alertManagerRows, table.data);

  let navigated = null;
  panel._navigate = (path, newTab) => { navigated = [path, newTab]; };
  table.listeners["row-click"]({ detail: { id: table.data[0].id } });
  assert.deepEqual(navigated, ["/config/automation/edit/123", true]);

  let moreInfo = null;
  panel._openMoreInfo = (entityId) => { moreInfo = entityId; };
  table.data[0].link = { type: "more_info", entity_id: "sensor.template_result" };
  table.listeners["row-click"]({ detail: { id: table.data[0].id } });
  assert.equal(moreInfo, "sensor.template_result");
});
