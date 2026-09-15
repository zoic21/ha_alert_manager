import assert from "node:assert/strict";
import test from "node:test";
import { ruleToYaml } from "../frontend-src/utils/formatting.js";

import {
  captureRuleDraftFromForm,
  hydrateRuleEditor,
  hydrateRuleEditorControls,
  normalizeRuleDraft,
  moveSequenceStep,
  refreshRuleConditionSection,
  renderRuleEditor,
  renderRuleConditionSection,
  serializeRuleDraft,
  validateRuleDraft,
} from "../frontend-src/components/rule-editor.js";
import {
  buildRuleTableRows,
  hydrateRules,
  renderRules,
} from "../frontend-src/views/rules.js";

const t = (key, replacements = {}) => `${key}${replacements.index ? `:${replacements.index}` : ""}`;

const rule = (changes = {}) => ({
  id: "rule-1",
  name: "Temperature",
  entity_ids: ["sensor.temperature"],
  enabled: true,
  source: "value",
  attribute: "",
  operator: "above",
  value: "25",
  duration: 900,
  message: "",
  update_message_when_active: false,
  condition_template: "",
  ...changes,
});

test("rule draft normalization is pure and handles legacy sources", () => {
  const source = rule({ source: "variation", operator: "equals", value: ["2", "3"] });
  const before = structuredClone(source);
  const normalized = normalizeRuleDraft(source);

  assert.deepEqual(source, before);
  assert.notEqual(normalized, source);
  assert.notEqual(normalized.entity_ids, source.entity_ids);
  assert.equal(normalized.source, "value_variation");
  assert.equal(normalized.operator, "above");
  assert.equal(normalized.value, "2");
});

test("rules rendering consumes an explicit context without a panel instance", () => {
  const markup = renderRules({
    editorOpen: true,
    editor: "<aside>editor</aside>",
    editorWidth: 640,
    pageMessages: "<ha-alert>notice</ha-alert>",
    t: (key) => key === "rules.title" ? "<Rules>" : key,
    renderFacetFilter: (_kind, _facet, label, statuses) => (
      `<filters label="${label}">${statuses.map((item) => item.value).join(",")}</filters>`
    ),
  });

  assert.match(markup, /class="rules-layout has-editor"/);
  assert.match(markup, /--rule-editor-width:640px/);
  assert.match(markup, /&lt;Rules&gt;/);
  assert.match(markup, /<filters label="rules.status">active,inactive<\/filters>/);
  assert.match(markup, /<aside>editor<\/aside>/);
});

test("rule table rows are built without DOM or panel state", () => {
  const rows = buildRuleTableRows([
    rule(),
    rule({ id: "rule-2", name: "Humidity", enabled: false, duration: 60 }),
  ], {
    t: (key) => key,
    summarizeRule: (item) => `${item.operator}:${item.value}`,
    formatDuration: (duration) => `${duration}s`,
  });

  assert.deepEqual(rows.map((row) => row.enabledKey), ["active", "inactive"]);
  assert.equal(rows[0].condition, "above:25");
  assert.equal(rows[1].duration, "60s");
  assert.match(rows[1].search_index, /rules.status_inactive/);
});

const tablePage = () => ({
  listeners: {},
  listenerCounts: {},
  shadowRoot: { querySelector() { return null; } },
  addEventListener(name, callback) {
    this.listeners[name] = callback;
    this.listenerCounts[name] = (this.listenerCounts[name] ?? 0) + 1;
  },
  querySelectorAll() { return []; },
});

const hydrationContext = (changes = {}) => ({
  hass: {},
  narrow: false,
  tabs: [],
  state: {
    search: "",
    columnOrder: ["name", "entities", "condition", "duration", "enabled"],
    hiddenColumns: [],
    sortBy: "name",
    sortDirection: "asc",
  },
  sourceRows: [{ id: "rule-1" }],
  visibleRows: [{ id: "rule-1" }],
  selectedFilters: [],
  filterPaneOpen: false,
  t,
  renderNameCell: (row) => row.name,
  renderEntitiesCell: (row) => row.entities,
  renderToggleCell: (row) => row.enabled,
  onSearch() {},
  onClearFilter() {},
  onSortingChanged() {},
  onColumnsChanged() {},
  onRowClick() {},
  onFilterChanged() {},
  ...changes,
});

