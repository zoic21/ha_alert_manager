import assert from "node:assert/strict";
import test from "node:test";
import { renderManagedBlueprint, handleManagedBlueprintAction, hydrateManagedBlueprint } from "../frontend-src/components/managed-blueprints.js";
import { refreshManagedBlueprints } from "../frontend-src/api/alert-manager-api.js";
import { nativeRuleNameCell, replaceRule } from "../frontend-src/views/rules.js";

const rule = { id: "r", name: "CPU", entity_ids: ["sensor.cpu"], blueprint: { id: "cpu", version: 1, managed: true, excluded_entities: ["sensor.missing"] } };
const proposal = { rule_id: "r", added: ["sensor.new"], removed: [], discovered: ["sensor.cpu", "sensor.new"], update_available: true, candidate: { entity_ids: ["sensor.cpu", "sensor.new"] }, token: "fresh" };
const t = (key) => key;

test("managed review escapes data and exposes explicit membership decisions", () => {
  const html = renderManagedBlueprint({ rule: { ...rule, blueprint: { ...rule.blueprint, id: "cpu" } }, proposal, review: { proposal }, t });
  assert.match(html, /data-managed-entity="sensor.new"/);
  assert.match(html, /data-managed-exclusion="sensor.missing"/);
  assert.match(html, /data-action="apply-blueprint"/);
  assert.match(html, /ha-alert/);
  assert.equal(renderManagedBlueprint({ rule: { ...rule, blueprint: { managed: false } }, t }), "");
  assert.doesNotMatch(renderManagedBlueprint({ rule, t }), /ha-alert/);
});

for (const [id, escaped] of [
  ["<script>", "&lt;script&gt;"],
  ["<SCRIPT>", "&lt;SCRIPT&gt;"],
  ["<ScRiPt>", "&lt;ScRiPt&gt;"],
  ['<SCRIPT src="test.js">', "&lt;SCRIPT src=&quot;test.js&quot;&gt;"],
]) {
  test(`managed review escapes blueprint identifiers: ${id}`, () => {
    const html = renderManagedBlueprint({
      rule: { ...rule, blueprint: { ...rule.blueprint, id } },
      proposal,
      review: { proposal },
      t: (key, replacements) => key === "managed.source" ? replacements.id : key,
    });
    assert.ok(html.includes(`<strong>${escaped}</strong>`));
    assert.doesNotMatch(html, /<script\b/i);
  });
}

test("background reconciliation yields, coalesces and leaves the table usable", async () => {
  let finish;
  let calls = 0;
  let updates = 0;
  const panel = {
    _config: { rules: [rule] }, _activeTab: "rules", isConnected: true,
    _api: { call: () => { calls++; return new Promise((resolve) => { finish = resolve; }); } },
    _refreshRulesData: () => { updates++; },
  };
  const first = refreshManagedBlueprints(panel);
  const second = refreshManagedBlueprints(panel);
  assert.equal(calls, 0);
  assert.equal(panel._busy, undefined);
  await new Promise((resolve) => setTimeout(resolve, 1));
  assert.equal(calls, 1);
  finish([proposal]);
  await Promise.all([first, second]);
  assert.equal(updates, 1);
  assert.equal(panel._managedBlueprints.r.token, "fresh");
});

test("late comparisons cannot update a disconnected panel or edited rules", async () => {
  for (const invalidate of [
    (panel) => { panel.isConnected = false; },
    (panel) => { panel._config.rules = []; },
  ]) {
    let finish;
    const panel = {
      _config: { rules: [rule] }, _activeTab: "rules", isConnected: true,
      _api: { call: () => new Promise((resolve) => { finish = resolve; }) },
      _refreshRulesData: () => assert.fail("stale result rendered"),
    };
    const request = refreshManagedBlueprints(panel);
    await new Promise((resolve) => setTimeout(resolve, 1));
    invalidate(panel);
    finish([proposal]);
    await request;
    assert.deepEqual(panel._managedBlueprints, {});
  }
});

test("accepted review sends only selected scope and preserved exclusions", async () => {
  const previous = globalThis.window;
  globalThis.window = { confirm: () => true };
  try {
    let sent;
    const panel = {
      _editingRule: rule, _t: t,
      _blueprintReview: { proposal, selected: new Set(["sensor.cpu"]), keptExclusions: new Set(["sensor.missing"]) },
      _call: async (message) => { sent = message; return { ...rule }; },
      _replaceRule: () => {}, _refreshRuleEditor: () => {}, _refreshTabData: () => {},
    };
    await handleManagedBlueprintAction(panel, "apply-blueprint");
    assert.deepEqual(sent.entity_ids, ["sensor.cpu"]);
    assert.deepEqual(sent.excluded_entities, ["sensor.missing", "sensor.new"]);
    assert.equal(sent.token, "fresh");
    assert.equal(panel._blueprintReview, null);
  } finally { globalThis.window = previous; }
});

