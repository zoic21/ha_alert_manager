import assert from "node:assert/strict";
import test from "node:test";
import { AlertManagerApi } from "../frontend-src/api/transport.js";
import { handleEntityReplacementAction, hydrateEntityReplacement, renderEntityReplacement } from "../frontend-src/views/entity-replacement.js";
import { renderCoherence } from "../frontend-src/views/coherence.js";

const translate = (key, values = {}) => `${key} ${JSON.stringify(values)}`;
const preview = {
  preview_id: "preview", old_entity_id: "light.old", new_entity_id: "light.new",
  replacement_count: 2, file_count: 1,
  replacements: [
    { id: "one", source_name: "Bureau <script>", source_type: "automation", file: "automations.yaml", line: 3, column: 8 },
    { id: "two", source_name: "Bureau", source_type: "automation", file: "automations.yaml", line: 3, column: 22 },
  ],
};

const element = (dataset = {}) => ({
  dataset, handlers: {}, addEventListener(name, callback) { this.handlers[name] = callback; },
});

test("replacement is available before a scan and previews escaped source names with checkboxes", () => {
  for (const result of [null, { results: [] }]) {
    assert.match(renderCoherence({ result, t: translate }), /data-action="open-entity-replacement"/);
  }
  const state = { preview, selected: new Set(["one"]), busy: false };
  const markup = renderEntityReplacement({ state, t: translate });
  assert.match(markup, /Bureau &lt;script&gt;/);
  assert.match(markup, /data-replacement-id="one" checked/);
  assert.match(markup, /data-replacement-id="two"\s+aria-label/);
  assert.match(markup, /data-action="apply-entity-replacement"/);
  assert.doesNotMatch(markup, /<button|<table|<input/);
  assert.equal(state.selected.size, 1);
});

test("native autocomplete allows typed IDs and hydration never stacks callbacks", () => {
  const old = element({ replacementField: "old_entity_id" });
  const next = element({ replacementField: "new_entity_id" });
  const dialog = element();
  dialog.querySelectorAll = (selector) => selector === "[data-replacement-field]" ? [old, next] : [];
  const root = { querySelector() { return dialog; } };
  const context = {
    _entityReplacement: { old_entity_id: "light.deleted", new_entity_id: "", busy: false },
    _hass: { states: { "light.new": { attributes: { friendly_name: "Bureau" } } }, entities: { "light.disabled": {} } },
    _t: translate, _render() {},
  };
  hydrateEntityReplacement(root, context);
  const callback = old.handlers["value-changed"];
  hydrateEntityReplacement(root, context);
  assert.equal(old.handlers["value-changed"], callback);
  assert.equal(old.selector.select.custom_value, true);
  assert.deepEqual(old.selector.select.options.map((item) => item.value), ["light.disabled", "light.new"]);
  assert.match(old.selector.select.options[1].label, /Bureau/);
  callback({ detail: { value: "light.typed" } });
  assert.equal(context._entityReplacement.old_entity_id, "light.typed");
  assert.equal(old.value, "light.typed");
  assert.equal(dialog.open, true);
});

test("unchecking the last occurrence disables Replace without a full render", () => {
  const checkbox = element({ replacementId: "one" });
  checkbox.checked = false;
  const apply = {};
  const count = {};
  const dialog = element();
  dialog.querySelectorAll = (selector) => selector === "[data-replacement-id]" ? [checkbox] : [];
  dialog.querySelector = (selector) => selector.includes("count") ? count : apply;
  const context = {
    _entityReplacement: { preview, selected: new Set(["one"]), busy: false },
    _t: translate, _render() { assert.fail("selection must preserve the focused checkbox"); },
  };
  hydrateEntityReplacement({ querySelector: () => dialog }, context);
  checkbox.handlers.change();
  assert.equal(context._entityReplacement.selected.size, 0);
  assert.equal(apply.disabled, true);
  assert.match(count.textContent, /&?"count":0/);
  checkbox.checked = true;
  checkbox.handlers.change();
  assert.equal(apply.disabled, false);
});

