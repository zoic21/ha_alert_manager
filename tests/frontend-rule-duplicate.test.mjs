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

test("mobile overview keeps extra spacing below summary cards", () => {
  const panel = new AlertManagerPanel();
  assert.match(
    panel._styles(),
    /@media\(max-width:700px\)\{\.table-page-top \.summary\{margin-bottom:28px\}\}/,
  );
});

test("mobile overview focuses the Home Assistant content scroller before more info", () => {
  const panel = new AlertManagerPanel();
  let focusCalls = 0;
  const subpage = {
    focusContentScroller() { focusCalls += 1; },
  };
  const tablePage = {
    shadowRoot: {
      querySelector(selector) {
        return selector === "hass-tabs-subpage" ? subpage : null;
      },
    },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === '[data-alert-table-page="overview"]' ? tablePage : null
  );
  panel._narrow = true;
  panel._activeTab = "overview";

  panel._focusOverviewContentScroller();
  assert.equal(focusCalls, 1);

  panel._narrow = false;
  panel._focusOverviewContentScroller();
  assert.equal(focusCalls, 1);
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

test("attribute mode uses a Home Assistant selector instead of a plain text input", () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = {
    ...rule(),
    source: "attribute",
    attribute: "unit_of_measurement",
  };

  const markup = panel._renderRuleEditor();

  assert.match(markup, /<ha-selector id="rule-attribute" data-field="attribute"><\/ha-selector>/);
  assert.doesNotMatch(markup, /<ha-input name="attribute"/);
});

test("attribute suggestions merge first-level attributes across selected entities without duplicates", () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = {
    ...rule(),
    source: "attribute",
    attribute: "unit_of_measurement",
    entity_ids: ["sensor.one", "sensor.two", "sensor.missing"],
  };
  panel._hass = {
    states: {
      "sensor.one": {
        attributes: {
          friendly_name: "One",
          unit_of_measurement: "W",
          nested: { child: true },
        },
      },
      "sensor.two": {
        attributes: {
          device_class: "power",
          friendly_name: "Two",
          precision: 1,
        },
      },
    },
  };

  const selectorElement = {};
  panel.shadowRoot.querySelector = (query) => query === "#rule-attribute" ? selectorElement : null;

  assert.deepEqual(panel._ruleAttributeOptions(), [
    "device_class",
    "friendly_name",
    "nested",
    "precision",
    "unit_of_measurement",
  ]);
  assert.equal(panel._ruleAttributeOptions().includes("child"), false);

  panel._refreshRuleAttributeSelector();

  assert.equal(selectorElement.hass, panel._hass);
  assert.equal(selectorElement.value, "unit_of_measurement");
  assert.deepEqual(selectorElement.selector, {
    select: {
      options: [
        "device_class",
        "friendly_name",
        "nested",
        "precision",
        "unit_of_measurement",
      ],
      custom_value: true,
      mode: "dropdown",
    },
  });
});

test("changing selected entities refreshes attribute suggestions immediately", () => {
  const panel = new AlertManagerPanel();
  const listeners = new Map();
  const entitySelector = {
    addEventListener(name, callback) {
      listeners.set(name, callback);
    },
  };
  panel.shadowRoot.querySelector = (query) => query === "#rule-entity-ids" ? entitySelector : null;

  let receivedValue = null;
  let refreshCount = 0;
  panel._refreshRuleAttributeSelector = () => { refreshCount += 1; };

  panel._configureSelector(
    "rule-entity-ids",
    { entity: { multiple: true } },
    [],
    (value) => { receivedValue = value; },
  );

  listeners.get("value-changed")({ detail: { value: ["sensor.one", "sensor.two"] } });

  assert.deepEqual(receivedValue, ["sensor.one", "sensor.two"]);
  assert.equal(refreshCount, 1);
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