test("review checkboxes hydrate idempotently and allow forgetting missing exclusions", () => {
  const checkbox = { dataset: { managedExclusion: "sensor.missing" } };
  const panel = {
    _blueprintReview: { keptExclusions: new Set(["sensor.missing"]) },
    shadowRoot: { querySelectorAll: (selector) => selector === "[data-managed-exclusion]" ? [checkbox] : [] },
  };
  hydrateManagedBlueprint(panel);
  hydrateManagedBlueprint(panel);
  assert.equal(checkbox.checked, true);
  checkbox.checked = false;
  checkbox.onchange();
  assert.equal(panel._blueprintReview.keptExclusions.size, 0);
});

test("table update icon precedes the name and opens review without mutation", () => {
  const previous = globalThis.document;
  globalThis.document = { createElement: (tag) => ({ tag, children: [], attrs: {}, style: {}, append(...items) { this.children.push(...items); }, setAttribute(key, value) { this.attrs[key] = value; }, addEventListener(key, fn) { this[key] = fn; } }) };
  try {
    let opened;
    const panel = {
      _managedBlueprints: { r: proposal }, _t: t,
      _ensureRulesTableState: () => ({ hiddenColumns: [], columnOrder: [] }),
      _openRuleEditor: (id) => { opened = id; },
    };
    const name = nativeRuleNameCell.call(panel, { id: "r", name: "CPU", managed: true });
    const [icon, title] = name.children[0].children;
    assert.equal(icon.tag, "ha-icon-button");
    assert.equal(icon.attrs["aria-label"], "managed.available");
    assert.equal(title.textContent, "CPU");
    icon.click({ stopPropagation() {} });
    assert.equal(opened, "r");
    const unmanaged = nativeRuleNameCell.call(panel, { id: "r", name: "CPU", managed: false });
    assert.equal(unmanaged.children[0].textContent, "CPU");
  } finally { globalThis.document = previous; }
});

for (const [label, cacheChanges, expectedCalls] of [
  ["fresh", {}, 0],
  ["expired", { checkedAt: 0 }, 1],
  ["edited rule", { ruleSignature: "old draft" }, 1],
]) {
  test(`review uses ${label} comparison appropriately`, async () => {
    let calls = 0;
    const panel = {
      _editingRule: rule, _config: { rules: [rule] },
      _managedBlueprints: { r: { ...proposal, checkedAt: Date.now(), ruleSignature: JSON.stringify(rule), ...cacheChanges } },
      _call: async () => { calls++; return [proposal]; },
      _refreshRulesData() {}, _refreshRuleEditor() {},
    };
    await handleManagedBlueprintAction(panel, "review-blueprint");
    assert.equal(calls, expectedCalls);
    assert.equal(panel._blueprintReview.proposal.token, "fresh");
    assert.deepEqual([...panel._blueprintReview.selected], ["sensor.cpu", "sensor.new"]);
  });
}

for (const result of [null, { ...rule, blueprint: { ...rule.blueprint, managed: false } }]) {
  test(`late ${result ? "successful" : "failed"} detach preserves the current editor`, async () => {
    const previous = globalThis.window;
    globalThis.window = { confirm: () => true };
    try {
      let finish;
      let replaced;
      const panel = {
        _editingRule: rule, _t: t,
        _call: () => new Promise((resolve) => { finish = resolve; }),
        _replaceRule: (updated) => { replaced = updated; },
        _refreshRuleEditor: () => assert.fail("late result reopened editor"),
      };
      const pending = handleManagedBlueprintAction(panel, "detach-blueprint");
      const other = { id: "other" };
      panel._editingRule = other;
      finish(result);
      await pending;
      assert.equal(panel._editingRule, other);
      assert.equal(replaced, result ?? undefined);
    } finally { globalThis.window = previous; }
  });
}


test("editing one rule retains other rules' update indicators and reviews", () => {
  const otherReview = { proposal: { rule_id: "other" } };
  const panel = {
    _config: { rules: [rule] }, _editingRule: { id: "other" },
    _managedBlueprints: { r: proposal, other: { update_available: true } },
    _blueprintReview: otherReview,
    _refreshRulesData() {},
  };
  replaceRule.call(panel, { ...rule, enabled: false });
  assert.equal(panel._managedBlueprints.r, undefined);
  assert.equal(panel._managedBlueprints.other.update_available, true);
  assert.equal(panel._blueprintReview, otherReview);
});

