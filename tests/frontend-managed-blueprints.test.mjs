import assert from "node:assert/strict";
import test from "node:test";
import { renderManagedBlueprint, handleManagedBlueprintAction, hydrateManagedBlueprint } from "../frontend-src/components/managed-blueprints.js";
import { refreshManagedBlueprints } from "../frontend-src/api/alert-manager-api.js";
import { nativeRuleNameCell } from "../frontend-src/views/rules.js";

const rule = { id: "r", name: "CPU", entity_ids: ["sensor.cpu"], blueprint: { id: "cpu", version: 1, managed: true, excluded_entities: ["sensor.missing"] } };
const proposal = { rule_id: "r", added: ["sensor.new"], removed: [], discovered: ["sensor.cpu", "sensor.new"], update_available: true, candidate: { entity_ids: ["sensor.cpu", "sensor.new"] }, token: "fresh" };
const t = (key) => key;

test("managed review escapes data and exposes explicit membership decisions", () => {
  const html = renderManagedBlueprint({ rule: { ...rule, blueprint: { ...rule.blueprint, id: '<script>' } }, proposal, review: { proposal }, t });
  assert.match(html, /data-managed-entity="sensor.new"/);
  assert.match(html, /data-managed-exclusion="sensor.missing"/);
  assert.match(html, /data-action="apply-blueprint"/);
  assert.match(html, /ha-alert/);
  assert.doesNotMatch(html, /<script>/);
  assert.equal(renderManagedBlueprint({ rule: { ...rule, blueprint: { managed: false } }, t }), "");
  assert.doesNotMatch(renderManagedBlueprint({ rule, t }), /ha-alert/);
});

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
