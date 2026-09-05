import assert from "node:assert/strict";
import test from "node:test";
import { ruleToYaml } from "../frontend-src/utils/formatting.js";

import {
  captureRuleDraftFromForm,
  hydrateRuleEditor,
  hydrateRuleEditorControls,
  normalizeRuleDraft,
  refreshRuleConditionSection,
  renderRuleEditor,
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
  source: "state",
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
  assert.equal(normalized.source, "state_variation");
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
    _editingRule: rule({ source: "state_variation", operator: "between" }),
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
  onSourceChanged("state_variation");
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
    ["source", { value: "state" }],
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
