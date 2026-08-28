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
};

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

globalThis.document = {
  createElement(tagName) {
    return {
      tagName: tagName.toUpperCase(),
      style: {},
      setAttribute() {},
      append() {},
    };
  },
};

await import("../frontend-src/alert-manager-panel-runtime.js");
const { AlertManagerPanel } = await import("../frontend-src/alert-manager-panel.js");

const rule = () => ({
  id: "rule-1",
  name: "Original",
  entity_ids: ["sensor.one"],
  enabled: true,
  source: "state",
  attribute: "",
  operator: "equals",
  value: ["on"],
  duration: 60,
  message: "Original message",
  condition_template: "",
});

test("rule editor menu follows Home Assistant actions styling", () => {
  const panel = new AlertManagerPanel();
  panel._hass = {
    localize(key) {
      return key === "ui.panel.config.automation.editor.duplicate" ? "Dupliquer" : undefined;
    },
  };
  panel._language = "fr";
  panel._editingRule = rule();

  const markup = panel._renderRuleEditor();

  assert.match(markup, /value="switch-editor"><ha-icon slot="icon" icon="mdi:playlist-edit"/);
  assert.match(markup, /value="duplicate-rule"><ha-icon slot="icon" icon="mdi:plus-circle-multiple-outline"><\/ha-icon>Dupliquer/);
  assert.match(markup, /value="delete-rule" variant="danger"><ha-icon slot="icon" icon="mdi:delete"/);
});

test("duplicating a rule creates an unsaved copy without reusing its id or name", async () => {
  const panel = new AlertManagerPanel();
  const original = rule();
  const originalEntities = original.entity_ids;
  const originalValues = original.value;
  panel._editingRule = original;
  panel._ruleEditorMode = "visual";
  panel._captureRuleDraft = () => {
    panel._editingRule.message = "Unsaved draft change";
  };
  panel._refreshRuleEditor = () => {};

  await panel._duplicateRuleDraft();

  assert.equal("id" in panel._editingRule, false);
  assert.equal(panel._editingRule.name, "");
  assert.equal(panel._editingRule.message, "Unsaved draft change");
  assert.deepEqual(panel._editingRule.entity_ids, ["sensor.one"]);
  assert.deepEqual(panel._editingRule.value, ["on"]);
  assert.notEqual(panel._editingRule.entity_ids, originalEntities);
  assert.notEqual(panel._editingRule.value, originalValues);
  assert.equal(panel._ruleDirty, true);
});
