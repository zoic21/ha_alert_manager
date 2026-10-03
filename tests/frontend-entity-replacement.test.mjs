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

test("single and bulk coherence corrections preview only selected rows and wait for confirmation", async () => {
  const rows = [
    { id: "a", index: 0, selectable: true },
    { id: "b", index: 1, selectable: true },
    { id: "deleted", index: 2, selectable: false },
  ];
  let requested;
  let writes = 0;
  let scans = 0;
  const correctionPreview = {
    ...preview,
    replacements: preview.replacements.map((row) => ({ ...row, old_entity_id: "light.old", new_entity_id: "light.current" })),
    coherence_correction: true,
  };
  const context = {
    _coherence: { scanned_at: "scan-time" },
    _selectedCoherenceIds: new Set(["a", "b", "deleted"]),
    _coherenceTableRows: () => rows,
    _t: translate, _errorText: () => "generic", _render() {},
    _api: {
      async previewCoherenceCorrections(scannedAt, indices) { requested = { scannedAt, indices }; return correctionPreview; },
      async applyEntityReplacement(id, ids) {
        writes++;
        assert.equal(id, "preview");
        assert.deepEqual(ids, ["one", "two"]);
        return { replacement_count: 2, file_count: 1, yaml_changed: true };
      },
      async scanCoherence() { scans++; return { scanned_at: "after-fix", results: [] }; },
    },
  };
  await handleEntityReplacementAction.call(context, "correct-coherence", { dataset: { rowIndex: "1" } });
  assert.deepEqual(requested, { scannedAt: "scan-time", indices: [1] });
  assert.equal(writes, 0);
  const markup = renderEntityReplacement({ state: context._entityReplacement, t: translate });
  assert.match(markup, /light.old → light.current/);
  assert.match(markup, /coherence.correction.confirm/);
  assert.doesNotMatch(markup, /back-entity-replacement|data-replacement-field/);
  await handleEntityReplacementAction.call(context, "close-entity-replacement");
  assert.equal(writes, 0);
  assert.equal(context._selectedCoherenceIds.size, 3);
  await handleEntityReplacementAction.call(context, "correct-selected-coherence");
  assert.deepEqual(requested, { scannedAt: "scan-time", indices: [0, 1] });
  await handleEntityReplacementAction.call(context, "apply-entity-replacement");
  assert.equal(writes, 1);
  assert.equal(scans, 1);
  assert.equal(context._selectedCoherenceIds.size, 0);
  assert.deepEqual(context._coherence.results, []);
  assert.equal(context._coherenceScannedAt, "after-fix");
  assert.ok(context._entityReplacement.result);
});

test("correction preview failures and noneditable selections never write", async () => {
  const context = {
    _coherence: { scanned_at: "scan-time" },
    _selectedCoherenceIds: new Set(["deleted"]),
    _coherenceTableRows: () => [{ id: "deleted", index: 0, selectable: false }],
    _render() {}, _t: translate, _errorText: () => "generic",
    _api: { previewCoherenceCorrections() { assert.fail(); } },
  };
  await handleEntityReplacementAction.call(context, "correct-selected-coherence");
  assert.equal(context._entityReplacement, undefined);
  context._coherenceTableRows = () => [{ id: "editable", index: 1, selectable: true }];
  context._api.previewCoherenceCorrections = async () => { throw { code: "replacement_preview_stale" }; };
  await handleEntityReplacementAction.call(context, "correct-coherence", { dataset: { rowIndex: "1" } });
  assert.match(context._entityReplacement.error, /replacement_preview_stale/);
  assert.equal(context._entityReplacement.busy, false);
  assert.doesNotMatch(renderEntityReplacement({ state: context._entityReplacement, t: translate }), /data-action="apply-entity-replacement"/);
  context._readOnly = true;
  await handleEntityReplacementAction.call(context, "correct-selected-coherence");
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

test("a failed native restoration still restores earlier objects and preserves the apply error", async () => {
  const failure = new Error("native save failed");
  const restoreFailure = new Error("native restore failed");
  const writes = [];
  const api = new AlertManagerApi(() => ({
    async callWS(message) {
      if (message.type.endsWith("prepare")) return { native_updates: updates };
      assert.fail("backend apply must not start after a native save fails");
    },
    async callApi(method, path, value) {
      if (method === "GET") return path.includes("automation") ? updates[0].before : updates[1].before;
      writes.push({ path, value });
      if (writes.length === 2) throw failure;
      if (writes.length === 3) throw restoreFailure;
    },
  }));

  await assert.rejects(api.applyEntityReplacement("preview", ["one", "two"]), (error) => {
    assert.equal(error.code, "replacement_rollback_failed");
    assert.equal(error.cause, failure);
    assert.deepEqual(error.rollbackErrors, [{ path: "config/script/config/test", error: restoreFailure }]);
    return true;
  });
  assert.equal(writes.length, 4);
  assert.deepEqual(writes.at(-1).value, updates[0].before);
});

for (const code of ["replacement_failed", "replacement_rollback_failed"]) {
  test(`confirmed backend ${code} restores native objects and retains the backend error`, async () => {
    const failure = { body: { code } };
    const writes = [];
    const api = new AlertManagerApi(() => ({
      async callWS(message) {
        if (message.type.endsWith("prepare")) return { native_updates: updates };
        throw failure;
      },
      async callApi(method, path, value) {
        if (method === "GET") return path.includes("automation") ? updates[0].before : updates[1].before;
        writes.push(value);
      },
    }));
    await assert.rejects(api.applyEntityReplacement("preview", ["one", "two"]), (error) => error === failure);
    assert.deepEqual(writes, [updates[0].after, updates[1].after, updates[1].before, updates[0].before]);
  });
}

test("a lost backend apply reply does not undo only the native part of a committed batch", async () => {
  const failure = new Error("connection lost after commit");
  const writes = [];
  let backendCommitted = false;
  const api = new AlertManagerApi(() => ({
    async callWS(message) {
      if (message.type.endsWith("prepare")) return { native_updates: updates };
      backendCommitted = true;
      throw failure;
    },
    async callApi(method, path, value) {
      if (method === "GET") return path.includes("automation") ? updates[0].before : updates[1].before;
      writes.push(value);
    },
  }));
  await assert.rejects(api.applyEntityReplacement("preview", ["one", "two"]), (error) => {
    assert.equal(error.code, "replacement_incomplete");
    assert.equal(error.cause, failure);
    return true;
  });
  assert.equal(backendCommitted, true);
  assert.deepEqual(writes, [updates[0].after, updates[1].after]);
});

for (const code of ["replacement_rollback_failed", "replacement_incomplete"]) {
  test(`${code} is translated in the replacement dialog`, async () => {
    const context = {
      _entityReplacement: { preview, selected: new Set(["one"]), busy: false },
      _api: { async applyEntityReplacement() { throw { code }; } },
      _t: translate, _render() {}, _errorText() { assert.fail("use the replacement diagnosis"); },
    };
    await handleEntityReplacementAction.call(context, "apply-entity-replacement");
    assert.match(context._entityReplacement.error, new RegExp(`coherence.replacement.errors.${code}`));
    assert.equal(context._entityReplacement.busy, false);
    assert.equal(context._entityReplacement.result, undefined);
  });
}
