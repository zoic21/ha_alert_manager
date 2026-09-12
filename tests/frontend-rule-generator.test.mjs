import assert from "node:assert/strict";
import test from "node:test";
import { renderRuleGenerator, hydrateRuleGenerator, handleRuleGeneratorAction } from "../frontend-src/components/rule-generator.js";
import { renderRules } from "../frontend-src/views/rules.js";

const row = { blueprint_id: "cpu", category: "system", name_key: "CPU", description_key: "Description", entity_count: 2, status: "available" };
const drawer = () => ({ kind: "generator", rows: [row], loading: false, selected: new Set() });
const render = (draft) => renderRuleGenerator({ drawer: draft, busy: false, t: (key) => key });

test("generator uses native drawer, escaped labels and disabled reasons", () => {
  const draft = drawer();
  draft.rows.push({ ...row, blueprint_id: 'bad"<', name_key: '<script>', status: "no_entities" });
  const html = render(draft);
  assert.match(html, /configuration-drawer/);
  assert.match(html, /ha-checkbox/);
  assert.match(html, /generator.status.no_entities/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script\b/i);
  assert.match(html, /data-action="generate-rules" disabled/);
  assert.ok(html.indexOf('data-blueprint-id="cpu"') < html.indexOf('generator.status.no_entities'));
  assert.doesNotMatch(html, /ha-selector|ha-input|ha-textfield/);
});

for (const [label, escaped] of [
  ["<script>", "&lt;script&gt;"],
  ["<SCRIPT>", "&lt;SCRIPT&gt;"],
  ["<ScRiPt>", "&lt;ScRiPt&gt;"],
  ['<SCRIPT src="test.js">', "&lt;SCRIPT src=&quot;test.js&quot;&gt;"],
]) {
  test(`generator escapes script labels: ${label}`, () => {
    const draft = drawer();
    draft.rows = [{ ...row, name_key: label, description_key: label }];
    const html = render(draft);
    assert.ok(html.includes(`<strong>${escaped}</strong><p>${escaped}</p>`));
    assert.ok(html.includes(`aria-label="${escaped}"`));
    assert.doesNotMatch(html, /<script\b/i);
  });
}

test("Custom rules exposes the generator action", () => {
  const html = renderRules({ editorOpen: false, editor: "", editorWidth: 560, pageMessages: "", t: (key) => key, renderFacetFilter: () => "" });
  assert.match(html, /class="rules-header-actions">\s*<ha-button data-action="open-rule-generator"><ha-icon slot="start" icon="mdi:auto-fix"><\/ha-icon>[\s\S]*?<\/ha-button>\s*<ha-button[^>]*data-action="new-rule"[\s\S]*?<\/ha-button>\s*<\/div>/);
});

test("checkbox hydration updates selection and create button without rerendering", () => {
  const draft = drawer();
  const checkbox = { dataset: { blueprintId: "cpu" }, disabled: false };
  const button = {};
  const root = { querySelectorAll: () => [checkbox], querySelector: () => button };
  const panel = { _configurationDrawer: draft, _busy: false };
  hydrateRuleGenerator(root, panel);
  hydrateRuleGenerator(root, panel);
  checkbox.checked = true;
  checkbox.onchange();
  assert.deepEqual([...draft.selected], ["cpu"]);
  assert.equal(button.disabled, false);
  checkbox.checked = false;
  checkbox.onchange();
  assert.equal(button.disabled, true);
});

test("creation submits IDs only, inserts returned rules and closes on success", async () => {
  const draft = drawer();
  draft.selected.add("cpu");
  let message;
  const panel = { _configurationDrawer: draft, _config: { rules: [] }, _t: (key) => key, _render() {}, async _call(value) { message = value; return [{ id: "new", blueprint: { id: "cpu", version: 1, managed: false } }]; } };
  assert.equal(await handleRuleGeneratorAction(panel, "generate-rules"), true);
  assert.deepEqual(message, { type: "alert_manager/rules/blueprints/create", blueprint_ids: ["cpu"] });
  assert.equal(panel._config.rules.length, 1);
  assert.equal(panel._configurationDrawer, null);
  assert.equal(panel._notice.kind, "success");
});

test("failed creation preserves selection and config for refresh or retry", async () => {
  const draft = drawer();
  draft.selected.add("cpu");
  const panel = { _configurationDrawer: draft, _config: { rules: [] }, _t: (key) => key, _render() {}, async _call() { return null; } };
  await handleRuleGeneratorAction(panel, "generate-rules");
  assert.equal(panel._configurationDrawer, draft);
  assert.equal(draft.selected.size, 1);
  assert.deepEqual(panel._config.rules, []);
});

test("late discovery response cannot reopen a closed or switched drawer", async () => {
  const draft = drawer();
  let complete;
  let renders = 0;
  const panel = { _configurationDrawer: draft, _render() { renders++; }, _call: () => new Promise((resolve) => { complete = resolve; }) };
  const pending = handleRuleGeneratorAction(panel, "refresh-rule-generator");
  panel._configurationDrawer = null;
  complete([row]);
  await pending;
  assert.equal(panel._configurationDrawer, null);
  assert.equal(renders, 1);
});

test("visual payload and YAML preserve structured provenance", async () => {
  const { serializeRuleDraft } = await import("../frontend-src/components/rule-editor.js");
  const { ruleToYaml } = await import("../frontend-src/utils/formatting.js");
  const rule = { name: "Renamed", entity_ids: ["sensor.cpu"], source: "value", operator: "above", value: 90, duration: 300, blueprint: { id: "cpu", version: 1, managed: false } };
  assert.deepEqual(serializeRuleDraft(rule).blueprint, rule.blueprint);
  assert.ok(ruleToYaml(rule).endsWith('blueprint:\n  id: "cpu"\n  version: 1\n  managed: false\n'));
  const { blueprint, ...manualRule } = rule;
  assert.doesNotMatch(ruleToYaml(manualRule), /^blueprint:/m);
  assert.ok(ruleToYaml({ ...rule, blueprint: { ...blueprint, id: 'cpu: "test"' } })
    .includes('  id: "cpu: \\"test\\""\n'));
});