test("rules hydration is idempotent and events use the latest context", () => {
  const table = tablePage();
  const root = { querySelector: () => table };
  const searches = [];

  hydrateRules(root, hydrationContext({ onSearch: () => searches.push("old") }));
  hydrateRules(root, hydrationContext({
    narrow: true,
    visibleRows: [{ id: "rule-2" }],
    onSearch: (value) => searches.push(value),
  }));
  table.listeners["search-changed"]({ detail: { value: "humidity" } });

  assert.equal(table.listenerCounts["search-changed"], 1);
  assert.equal(table.listenerCounts["row-click"], 1);
  assert.equal(table.narrow, true);
  assert.deepEqual(table.data, [{ id: "rule-2" }]);
  assert.deepEqual(searches, ["humidity"]);
});

test("the edited rule uses the native table row highlight", () => {
  const selections = [];
  const nativeTable = {
    style: { setProperty() {} },
    select(ids, clear) { selections.push({ ids, clear }); },
  };
  const table = tablePage();
  table.shadowRoot.querySelector = () => nativeTable;
  const root = { querySelector: () => table };

  hydrateRules(root, hydrationContext({ editingRuleId: "rule-1" }));
  hydrateRules(root, hydrationContext({ editingRuleId: null }));

  assert.deepEqual(selections, [
    { ids: ["rule-1"], clear: true },
    { ids: [], clear: true },
  ]);
});

test("rule editor rendering is pure and receives all dependencies explicitly", () => {
  const draft = normalizeRuleDraft(rule({ operator: "between", value: ["10", "20"] }));
  const before = structuredClone(draft);
  const markup = renderRuleEditor({
    rule: draft,
    mode: "visual",
    busy: false,
    editorError: null,
    yamlError: null,
    t,
    duplicateLabel: "Duplicate",
    renderTextField: (_name, label, value) => `<field label="${label}">${value}</field>`,
    renderNumberField: (_name, label, value) => `<number label="${label}">${value}</number>`,
  });

  assert.deepEqual(draft, before);
  assert.match(markup, /<ha-selector id="rule-entity-ids">/);
  assert.match(markup, /data-field="lower-bound"/);
  assert.match(markup, /data-field="upper-bound"/);
  assert.match(markup, /Duplicate/);
});

test("condition updates replace only their section and preserve the editor scroller", () => {
  const form = { scrollTop: 428 };
  const section = { outerHTML: "" };
  let editorRefreshes = 0;
  let hydrations = 0;
  const panel = {
    _editingRule: rule({ source: "value_variation", operator: "between" }),
    _t: t,
    _refreshRuleEditor() { editorRefreshes += 1; },
    _hydrateRuleEditorControls() { hydrations += 1; },
    shadowRoot: {
      querySelector(selector) {
        if (selector === "#rule-form") return form;
        if (selector === "[data-rule-condition-section]") return section;
        return null;
      },
    },
  };

  refreshRuleConditionSection.call(panel);

  assert.equal(editorRefreshes, 0);
  assert.equal(hydrations, 1);
  assert.equal(form.scrollTop, 428);
  assert.match(section.outerHTML, /data-rule-condition-section/);
  assert.match(section.outerHTML, /data-field="lower-bound"/);
});

test("structural source and operator changes refresh only the condition section", () => {
  let onSourceChanged;
  let onOperatorChanged;
  let conditionRefreshes = 0;
  let editorRefreshes = 0;
  const panel = {
    _editingRule: rule(),
    _ruleEditorMode: "visual",
    _t: t,
    _ruleAttributeOptions: () => [],
    _configureSelect(id, _options, _value, onChange) {
      if (id === "rule-source") onSourceChanged = onChange;
      if (id === "rule-operator") onOperatorChanged = onChange;
    },
    _configureSelector() {},
    _handleSelected() {},
    _captureRuleDraft() { return this._editingRule; },
    _ruleValueList: (value) => Array.isArray(value) ? value : [value ?? ""],
    _refreshRuleConditionSection() { conditionRefreshes += 1; },
    _refreshRuleEditor() { editorRefreshes += 1; },
    shadowRoot: { querySelector() { return null; } },
  };

  hydrateRuleEditorControls.call(panel);
  onSourceChanged("value_variation");
  onOperatorChanged("between");

  assert.equal(conditionRefreshes, 2);
  assert.equal(editorRefreshes, 0);
});