test("dialog previews before applying, retains selection on error and blocks duplicate requests", async () => {
  let release;
  let applied;
  const context = {
    _api: {
      previewEntityReplacement(old, next) {
        assert.equal(old, "light.old"); assert.equal(next, "light.new");
        return new Promise((resolve) => { release = () => resolve(preview); });
      },
      async applyEntityReplacement(id, ids) {
        applied = { id, ids }; throw { code: "replacement_entity_missing" };
      },
    },
    _t: translate, _render() {}, _errorText: () => "generic",
  };
  await handleEntityReplacementAction.call(context, "open-entity-replacement");
  context._entityReplacement.old_entity_id = "light.old";
  context._entityReplacement.new_entity_id = "light.new";
  const pending = handleEntityReplacementAction.call(context, "preview-entity-replacement");
  assert.equal(context._entityReplacement.busy, true);
  await handleEntityReplacementAction.call(context, "close-entity-replacement");
  assert.ok(context._entityReplacement);
  release(); await pending;
  context._entityReplacement.selected.delete("two");
  await handleEntityReplacementAction.call(context, "apply-entity-replacement");
  assert.deepEqual(applied, { id: "preview", ids: ["one"] });
  assert.match(context._entityReplacement.error, /replacement_entity_missing/);
  assert.deepEqual([...context._entityReplacement.selected], ["one"]);
  await handleEntityReplacementAction.call(context, "back-entity-replacement");
  assert.equal(context._entityReplacement.preview, null);
  assert.equal(context._entityReplacement.old_entity_id, "light.old");
});

test("read-only users never preview or apply replacements", async () => {
  const context = { _readOnly: true, _api: { previewEntityReplacement() { assert.fail(); } } };
  for (const action of ["open", "preview", "apply"]) {
    await handleEntityReplacementAction.call(context, `${action}-entity-replacement`);
  }
  assert.equal(context._entityReplacement, undefined);
});

const updates = [
  { domain: "automation", key: "office/é", before: { id: "office/é", entity_id: "light.old" }, after: { id: "office/é", entity_id: "light.new" } },
  { domain: "script", key: "test", before: { sequence: [{ entity_id: "light.old" }] }, after: { sequence: [{ entity_id: "light.new" }] } },
];

test("native configuration APIs validate and save each object before backend final verification", async () => {
  const calls = [];
  const api = new AlertManagerApi(() => ({
    async callWS(message) {
      calls.push(message.type);
      if (message.type.endsWith("prepare")) return { native_updates: updates };
      return { replacement_count: 2 };
    },
    async callApi(method, path, value) {
      calls.push({ method, path, value });
      if (method === "GET") return path.includes("automation") ? { entity_id: "light.old", id: "office/é" } : updates[1].before;
      return { result: "ok" };
    },
  }));
  const result = await api.applyEntityReplacement("preview", ["one", "two"]);
  assert.equal(result.replacement_count, 2);
  assert.equal(calls[0], "alert_manager/coherence/entity_replacement/prepare");
  assert.deepEqual(calls[2], { method: "POST", path: "config/automation/config/office%2F%C3%A9", value: updates[0].after });
  assert.equal(calls.at(-1), "alert_manager/coherence/entity_replacement/apply");
});

for (const failure of ["native", "backend"]) {
  test(`${failure} failure rolls back all attempted native writes through HA APIs`, async () => {
    const writes = [];
    const api = new AlertManagerApi(() => ({
      async callWS(message) {
        if (message.type.endsWith("prepare")) return { native_updates: updates };
        if (failure === "backend") throw { code: "replacement_yaml_invalid" };
        assert.fail("a failed HA validation must prevent external YAML writes");
      },
      async callApi(method, path, value) {
        if (method === "GET") return path.includes("automation") ? updates[0].before : updates[1].before;
        writes.push({ path, value });
        if (failure === "native" && writes.length === 2) throw new Error("HA validation rejected this object");
      },
    }));
    await assert.rejects(api.applyEntityReplacement("preview", ["one", "two"]));
    assert.equal(writes.length, 4);
    assert.deepEqual(writes[2].value, updates[1].before);
    assert.deepEqual(writes[3].value, updates[0].before);
  });
}

test("a concurrent native editor change is preserved and prevents its replacement", async () => {
  let writes = 0;
  const api = new AlertManagerApi(() => ({
    async callWS() { return { native_updates: [updates[0]] }; },
    async callApi(method) {
      if (method === "GET") return { id: "office/é", entity_id: "light.edited" };
      writes++;
    },
  }));
  await assert.rejects(api.applyEntityReplacement("preview", ["one"]), (error) => error.code === "replacement_preview_stale");
  assert.equal(writes, 0);
});
