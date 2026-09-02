import assert from "node:assert/strict";
import test from "node:test";

import { compactCss } from "./frontend-test-helpers.mjs";

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

  toggleAttribute(name, force) {
    this._attributes ??= new Set();
    if (force) this._attributes.add(name);
    else this._attributes.delete(name);
  }

  hasAttribute(name) {
    return this._attributes?.has(name) ?? false;
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

test("overview keeps summary spacing inside the gray header at every width", () => {
  const panel = new AlertManagerPanel();
  const styles = compactCss(panel._styles());

  assert.match(styles, /\.table-page-top\{display:flow-root\}/);
  assert.match(styles, /\.table-page-top \.summary\{margin-bottom:20px\}/);
  assert.doesNotMatch(styles, /margin-bottom:28px/);
  assert.doesNotMatch(
    styles,
    /@media\(max-width:700px\)\{\.table-page-top\{display:flow-root\}\}/,
  );
});

test("only the narrow companion app cancels the duplicated Home Assistant toolbar", () => {
  const panel = new AlertManagerPanel();
  const styles = compactCss(panel._styles());

  assert.match(
    styles,
    /:host\(\[companion-app\]\[narrow\]\) #panel-shell\{margin-block-start:calc\(0px - var\(--header-height,56px\)\)\}/,
  );
  assert.doesNotMatch(styles, /@media\(max-width:870px\),\(max-height:500px\)/);
  assert.match(styles, /--ha-bottom-sheet-border-color:var\(--primary-color\)/);

  panel.narrow = true;
  assert.equal(panel.hasAttribute("narrow"), true);
  assert.equal(panel.hasAttribute("companion-app"), false);
});

test("narrow native table action rows stay gray on every table page", () => {
  const panel = new AlertManagerPanel();
  const selectors = [
    '[data-alert-table-page="overview"]',
    '[data-alert-table-page="history"]',
    "[data-rules-table-page]",
    "[data-coherence-table-page]",
  ];
  const pages = new Map(selectors.map((selector) => {
    const injectedStyles = [];
    const shadowRoot = {
      querySelector(query) {
        if (!query.startsWith("#")) return null;
        return injectedStyles.find((style) => style.id === query.slice(1)) ?? null;
      },
      append(style) {
        injectedStyles.push(style);
      },
    };
    return [selector, { shadowRoot, injectedStyles }];
  }));
  panel.shadowRoot.querySelector = (selector) => pages.get(selector) ?? null;

  panel._syncNarrowTableHeaderBackgrounds();
  panel._syncNarrowTableHeaderBackgrounds();

  for (const { injectedStyles } of pages.values()) {
    assert.equal(injectedStyles.length, 1);
    assert.equal(injectedStyles[0].tagName, "STYLE");
    assert.match(
      injectedStyles[0].textContent,
      /:host\(\[narrow\]\) \.narrow-header-row \{[\s\S]*background: var\(--primary-background-color\);/,
    );
    assert.match(
      injectedStyles[0].textContent,
      /border-bottom: 1px solid var\(--divider-color\);/,
    );
  }
});

test("runtime does not force focus before opening more info", () => {
  const panel = new AlertManagerPanel();
  assert.equal(panel._focusOverviewContentScroller, undefined);
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