test("rule editor uses the native resizable bottom sheet on mobile", () => {
  const markup = renderRuleEditor({
    rule: normalizeRuleDraft(rule()),
    mode: "visual",
    busy: false,
    editorError: null,
    yamlError: null,
    t,
    duplicateLabel: "Duplicate",
    useBottomSheet: true,
    renderTextField: () => "<ha-input></ha-input>",
    renderNumberField: () => "<ha-input></ha-input>",
  });

  assert.match(markup, /^<ha-resizable-bottom-sheet/);
  assert.match(markup, /data-close-action="cancel-rule"/);
  assert.doesNotMatch(markup, /side-drawer-backdrop/);
});

test("rule draft capture, serialization and validation are independently testable", () => {
  const fields = new Map([
    ["name", { value: "  Presence  " }],
    ["source", { value: "value" }],
    ["operator", { value: "contains" }],
    ["duration", { value: "30" }],
  ]);
  const form = {
    elements: { namedItem() { return null; } },
    querySelector(selector) {
      const fieldMatch = selector.match(/^\[data-field="([^"]+)"\]$/);
      if (fieldMatch) return fields.get(fieldMatch[1]) ?? null;
      return null;
    },
    querySelectorAll(selector) {
      return selector === "[data-rule-value-index]"
        ? [{ value: " on " }, { value: " home " }]
        : [];
    },
  };
  const draft = captureRuleDraftFromForm(form, rule({
    entity_ids: ["binary_sensor.presence"],
    message: "  Present  ",
  }));
  const serialized = serializeRuleDraft(draft);

  assert.deepEqual(serialized.value, ["on", "home"]);
  assert.equal(serialized.name, "Presence");
  assert.equal(serialized.message, "Present");
  assert.deepEqual(validateRuleDraft(serialized), { valid: true, errorKey: null });
  assert.deepEqual(validateRuleDraft({ source: "jinja", condition_template: "" }), {
    valid: false,
    errorKey: "rules.condition_template_required",
  });
});

test("rule editor hydration configures Home Assistant controls through callbacks", () => {
  const calls = [];
  const closeButton = {};
  hydrateRuleEditor({ querySelector: () => closeButton }, {
    mode: "visual",
    draft: rule(),
    closeLabel: "Close",
    sourceOptions: [{ value: "state", label: "State" }],
    operatorOptions: [{ value: "above", label: "Above" }],
    attributeOptions: ["temperature"],
    configureSelect: (...args) => calls.push(["select", ...args.slice(0, 3)]),
    configureSelector: (...args) => calls.push(["selector", ...args.slice(0, 3)]),
    onSourceChanged() {},
    onOperatorChanged() {},
    onEntitiesChanged() {},
    onAttributeChanged() {},
    onConditionTemplateChanged() {},
    onMessageChanged() {},
  });

  assert.equal(closeButton.label, "Close");
  assert.deepEqual(calls.map((call) => call[1]), [
    "rule-source",
    "rule-operator",
    "rule-entity-ids",
    "rule-label-ids",
    "rule-attribute",
    "rule-condition-template",
    "rule-message-template",
  ]);
});

test("rule labels survive drafts, duplication, serialization and YAML", () => {
  const original = { ...rule(), label_ids: ["cold", "kitchen"] };
  const draft = normalizeRuleDraft(original);
  draft.label_ids.push("garage");
  assert.deepEqual(original.label_ids, ["cold", "kitchen"]);
  const captured = captureRuleDraftFromForm({ querySelector: () => null }, draft);
  const serialized = serializeRuleDraft(captured);
  assert.deepEqual(serialized.label_ids, ["cold", "kitchen", "garage"]);
  assert.match(ruleToYaml(serialized), /label_ids: \["cold","kitchen","garage"\]/);
  const calls = [];
  let changed;
  hydrateRuleEditor({ querySelector: () => null }, {
    mode: "visual", draft,
    configureSelect() {},
    configureSelector: (...args) => calls.push(args),
    onLabelsChanged: (value) => { changed = value; },
  });
  const selector = calls.find(([id]) => id === "rule-label-ids");
  assert.deepEqual(selector[1], { label: { multiple: true } });
  assert.deepEqual(selector[2], serialized.label_ids);
  selector[3]([]);
  assert.deepEqual(changed, []);
});