const editor = await import("../frontend-src/components/rule-editor.js");
const managedDraft = { ...rule, source: "jinja", condition_template: "{{ true }}", message: "{{ secret }}", operator: "equals", value: "", duration: 0 };

test("managed editor has YAML and action icons, hides structure and duplication, and renders test results", () => {
  const context = { rule: managedDraft, mode: "visual", t, renderTextField: () => "", renderNumberField: () => "", renderTestResult: () => "test-result" };
  const html = editor.renderRuleEditor(context);
  assert.match(html, /value="switch-editor"/);
  assert.doesNotMatch(html, /value="duplicate-rule"|\{\{ secret \}\}|\{\{ true \}\}|<dt>/);
  assert.match(html, /data-rule-test-result>test-result/);
  for (const icon of ["mdi:refresh", "mdi:link-off", "mdi:flask-outline", "mdi:content-save"]) assert.ok(html.includes(icon));
  const yaml = editor.renderRuleEditor({ ...context, mode: "yaml" });
  assert.match(yaml, /id="rule-yaml-editor"/);
  assert.match(yaml, /managed.yaml_help/);
  assert.doesNotMatch(yaml, /data-action="review-blueprint"|value="duplicate-rule"/);
});

test("membership changes never capture or dirty the rule form", () => {
  const panel = { _editingRule: managedDraft, _ruleDirty: false, _captureRuleDraft() { assert.fail("review is not a rule edit"); } };
  editor.handleRuleInput.call(panel, { target: { closest: (selector) => [".managed-review", "#rule-form"].includes(selector) } });
  assert.equal(panel._ruleDirty, false);
});

test("real rule edits still block blueprint actions and empty membership has an actionable error", async () => {
  for (const dirty of [true, false]) {
    const panel = { _editingRule: managedDraft, _ruleDirty: dirty, _t: t, _blueprintReview: { proposal, selected: new Set() }, _refreshRuleEditor() {}, _call() { assert.fail("invalid apply sent"); } };
    await handleManagedBlueprintAction(panel, "apply-blueprint");
    assert.equal(panel._ruleEditorError, dirty ? "managed.save_first" : "managed.empty");
  }
});

test("managed YAML contains only editable settings and switching back preserves provenance", async () => {
  const panel = { _editingRule: managedDraft, _ruleEditorMode: "visual", _clearRuleEditorError() {}, _clearRuleTestResult() {}, _captureRuleDraft() {}, _refreshRuleEditor() {}, _call: async () => managedDraft };
  await editor.switchRuleEditor.call(panel);
  assert.equal(panel._ruleYaml, "enabled: true\n");
  assert.doesNotMatch(panel._ruleYaml, /blueprint|entity_ids|source|operator|value:|message|condition_template/);
  await editor.switchRuleEditor.call(panel);
  assert.equal(panel._ruleEditorMode, "visual");
  assert.deepEqual(panel._editingRule.blueprint, managedDraft.blueprint);
});

test("managed duplication is guarded even when invoked directly", async () => {
  const panel = { _editingRule: managedDraft, _captureRuleDraft() { assert.fail("duplicated managed rule"); } };
  await editor.duplicateRuleDraft.call(panel);
  assert.equal(panel._editingRule, managedDraft);
});

test("managed test sends editable overrides and updates the shared result surface", async () => {
  let sent;
  let scrolled;
  const panel = { _editingRule: managedDraft, _ruleTestSequence: 0, _clearRuleEditorError() {}, _captureRuleDraft: () => managedDraft, _api: { testRule: async (payload, id) => { sent = { payload, id }; return { results: [] }; } }, _updateRuleTestDisplay(options) { scrolled = options?.scroll; } };
  await editor.testRule.call(panel);
  assert.equal(sent.id, managedDraft.id);
  assert.equal(sent.payload.duration, 0);
  assert.deepEqual(panel._ruleTestResult, { results: [] });
  assert.equal(scrolled, true);
  assert.equal(panel._ruleTestLoading, false);
});

for (const [operator, current, candidate, changed] of [
  ["above", "90", 90, false],
  ["below", "90.0", 90, false],
  ["between", ["80", "90"], [80, 90], false],
  ["outside", ["80", "90"], [90, 80], true],
  ["above", "90", 95, true],
  ["above", "", 0, true],
  ["above", null, 0, true],
  ["equals", "090", 90, true],
]) {
  test(`blueprint review preserves semantic threshold changes: ${operator} ${JSON.stringify(current)} → ${JSON.stringify(candidate)}`, () => {
    const currentRule = { ...rule, source: "value", operator, value: current };
    const next = { ...proposal, candidate: { ...currentRule, value: candidate } };
    const html = renderManagedBlueprint({ rule: currentRule, review: { proposal: next }, t });
    assert.equal(html.includes("<h4>managed.changes</h4>"), changed);
  });
}

