import assert from "node:assert/strict";
import test from "node:test";

globalThis.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = {
      addEventListener() {},
      querySelector() { return null; },
      querySelectorAll() { return []; },
      innerHTML: "",
    };
    return this.shadowRoot;
  }
};
globalThis.customElements = {
  items: new Map(),
  define(name, value) { this.items.set(name, value); },
  get(name) { return this.items.get(name); },
};
globalThis.window = {
  localStorage: {
    getItem() { return null; },
    setItem() {},
  },
};

await import("../custom_components/alert_manager/frontend/alert-manager-panel.js");

test("standalone bundle registers the composed panel", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();

  assert.ok(panel instanceof HTMLElement);
  assert.equal(typeof panel._render, "function");
  assert.equal(typeof panel._durationText, "function");
  assert.equal(typeof panel._saveRule, "function");
  assert.equal(typeof panel._saveSettings, "function");
  assert.match(panel._styles(), /hass-tabs-subpage-data-table/);
});