test("unified drafts migrate legacy state targets without retaining stale attributes", () => {
  for (const [legacy, source] of [["state", "value"], ["variation", "value_variation"], ["state_variation", "value_variation"], ["transition", "value_transition"]]) {
    const migrated = normalizeRuleDraft(rule({ source: legacy, attribute: "stale" }));
    assert.equal(migrated.source, source);
    assert.equal(migrated.attribute, null);
    assert.deepEqual(normalizeRuleDraft(migrated), migrated);
  }
  for (const [legacy, source] of [["attribute", "value"], ["attribute_variation", "value_variation"], ["attribute_transition", "value_transition"]]) {
    const migrated = normalizeRuleDraft(rule({ source: legacy, attribute: "metrics.power" }));
    assert.equal(migrated.source, source);
    assert.equal(migrated.attribute, "metrics.power");
    assert.equal(normalizeRuleDraft(rule({ source: legacy, attribute: "" })).source, legacy);
  }
});

test("optional attributes serialize consistently for every unified operation", () => {
  for (const source of ["value", "value_variation", "value_transition"]) {
    for (const attribute of [undefined, "", "  ", "metrics.power"]) {
      const draft = normalizeRuleDraft(rule({ source, attribute }));
      const serialized = serializeRuleDraft(draft);
      assert.equal(serialized.source, source);
      assert.equal(serialized.attribute, attribute?.trim() || null);
    }
  }
});

test("transition resolution mode survives form capture, payload and YAML", () => {
  const current = normalizeRuleDraft({ ...rule(), source: "value_transition", from_value: "A", to_value: "B", auto_resolve: 120 });
  const form = { querySelector: (selector) => selector === '[data-field="resolve_mode"]' ? { value: "state" } : null };
  const draft = captureRuleDraftFromForm(form, current);
  assert.equal(draft.resolve_mode, "state");
  assert.equal(draft.auto_resolve, 120);
  assert.equal(serializeRuleDraft(draft).resolve_mode, "state");
  assert.match(ruleToYaml(draft), /resolve_mode: "state"/);
  assert.equal(serializeRuleDraft(current).resolve_mode, "duration");
  assert.equal("resolve_mode" in serializeRuleDraft({ ...draft, source: "value" }), false);
});

test("transition resolution selector refreshes its duration control and keeps the draft", () => {
  let changeMode;
  let refreshes = 0;
  const panel = {
    _editingRule: { ...rule(), source: "value_transition", resolve_mode: "duration", auto_resolve: 120 },
    _ruleEditorMode: "visual", _t: t, _ruleAttributeOptions: () => [],
    _configureSelect(id, options, value, callback) {
      if (id === "rule-resolve-mode") {
        assert.deepEqual(options.map((option) => option.value), ["duration", "state", "condition"]);
        assert.equal(value, "duration");
        changeMode = callback;
      }
    },
    _configureSelector() {}, _handleSelected() {},
    _captureRuleDraft() {},
    _refreshRuleConditionSection() { refreshes += 1; },
    shadowRoot: { querySelector() { return null; } },
  };
  hydrateRuleEditorControls.call(panel);
  changeMode("state");
  assert.equal(panel._editingRule.resolve_mode, "state");
  assert.equal(panel._editingRule.auto_resolve, 120);
  assert.equal(panel._ruleDirty, true);
  assert.equal(refreshes, 1);
});

test("state resolution hides only the expiration duration", () => {
  const context = {
    rule: { ...rule(), source: "value_transition", from_value: "A", to_value: "B" }, t,
    renderTextField: (name) => `<ha-textfield name="${name}"></ha-textfield>`,
    renderNumberField: (name) => `<ha-selector data-field="${name}"></ha-selector>`,
  };
  const timed = renderRuleConditionSection(context);
  const maintained = renderRuleConditionSection({ ...context, rule: { ...context.rule, resolve_mode: "state" } });
  assert.match(timed, /data-field="auto_resolve"/);
  assert.doesNotMatch(maintained, /data-field="auto_resolve"/);
  assert.match(maintained, /id="rule-resolve-mode"/);
  assert.match(maintained, /name="to_value"/);
});