test("applying a reviewed selection sends it without another confirmation", async () => {
  const previous = globalThis.window;
  globalThis.window = { confirm() { assert.fail("redundant confirmation"); } };
  try {
    let sent;
    const panel = {
      _editingRule: rule, _t: t,
      _blueprintReview: { proposal, selected: new Set(["sensor.cpu"]), keptExclusions: new Set() },
      _call: async (message) => { sent = message; return { ...rule }; },
      _replaceRule() {}, _refreshRuleEditor() {}, _refreshTabData() {},
    };
    await handleManagedBlueprintAction(panel, "apply-blueprint");
    assert.equal(sent.type, "alert_manager/rules/blueprints/apply");
    assert.deepEqual(sent.entity_ids, ["sensor.cpu"]);
    assert.deepEqual(sent.excluded_entities, ["sensor.new"]);
  } finally { globalThis.window = previous; }
});

test("managed YAML separates enabled state from explicit overrides", async () => {
  const validated = { ...managedDraft, enabled: false, blueprint: { ...managedDraft.blueprint, overrides: { name: "My CPU", duration: 600, value: 95 } } };
  const panel = { _editingRule: managedDraft, _ruleEditorMode: "visual", _clearRuleEditorError() {}, _clearRuleTestResult() {}, _captureRuleDraft() {}, _refreshRuleEditor() {}, _call: async () => validated };
  await editor.switchRuleEditor.call(panel);
  assert.match(panel._ruleYaml, /^enabled: false\noverride:/);
  assert.match(panel._ruleYaml, /^  name: "My CPU"$/m);
  assert.match(panel._ruleYaml, /^  duration: 600$/m);
  assert.match(panel._ruleYaml, /^  value: 95$/m);
  assert.doesNotMatch(panel._ruleYaml, /^(name|duration|value):/m);
});

test("applying blueprint changes displays a success message inside the drawer", async () => {
  const panel = {
    _editingRule: rule, _t: t,
    _blueprintReview: { proposal, selected: new Set(["sensor.cpu"]), keptExclusions: new Set() },
    _call: async () => ({ ...rule }), _replaceRule() {}, _refreshRuleEditor() {}, _refreshTabData() {},
  };
  await handleManagedBlueprintAction(panel, "apply-blueprint");
  assert.deepEqual(panel._notice, { kind: "success", text: "managed.applied", ruleId: rule.id });
  const html = editor.renderRuleEditor({ rule: managedDraft, mode: "visual", t, notice: panel._notice, renderTextField: () => "", renderNumberField: () => "" });
  assert.match(html, /class="rule-editor-success" alert-type="success" role="status">managed.applied/);
});

test("failed blueprint application never reports success", async () => {
  const panel = {
    _editingRule: rule, _t: t,
    _blueprintReview: { proposal, selected: new Set(["sensor.cpu"]), keptExclusions: new Set() },
    _call: async () => null, _refreshRuleEditor() {},
  };
  await handleManagedBlueprintAction(panel, "apply-blueprint");
  assert.equal(panel._notice, null);
  assert.equal(panel._ruleEditorError, "errors.unknown");
  assert.notEqual(panel._blueprintReview, null);
});

test("failed managed YAML preparation preserves the visual draft and reports the error", async () => {
  const panel = { _editingRule: managedDraft, _ruleEditorMode: "visual", _ruleDirty: true, _notice: { text: "Validation failed" }, _clearRuleEditorError() {}, _clearRuleTestResult() {}, _captureRuleDraft() {}, _refreshRuleEditor() {}, _refreshUiState() {}, _t: t, _call: async () => null };
  await editor.switchRuleEditor.call(panel);
  assert.equal(panel._editingRule, managedDraft);
  assert.equal(panel._ruleEditorMode, "visual");
  assert.equal(panel._ruleDirty, true);
  assert.equal(panel._ruleEditorError, "Validation failed");
});

test("late managed YAML preparation cannot replace another editor", async () => {
  let finish;
  const panel = { _editingRule: managedDraft, _ruleEditorMode: "visual", _clearRuleEditorError() {}, _clearRuleTestResult() {}, _captureRuleDraft() {}, _refreshRuleEditor() { assert.fail("stale editor refreshed"); }, _call: () => new Promise(resolve => { finish = resolve; }) };
  const pending = editor.switchRuleEditor.call(panel);
  const other = { id: "other" };
  panel._editingRule = other;
  finish(managedDraft);
  await pending;
  assert.equal(panel._editingRule, other);
  assert.equal(panel._ruleEditorMode, "visual");
});
