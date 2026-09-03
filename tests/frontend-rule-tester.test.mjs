import assert from "node:assert/strict";
import test from "node:test";

globalThis.HTMLElement = class {
  constructor() { this.isConnected = true; }
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
  localStorage: { getItem() { return null; }, setItem() {} },
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
const { renderRuleTestResult } = await import(
  "../frontend-src/components/rule-editor.js"
);

const draft = (changes = {}) => ({
  name: "Unsaved temperature",
  entity_ids: ["sensor.temperature"],
  enabled: true,
  source: "state",
  attribute: "",
  operator: "below",
  value: "19",
  duration: 600,
  message: "Temperature {{ value }}",
  condition_template: "",
  ...changes,
});

function formFor(rule, changes = {}) {
  const current = { ...rule, ...changes };
  const fields = new Map([
    ["name", { value: current.name }],
    ["source", { value: current.source }],
    ["operator", { value: current.operator }],
    ["value", { value: current.value }],
    ["duration", { value: String(current.duration) }],
  ]);
  return {
    elements: { namedItem() { return null; } },
    querySelector(selector) {
      const match = selector.match(/^\[data-field="([^"]+)"\]$/);
      if (match) return fields.get(match[1]) ?? null;
      if (selector === "#rule-update-message-when-active") return { checked: false };
      if (selector === "#rule-flapping-enabled") return { checked: false };
      return null;
    },
    querySelectorAll() { return []; },
    reportValidity() { return true; },
  };
}

test("visual editor places the native Test action opposite Save and result above Name", () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = draft();

  const markup = panel._renderRuleEditor();
  const resultPosition = markup.indexOf("data-rule-test-result");
  const namePosition = markup.indexOf('data-field="name"');
  const testPosition = markup.indexOf('data-action="test-rule"');
  const spacerPosition = markup.indexOf('class="action-spacer"');
  const savePosition = markup.indexOf('data-action="save-rule"');

  assert.ok(resultPosition >= 0 && resultPosition < namePosition);
  assert.ok(testPosition < spacerPosition && spacerPosition < savePosition);
  assert.match(markup, /<ha-button type="button" appearance="plain" data-action="test-rule"/);
  assert.doesNotMatch(markup, /<button/);

  panel._ruleEditorMode = "yaml";
  assert.doesNotMatch(panel._renderRuleEditor(), /data-action="test-rule"/);
});

test("the tester remains inside Home Assistant's native mobile bottom sheet", () => {
  customElements._items.set("ha-resizable-bottom-sheet", class {});
  const panel = new AlertManagerPanel();
  panel._narrow = true;
  panel._editingRule = draft();

  const markup = panel._renderRuleEditor();

  assert.match(markup, /^<ha-resizable-bottom-sheet/);
  assert.match(markup, /data-rule-test-result/);
  assert.match(markup, /data-action="test-rule"/);
  customElements._items.delete("ha-resizable-bottom-sheet");
});

test("test action sends the current unsaved draft and scrolls only the editor form", async () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = draft({
    id: "rule-1",
    value: "19",
    condition_template: "{{ false }}",
    message: "Saved {{ value }}",
  });
  const form = formFor(panel._editingRule, { value: "18.5" });
  const resultContainer = { innerHTML: "" };
  const button = {
    disabled: false,
    loading: false,
    toggleAttribute() {},
  };
  let scrollOptions = null;
  form.scrollTo = (options) => { scrollOptions = options; };
  panel.shadowRoot.querySelector = (selector) => {
    if (selector === "#rule-entity-ids") return { value: ["sensor.draft"] };
    if (selector === "#rule-condition-template") return { value: "{{ true }}" };
    if (selector === "#rule-message-template") return { value: "Draft {{ value }}" };
    if (selector === "[data-rule-test-result]") return resultContainer;
    if (selector === '[data-action="test-rule"]') return button;
    if (selector === "#rule-form") return form;
    return null;
  };
  let request = null;
  panel._api.testRule = async (rule, ruleId) => {
    request = { rule, ruleId };
    return {
      enabled: true,
      duration: 600,
      total: 1,
      matched_count: 1,
      not_matched_count: 0,
      indeterminate_count: 0,
      error_count: 0,
      results: [{
        entity_id: "sensor.temperature",
        name: "Temperature",
        state: "18.2",
        source: "state",
        operator: "below",
        comparison_value: "18.5",
        duration: 600,
        status: "match",
        value: "18.2",
        comparison_result: true,
        jinja_result: true,
        final_result: true,
      }],
    };
  };

  await panel._testRule(form);

  assert.equal(request.ruleId, "rule-1");
  assert.deepEqual(request.rule.entity_ids, ["sensor.draft"]);
  assert.equal(request.rule.value, "18.5");
  assert.equal(request.rule.condition_template, "{{ true }}");
  assert.equal(request.rule.message, "Draft {{ value }}");
  assert.deepEqual(scrollOptions, { top: 0, behavior: "smooth" });
  assert.match(resultContainer.innerHTML, /<ha-alert/);
  assert.match(resultContainer.innerHTML, /<ha-expansion-panel outlined/);
  assert.equal(panel._editingRule.value, "18.5");
});

test("multi-entity results stay compact and use Home Assistant components", () => {
  const markup = renderRuleTestResult({
    enabled: false,
    total: 3,
    matched_count: 2,
    not_matched_count: 1,
    indeterminate_count: 0,
    error_count: 0,
    results: [
      { entity_id: "sensor.one", status: "match", duration: 0, final_result: true },
      { entity_id: "sensor.two", status: "no_match", duration: 0, final_result: false },
      { entity_id: "sensor.three", status: "match", duration: 60, final_result: true },
    ],
  }, {
    t(key, values = {}) {
      return `${key} ${Object.values(values).join(" ")}`.trim();
    },
    formatDuration(value) { return `${value}s`; },
  });

  assert.equal((markup.match(/<ha-expansion-panel/g) ?? []).length, 3);
  assert.match(markup, /<ha-alert class="rule-test-summary"/);
  assert.match(markup, /<ha-icon icon="mdi:check-circle"/);
  assert.doesNotMatch(markup, /<ha-card/);
});

test("editing any functional field invalidates the previous result", () => {
  const panel = new AlertManagerPanel();
  panel._editingRule = draft();
  panel._ruleTestResult = { matched_count: 1 };
  const resultContainer = { innerHTML: "old" };
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-rule-test-result]" ? resultContainer : null
  );

  panel._handleRuleInput({
    target: {
      closest(selector) { return selector === "#rule-form" ? {} : null; },
    },
  });

  assert.equal(panel._ruleTestResult, null);
  assert.equal(resultContainer.innerHTML, "");
});