test("sequence drafts preserve typed values and YAML structure without mutating their source", () => {
  const original = rule({ source: "value_sequence", attribute: "metrics.power", steps: [
    { operator: "above", value: 100, duration_mode: "at_least", duration: 300 },
    { operator: "between", value: [0, 10], duration_mode: "between", duration: 120, duration_max: 300 },
  ], sequence_timeout: 21600, auto_resolve: 600 });
  const before = structuredClone(original);
  const draft = normalizeRuleDraft(original);
  const serialized = serializeRuleDraft(draft);
  assert.deepEqual(serialized.steps, original.steps);
  assert.equal(serialized.duration, 0);
  assert.equal(serialized.attribute, "metrics.power");
  assert.equal(serialized.condition_template, null);
  const yaml = ruleToYaml(serialized);
  assert.match(yaml, /steps:\n  - operator: "above"\n    value: 100/);
  assert.match(yaml, /value: \[0,10\]/);
  assert.match(yaml, /duration_max: 300/);
  assert.match(yaml, /sequence_timeout: 21600/);
  assert.doesNotMatch(yaml, /from_value:|to_value:/);
  draft.steps[1].value[0] = 5;
  assert.deepEqual(original, before);
  assert.equal("steps" in serializeRuleDraft({ ...draft, source: "value" }), false);
});

test("sequence modes rebuild only the condition section and retain neighboring step values", () => {
  const changes = new Map();
  let refreshes = 0;
  const panel = {
    _editingRule: normalizeRuleDraft(rule({ source: "value_sequence", steps: [
      { operator: "above", value: 100, duration: 300 },
      { operator: "below", value: 10, duration: 120 },
    ] })),
    _ruleEditorMode: "visual", _t: t, _ruleAttributeOptions: () => [],
    _configureSelect(id, options, value, callback) { changes.set(id, callback); },
    _configureSelector() {}, _handleSelected() {}, _clearRuleTestResult() {},
    _captureRuleDraft() {}, _refreshRuleConditionSection() { refreshes++; },
    shadowRoot: { querySelector() { return null; } },
  };
  hydrateRuleEditorControls.call(panel);
  changes.get("sequence-1-mode")("between");
  assert.equal(panel._editingRule.steps[1].duration_mode, "between");
  assert.equal(panel._editingRule.steps[1].duration, 120);
  assert.equal(panel._editingRule.steps[0].value, 100);
  const context = {
    rule: panel._editingRule, t, renderTextField: () => "",
    renderNumberField: (name) => `<ha-selector data-field="${name}"></ha-selector>`,
  };
  assert.match(renderRuleConditionSection(context), /sequence-1-duration_max/);
  changes.get("sequence-1-mode")("at_least");
  const html = renderRuleConditionSection(context);
  assert.doesNotMatch(html, /sequence-1-duration_max/);
  assert.match(html, /sequence-1-duration/);
  assert.doesNotMatch(html, /id="rule-condition-template"|name="from_value"/);
  assert.equal(refreshes, 2);
});

test("sequence form capture scopes comparison and duration inputs to their own step", () => {
  const original = normalizeRuleDraft(rule({ source: "value_sequence", steps: [
    { operator: "above", value: 100, duration: 300, duration_mode: "at_least" },
    { operator: "between", value: [0, 10], duration_mode: "between", duration: 120, duration_max: 300 },
  ] }));
  function row(index, fields) {
    return {
      dataset: { sequenceStep: String(index) },
      querySelector(selector) {
        const key = /data-field="([^"]+)"/.exec(selector)?.[1];
        return fields[key] ?? null;
      },
      querySelectorAll: () => [],
    };
  }
  const duration = (minutes) => ({ dataset: { durationValue: "0" }, value: { hours: 0, minutes, seconds: 0 } });
  const rows = [
    row(0, { operator: { value: "above" }, value: { value: "100" }, "sequence-0-duration": duration(5) }),
    row(1, { operator: { value: "between" }, "lower-bound": { value: "0" }, "upper-bound": { value: "10" }, "sequence-1-duration": duration(2), "sequence-1-duration_max": duration(6) }),
  ];
  const form = { querySelector: () => null, querySelectorAll: (selector) => selector === "[data-sequence-step]" ? rows : [] };
  const captured = captureRuleDraftFromForm(form, original);
  assert.equal(captured.steps[0].value, 100);
  assert.equal(captured.steps[0].duration, 300);
  assert.deepEqual(captured.steps[1].value, [0, 10]);
  assert.equal(captured.steps[1].duration_max, 360);
  assert.equal(original.steps[1].duration_max, 300);
});

