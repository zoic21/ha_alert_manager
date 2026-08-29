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
  name: "Range rule",
  entity_ids: ["sensor.temperature"],
  enabled: true,
  source: "state",
  attribute: "",
  operator: "between",
  value: ["30", "20"],
  duration: 60,
  message: "",
  condition_template: "",
});

const rangeForm = () => {
  const fields = new Map([
    ["name", { value: "Range rule" }],
    ["source", { value: "state" }],
    ["operator", { value: "between" }],
    ["lower-bound", { value: "30" }],
    ["upper-bound", { value: "20" }],
    ["duration", { value: "60" }],
  ]);
  return {
    elements: { namedItem() { return null; } },
    querySelector(selector) {
      const match = selector.match(/^\[data-field="([^"]+)"\]$/);
      return match ? fields.get(match[1]) ?? null : null;
    },
    querySelectorAll() { return []; },
  };
};

test("rule validation errors are rendered inside the sticky editor actions", () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = rule();
  panel._ruleEditorError = "La borne inférieure doit être inférieure ou égale à la borne supérieure.";

  const markup = panel._renderRuleEditor();
  const styles = panel._styles();

  assert.match(
    markup,
    /<div class="actions rule-editor-actions"><ha-alert class="rule-editor-error" alert-type="error" role="alert">La borne inférieure/,
  );
  assert.match(styles, /\.rule-editor-actions\{flex-wrap:wrap\}/);
  assert.match(styles, /\.rule-editor-error\{flex:1 0 100%;width:100%;margin:0 0 4px\}/);
  assert.match(styles, /\.rule-editor-actions\{position:sticky;bottom:0/);
});

test("a rejected visual rule save moves the translated error from the page notice into the drawer", async () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = rule();
  panel._translations[
    "component.alert_manager.config_panel.errors.range_bounds_order"
  ] = "La borne inférieure doit être inférieure ou égale à la borne supérieure.";
  panel._hass = {
    async callWS() {
      throw {
        code: "invalid_format",
        message: "Range lower bound must not exceed upper bound",
      };
    },
  };
  panel._render = () => {};
  let refreshCount = 0;
  panel._refreshRuleEditor = () => { refreshCount += 1; };

  await panel._saveRule(rangeForm());

  assert.equal(
    panel._ruleEditorError,
    "La borne inférieure doit être inférieure ou égale à la borne supérieure.",
  );
  assert.equal(panel._notice, null);
  assert.equal(refreshCount, 1);
  assert.equal(panel._editingRule.value[0], "30");
  assert.equal(panel._editingRule.value[1], "20");
});

test("editing the visual rule clears a stale inline validation error", () => {
  const panel = new AlertManagerPanel();
  let removed = 0;
  panel._ruleEditorError = "Old validation error";
  panel.shadowRoot.querySelector = (selector) => (
    selector === ".rule-editor-error"
      ? { remove() { removed += 1; } }
      : null
  );

  panel._handleRuleInput({
    target: {
      closest(selector) {
        return selector === "#rule-form" ? {} : null;
      },
    },
  });

  assert.equal(panel._ruleEditorError, null);
  assert.equal(removed, 1);
  assert.equal(panel._ruleDirty, true);
});
