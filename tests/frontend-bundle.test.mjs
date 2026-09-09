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

await import("../custom_components/alert_manager/frontend/alert-manager-card.js");

test("standalone dashboard bundle coexists with the panel and embeds offline translations", () => {
  const Card = customElements.get("alert-manager-card");
  const card = new Card();
  assert.equal(card.connectedWhileHidden, true);
  assert.equal(card._t("dashboard.max_tiles"), "Maximum number of tiles");
  assert.ok(customElements.get("alert-manager-card-editor"));
  assert.equal(window.customCards.filter((item) => item.type === "alert-manager-card").length, 1);
});