test("sequence reordering and removal retain the entire step including durations", async () => {
  const { handleRulesAction } = await import("../frontend-src/views/rules.js");
  const steps = [
    { operator: "above", value: 100, duration: 300 },
    { operator: "below", value: 10, duration_mode: "between", duration: 120, duration_max: 300 },
    { operator: "equals", value: ["idle", "off"], duration: 0 },
  ];
  const panel = {
    _editingRule: { steps: structuredClone(steps) },
    _captureRuleDraft() {}, _clearRuleTestResult() {}, _refreshRuleConditionSection() {},
    shadowRoot: { querySelector: () => null },
  };
  moveSequenceStep(panel, 1, 0);
  assert.deepEqual(panel._editingRule.steps, [steps[1], steps[0], steps[2]]);
  await handleRulesAction.call(panel, "remove-sequence-step", { dataset: { index: "1" } });
  assert.deepEqual(panel._editingRule.steps, [steps[1], steps[2]]);
  await handleRulesAction.call(panel, "remove-sequence-step", { dataset: { index: "0" } });
  assert.equal(panel._editingRule.steps.length, 2);
  await handleRulesAction.call(panel, "add-sequence-step", { dataset: {} });
  assert.equal(panel._editingRule.steps.length, 3);
  assert.equal(panel._ruleDirty, true);
});

test("choosing Sequence in a new ordinary rule immediately creates two editable steps", () => {
  let chooseSource;
  const panel = {
    _editingRule: rule(), _ruleEditorMode: "visual", _t: t,
    _ruleAttributeOptions: () => [], _configureSelector() {},
    _configureSelect(id, options, value, callback) { if (id === "rule-source") chooseSource = callback; },
    _captureRuleDraft() { this._editingRule = captureRuleDraftFromForm({ querySelector: () => null, querySelectorAll: () => [] }, this._editingRule); },
    _refreshRuleEditor() {}, shadowRoot: { querySelector: () => null },
  };
  hydrateRuleEditorControls.call(panel);
  chooseSource("value_sequence");
  assert.equal(panel._editingRule.steps.length, 2);
  assert.notEqual(panel._editingRule.steps[0], panel._editingRule.steps[1]);
});

test("sequence and transition resolution fields survive mode changes and YAML", () => {
  for (const source of ["value_sequence", "value_transition"]) {
    const current = normalizeRuleDraft(rule({ source, resolve_mode: "condition", auto_resolve: 240, resolve_condition: { operator: "between", value: [10, 20] } }));
    const row = { querySelector: (selector) => ({ '[data-field="operator"]': { value: "between" }, '[data-field="lower-bound"]': { value: "12" }, '[data-field="upper-bound"]': { value: "30" } })[selector] ?? null, querySelectorAll: () => [] };
    const form = { querySelector: (selector) => selector === "[data-resolution-condition]" ? row : null, querySelectorAll: () => [] };
    let captured = captureRuleDraftFromForm(form, current);
    assert.deepEqual(captured.resolve_condition, { operator: "between", value: ["12", "30"] });
    const context = { t, renderTextField: () => "", renderNumberField: (name) => `<ha-selector data-field="${name}"></ha-selector>` };
    for (const mode of ["state", "duration", "condition"]) {
      captured = captureRuleDraftFromForm({ querySelector: () => null, querySelectorAll: () => [] }, { ...captured, resolve_mode: mode });
      const html = renderRuleConditionSection({ ...context, rule: captured });
      assert.equal(html.includes('data-field="auto_resolve"'), mode === "duration");
      assert.equal(html.includes("data-resolution-condition"), mode === "condition");
      assert.equal((html.match(/id="rule-resolve-mode"/g) ?? []).length, 1);
      assert.equal(captured.auto_resolve, 240);
      const payload = serializeRuleDraft(captured);
      assert.equal(payload.resolve_mode, mode);
      assert.equal("resolve_condition" in payload, mode === "condition");
      if (mode === "condition") {
        assert.deepEqual(payload.resolve_condition, { operator: "between", value: ["12", "30"] });
        assert.match(ruleToYaml(payload), /resolve_condition: \{"operator":"between","value":\["12","30"\]\}/);
      }
    }
    assert.equal("resolve_condition" in serializeRuleDraft({ ...captured, source: "value" }), false);
  }
});

test("sequence expansion captures edits, keeps its state and never serializes it", () => {
  const listeners = new Map();
  const summary = { textContent: "" };
  const expansion = {
    querySelectorAll: () => [], querySelector: () => summary,
    addEventListener: (name, handler) => listeners.set(name, handler),
    removeEventListener: (name) => listeners.delete(name),
  };
  const panel = {
    _editingRule: normalizeRuleDraft(rule({ source: "value_sequence", steps: [{ operator: "above", value: 100, duration: 300 }, { operator: "below", value: 10, duration: 120 }] })),
    _ruleEditorMode: "visual", _t: t, _ruleAttributeOptions: () => [],
    _configureSelect() {}, _configureSelector() {}, _handleSelected() {},
    _captureRuleDraft() { this._editingRule.steps[0].value = 200; },
    shadowRoot: { querySelector: (selector) => selector === '[data-sequence-step="0"]' ? expansion : null },
  };
  hydrateRuleEditorControls.call(panel);
  hydrateRuleEditorControls.call(panel);
  assert.equal(listeners.size, 1);
  listeners.get("expanded-changed")({ target: expansion, detail: { expanded: true } });
  assert.equal(panel._editingRule.steps[0]._expanded, true);
  listeners.get("expanded-changed")({ target: expansion, detail: { expanded: false } });
  assert.equal(panel._editingRule.steps[0]._expanded, false);
  assert.match(summary.textContent, /200/);
  assert.match(summary.textContent, /duration.minutes/);
  const html = renderRuleConditionSection({ rule: panel._editingRule, t, renderTextField: () => "", renderNumberField: () => "" });
  assert.match(html, /<ha-expansion-panel[^>]*data-sequence-step="0"/);
  assert.doesNotMatch(html, /data-sequence-step="0"[^>]* expanded/);
  assert.match(html, /slot="icons" class="sequence-step-actions"/);
  assert.equal("_expanded" in serializeRuleDraft(panel._editingRule).steps[0], false);
  assert.doesNotMatch(ruleToYaml(panel._editingRule), /_expanded/);
});

test("resolution comparison value actions do not change sequence steps", async () => {
  const { handleRulesAction } = await import("../frontend-src/views/rules.js");
  const panel = {
    _editingRule: { resolve_condition: { operator: "equals", value: ["done"] }, steps: [{ value: 100 }] },
    _captureRuleDraft() {}, _clearRuleTestResult() {}, _refreshRuleConditionSection() {},
    _ruleValueList: (value) => [...value], shadowRoot: { querySelector: () => null },
  };
  const button = { closest: (selector) => selector === "[data-resolution-condition]" ? {} : null, dataset: { index: "0" } };
  await handleRulesAction.call(panel, "add-rule-value", button);
  assert.deepEqual(panel._editingRule.resolve_condition.value, ["done", ""]);
  await handleRulesAction.call(panel, "remove-rule-value", button);
  assert.deepEqual(panel._editingRule.resolve_condition.value, [""]);
  assert.deepEqual(panel._editingRule.steps, [{ value: 100 }]);
});


test("sequence step toggle is saved in visual and YAML drafts without losing its fields", () => {
  const draft = normalizeRuleDraft(rule({ source: "value_sequence", steps: [
    { operator: "above", value: 100, duration: 30, enabled: false },
    { operator: "below", value: 10, duration: 20 },
  ] }));
  const captured = captureRuleDraftFromForm({ querySelector: () => null, querySelectorAll: () => [] }, draft);
  assert.equal(serializeRuleDraft(captured).steps[0].enabled, false);
  assert.match(ruleToYaml(captured), /enabled: false/);
  const html = renderRuleConditionSection({ rule: captured, t, renderTextField: () => "", renderNumberField: () => "" });
  assert.match(html, /<ha-sortable[^>]*handle-selector=".sequence-step-reorder"/);
  assert.match(html, /class="sequence-step sequence-step-disabled"/);
  assert.match(html, /sequence_disabled/);
  assert.match(html, /data-sequence-enabled/);
  assert.doesNotMatch(html, /move-sequence-step|mdi:chevron-up|mdi:chevron-down/);
});

test("native sequence sorting captures edits, supports nonadjacent moves and binds once", async () => {
  const { hydrateConfigurationSorting } = await import("../frontend-src/components/configuration-drawer.js");
  const previous = globalThis.customElements;
  globalThis.customElements = { get: () => true };
  try {
    const listeners = [];
    const sortable = { isConnected: true, addEventListener: (name, cb) => listeners.push(cb) };
    const panel = {
      _editingRule: { steps: [{ value: 1 }, { value: 2, enabled: false }, { value: 3, duration: 30 }] },
      _captureRuleDraft() { this._editingRule.steps = this._editingRule.steps.map(step => ({ ...step })); },
      _clearRuleTestResult() {}, _refreshRuleConditionSection() {},
      shadowRoot: { querySelector: selector => selector === "#sort" ? sortable : null },
    };
    const hydrate = () => hydrateConfigurationSorting(panel, { selector: "#sort", handleSelector: ".handle", count: 3, move: (a, b) => moveSequenceStep(panel, a, b) });
    hydrate(); hydrate();
    assert.equal(listeners.length, 1);
    listeners[0]({ stopPropagation() {}, detail: { oldIndex: 2, newIndex: 0 } });
    await new Promise(resolve => queueMicrotask(resolve));
    assert.deepEqual(panel._editingRule.steps.map(s => s.value), [3, 1, 2]);
    assert.equal(panel._editingRule.steps[0].duration, 30);
    sortable.onkeydown({ key: "Home", target: { closest: () => ({ dataset: { index: "2" } }) }, preventDefault() {}, stopPropagation() {} });
    assert.equal(panel._editingRule.steps[0].enabled, false);
    panel._busy = true;
    moveSequenceStep(panel, 0, 2);
    assert.equal(panel._editingRule.steps[0].enabled, false);
  } finally { globalThis.customElements = previous; }
});

test("sequence switches update only their step and preserve collapsed state", () => {
  const toggle = { checked: true };
  const expansion = { querySelector: selector => selector === "[data-sequence-enabled]" ? toggle : null };
  const panel = {
    _editingRule: normalizeRuleDraft(rule({ source: "value_sequence", steps: [
      { operator: "above", value: 100, duration: 30, _expanded: false },
      { operator: "below", value: 10, duration: 20 },
    ] })),
    _ruleEditorMode: "visual", _t: t, _ruleAttributeOptions: () => [],
    _configureSelect() {}, _configureSelector() {}, _handleSelected() {},
    _captureRuleDraft() {}, _clearRuleTestResult() {}, _refreshRuleConditionSection() {},
    shadowRoot: { querySelector: selector => selector === '[data-sequence-step="0"]' ? expansion : null },
  };
  hydrateRuleEditorControls.call(panel);
  toggle.checked = false;
  toggle.onchange({ stopPropagation() {} });
  assert.equal(panel._editingRule.steps[0].enabled, false);
  assert.equal(panel._editingRule.steps[0]._expanded, false);
  assert.equal(panel._editingRule.steps[0].duration, 30);
  assert.notEqual(panel._editingRule.steps[1].enabled, false);
  assert.equal(panel._ruleDirty, true);
  toggle.checked = true;
  toggle.onchange({ stopPropagation() {} });
  assert.equal(panel._editingRule.steps[0].enabled, true);
});
