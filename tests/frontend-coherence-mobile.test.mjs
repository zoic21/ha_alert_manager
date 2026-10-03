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

  dispatchEvent() {
    return true;
  }
};

globalThis.CustomEvent = class {
  constructor(type, options) {
    this.type = type;
    Object.assign(this, options);
  }
};

const fakeDomElement = (tagName) => ({
  tagName: tagName.toUpperCase(),
  attributes: {},
  children: [],
  dataset: {},
  style: { cssText: "" },
  textContent: "",
  setAttribute(name, value) { this.attributes[name] = String(value); },
  append(...children) { this.children.push(...children); },
  addEventListener(name, callback) { this.listeners ??= {}; this.listeners[name] = callback; },
});
globalThis.document = { createElement: fakeDomElement };
globalThis.customElements = {
  _items: new Map(),
  define(name, value) { this._items.set(name, value); },
  get(name) { return this._items.get(name); },
};

const storage = new Map();
globalThis.window = {
  localStorage: {
    getItem(key) { return storage.get(key) ?? null; },
    setItem(key, value) { storage.set(key, value); },
    clear() { storage.clear(); },
  },
};

await import("../frontend-src/alert-manager-panel.js");

const Panel = customElements.get("alert-manager-panel");

test("rename history is in the adjacent action column before and after a scan", async () => {
  const { renderCoherence } = await import("../frontend-src/views/coherence.js");
  for (const result of [null, { results: [] }]) {
    const markup = renderCoherence({ result, t: (key) => key });
    assert.match(markup, /<div class="coherence-action-column">\s*<ha-button appearance="outlined" data-action="open-entity-renames"/);
    assert.ok(markup.indexOf('data-action="open-entity-renames"') > markup.indexOf('data-action="export-entities"'));
  }
});

test("rename drawer loads on demand once, closes while loading and refreshes on reopen", async () => {
  const { handleCoherenceAction } = await import("../frontend-src/views/coherence.js");
  const { AlertManagerApi } = await import("../frontend-src/api/transport.js");
  let resolveLoad;
  let calls = 0;
  const context = {
    _readOnly: false,
    _entityRenamesState: { data: null, loading: false, error: null },
    _render() {},
    _errorText: (error) => error.message,
    _api: new AlertManagerApi(() => ({ callWS(message) {
      assert.deepEqual(message, { type: "alert_manager/coherence/entity_renames/list" });
      calls += 1;
      return new Promise((resolve) => { resolveLoad = resolve; });
    } })),
  };
  const pending = handleCoherenceAction.call(context, "open-entity-renames");
  assert.deepEqual(context._configurationDrawer, { kind: "entity-renames" });
  assert.equal(context._entityRenamesState.loading, true);
  await handleCoherenceAction.call(context, "open-entity-renames");
  assert.equal(calls, 1);
  await handleCoherenceAction.call(context, "close-entity-renames");
  resolveLoad({ renames: [] });
  await pending;
  assert.equal(context._configurationDrawer, null);
  assert.equal(context._entityRenamesState.loading, false);
  const reopened = handleCoherenceAction.call(context, "open-entity-renames");
  assert.equal(calls, 2);
  resolveLoad({ renames: [{ new_entity_id: "sensor.new" }] });
  await reopened;
  assert.equal(context._entityRenamesState.data.renames.length, 1);
  context._api = { entityRenames: async () => { throw new Error("offline"); } };
  await handleCoherenceAction.call(context, "open-entity-renames");
  assert.equal(context._entityRenamesState.error, "offline");
  assert.equal(context._entityRenamesState.loading, false);
  context._readOnly = true;
  context._api = { entityRenames() { assert.fail("Read-only users cannot read coherence history"); } };
  await handleCoherenceAction.call(context, "open-entity-renames");
});

test("rename information icon uses the existing Home Assistant more-info action", async () => {
  const { handleAlertTableAction } = await import("../frontend-src/components/alert-table.js");
  const opened = [];
  const context = {
    _closeAlertDetailsDialog: (callback) => callback(),
    _openMoreInfo: (entityId) => opened.push(entityId),
  };
  const handled = await handleAlertTableAction.call(context, "more-info", {
    dataset: { entityId: "sensor.current" },
  }, { preventDefault() {}, stopPropagation() {} });
  assert.equal(handled, true);
  assert.deepEqual(opened, ["sensor.current"]);
});

test("entity export is below deleted entities before and after a coherence scan", async () => {
  const { renderCoherence } = await import("../frontend-src/views/coherence.js");
  for (const result of [null, { results: [] }]) {
    const markup = renderCoherence({ result, t: (key) => key, entityExportLoading: true });
    assert.ok(markup.indexOf('data-action="export-entities"') > markup.indexOf('data-action="open-deleted-entities"'));
    assert.match(markup, /data-action="export-entities" disabled/);
    assert.match(markup, /coherence.export.loading/);
  }
});

test("entity export downloads JSON once and releases busy state on success or failure", async () => {
  const { handleCoherenceAction } = await import("../frontend-src/views/coherence.js");
  const { AlertManagerApi } = await import("../frontend-src/api/transport.js");
  const originalDocument = globalThis.document;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  let resolveExport;
  let calls = 0;
  let downloaded = 0;
  let blob;
  let revoked;
  const link = { click() { downloaded += 1; } };
  const context = {
    _readOnly: false,
    _render() {},
    _refreshCoherenceData() {},
    _t: (key) => key,
    _api: new AlertManagerApi(() => ({
      callWS(message) {
        assert.deepEqual(message, { type: "alert_manager/coherence/entities/export" });
        calls += 1;
        return new Promise((resolve) => { resolveExport = resolve; });
      },
    })),
  };
  try {
    globalThis.document = { createElement(tag) { assert.equal(tag, "a"); return link; } };
    URL.createObjectURL = (value) => { blob = value; return "blob:export"; };
    URL.revokeObjectURL = (value) => { revoked = value; };
    await handleCoherenceAction.call(context, "download-entities");
    assert.equal(calls, 0);
    await handleCoherenceAction.call(context, "export-entities");
    assert.equal(context._entityExportOpen, true);
    assert.equal(calls, 0);
    await handleCoherenceAction.call(context, "close-entity-export");
    assert.equal(context._entityExportOpen, false);
    assert.equal(calls, 0);
    await handleCoherenceAction.call(context, "export-entities");
    const pending = handleCoherenceAction.call(context, "download-entities");
    assert.equal(context._entityExportOpen, false);
    assert.equal(context._entityExportLoading, true);
    await handleCoherenceAction.call(context, "download-entities");
    assert.equal(calls, 1);
    const content = '{"attributes":{"friendly_name":"<salon>"}}';
    resolveExport({ content, filename: "entities.json", content_type: "application/json;charset=utf-8" });
    await pending;
    assert.equal(context._entityExportLoading, false);
    assert.equal(downloaded, 1);
    assert.equal(link.download, "entities.json");
    assert.equal(blob.type, "application/json;charset=utf-8");
    assert.equal(await blob.text(), content);
    assert.equal(revoked, "blob:export");
    context._api = { exportEntities: async () => { throw new Error("offline"); } };
    await handleCoherenceAction.call(context, "export-entities");
    await handleCoherenceAction.call(context, "download-entities");
    assert.equal(context._entityExportLoading, false);
    assert.deepEqual(context._pageNotice, { kind: "error", text: "coherence.export.error" });
    assert.equal(downloaded, 1);
    context._readOnly = true;
    context._api = { exportEntities() { assert.fail("Read-only users cannot export"); } };
    await handleCoherenceAction.call(context, "export-entities");
    assert.equal(context._entityExportOpen, false);
    context._entityExportOpen = true;
    await handleCoherenceAction.call(context, "download-entities");
  } finally {
    globalThis.document = originalDocument;
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  }
});

test("entity export warning is escaped and shown before download with or without a scan", async () => {
  const { renderCoherence, hydrateEntityExport } = await import("../frontend-src/views/coherence.js");
  for (const result of [null, { results: [] }]) {
    const markup = renderCoherence({
      result,
      entityExportOpen: true,
      t: (key) => key === "coherence.export.warning" ? "Review <private> data" : key,
    });
    assert.match(markup, /<ha-dialog id="entity-export-dialog"/);
    assert.match(markup, /aria-describedby="entity-export-warning"/);
    assert.match(markup, /alert-type="warning">Review &lt;private&gt; data/);
    assert.match(markup, /data-action="download-entities"/);
    assert.match(markup, /data-action="close-entity-export"/);
  }
  const dialog = fakeDomElement("ha-dialog");
  const context = { _entityExportOpen: true, _hass: {}, _render() {} };
  const root = { querySelector: () => dialog };
  hydrateEntityExport(root, context);
  assert.equal(dialog.open, true);
  assert.equal(dialog.hass, context._hass);
  assert.equal(dialog.escapeKeyAction, "close");
  const closed = dialog.listeners.closed;
  hydrateEntityExport(root, context);
  assert.equal(dialog.listeners.closed, closed);
  closed();
  assert.equal(context._entityExportOpen, false);
});

const coherenceResult = () => ({
  results: [{
    entity_id: "sensor.missing_entity",
    source_type: "automation",
    source_name: "Thermostat : bureau",
    file: "automations.yaml",
    line: 42,
    link: { type: "navigate", path: "/config/automation/edit/123" },
  }],
  missing_count: 1,
  files_scanned: 4,
  files_skipped: 0,
  references_checked: 12,
  duration_ms: 8,
  scanned_at: "2026-08-28T12:00:00+00:00",
});

test("coherence narrow cell keeps entity primary and metadata secondary in selected order", () => {
  const panel = new Panel();
  panel._coherenceTableState = {
    search: "",
    columnOrder: ["entity", "file", "type", "source", "line", "action"],
    hiddenColumns: ["source"],
    sortBy: "entity",
    sortDirection: "asc",
    groupBy: "",
  };
  const cell = panel._nativeCoherenceEntityCell({
    entity: "sensor.missing_entity",
    type: "Automatisation",
    source: "Thermostat : bureau",
    file: "automations.yaml",
    line: "42",
  }, true);

  assert.equal(cell.children[0].textContent, "sensor.missing_entity");
  assert.equal(
    cell.children[1].textContent,
    "automations.yaml · Automatisation · 42",
  );
});

test("coherence result uses the native Home Assistant data-table toolbar without filters", () => {
  const panel = new Panel();
  panel._coherence = coherenceResult();
  const rendered = panel._renderCoherence();

  assert.match(rendered, /hass-tabs-subpage-data-table/);
  assert.match(rendered, /data-coherence-table-page/);
  assert.doesNotMatch(rendered, /has-filters/);
  assert.doesNotMatch(rendered, /\bclickable\b/);
});

test("coherence table exposes search, sorting, grouping and column settings", () => {
  const panel = new Panel();
  const tablePage = {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-coherence-table-page]" ? tablePage : null
  );
  panel._hass = {};
  panel._coherence = coherenceResult();
  panel.narrow = true;
  panel._hydrateCoherenceTable();

  assert.equal(tablePage.narrow, true);
  assert.equal(tablePage.clickable, false);
  assert.equal(tablePage.columns.entity.main, true);
  assert.equal(tablePage.columns.entity.groupable, true);
  assert.equal(tablePage.columns.entity.hideable, false);
  assert.equal(tablePage.columns.type.groupable, undefined);
  assert.equal(tablePage.columns.search_index.filterable, true);
  assert.deepEqual(
    tablePage.columnOrder,
    ["entity", "target", "type", "source", "file", "line", "action"],
  );
  assert.equal(tablePage.initialSorting.column, "entity");
  assert.equal(tablePage.initialSorting.direction, "asc");
  assert.equal(tablePage.initialGroupColumn, undefined);
  assert.equal(typeof tablePage.listeners["search-changed"], "function");
  assert.equal(typeof tablePage.listeners["sorting-changed"], "function");
  assert.equal(typeof tablePage.listeners["grouping-changed"], "function");
  assert.equal(typeof tablePage.listeners["columns-changed"], "function");

  tablePage.listeners["search-changed"]({ detail: { value: "thermostat" } });
  assert.equal(panel._coherenceTableState.search, "thermostat");

  tablePage.listeners["sorting-changed"]({
    detail: { column: "file", direction: "desc" },
  });
  assert.equal(panel._coherenceTableState.sortBy, "file");
  assert.equal(panel._coherenceTableState.sortDirection, "desc");

  tablePage.listeners["grouping-changed"]({ detail: { value: "entity" } });
  assert.equal(panel._coherenceTableState.groupBy, "entity");

  tablePage.listeners["columns-changed"]({
    detail: {
      columnOrder: ["entity", "line", "file", "type", "source", "action"],
      hiddenColumns: ["source"],
    },
  });
  assert.deepEqual(
    panel._coherenceTableState.columnOrder,
    ["entity", "line", "file", "type", "source", "action", "target"],
  );
  assert.deepEqual(panel._coherenceTableState.hiddenColumns, ["source"]);
});

test("coherence target and native checkboxes are available only for editable findings", async () => {
  const panel = new Panel();
  panel._hass = { user: { is_admin: true } };
  panel._coherence = coherenceResult();
  panel._coherence.results[0].correction_target = "sensor.current";
  panel._coherence.results.push({
    entity_id: "sensor.deleted", file: ".storage/core.config_entries", line: 1,
    source_type: "file", source_name: "Home Assistant",
  });
  const bulk = {};
  const nativeTable = { requestUpdate() { this.updated = true; } };
  const tablePage = {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    querySelector() { return bulk; },
    shadowRoot: { querySelector() { return nativeTable; } },
  };
  panel.shadowRoot.querySelector = () => tablePage;
  panel._render = () => assert.fail("Selection must not remount the table");
  panel._hydrateCoherenceTable();
  const [editable, deleted] = tablePage.data;
  assert.equal(editable.target, "sensor.current");
  assert.match(editable.search_index, /sensor.current/);
  assert.equal(editable.selectable, true);
  assert.equal(deleted.selectable, false);
  assert.equal(tablePage.selectable, true);
  const listener = tablePage.listeners["selection-changed"];
  listener({ detail: { value: [editable.id, deleted.id] } });
  assert.deepEqual([...panel._selectedCoherenceIds], [editable.id]);
  assert.equal(tablePage.selected, 1);
  assert.equal(bulk.disabled, false);
  panel._hydrateCoherenceTable();
  await Promise.resolve();
  assert.equal(tablePage.listeners["selection-changed"], listener);
  assert.deepEqual(nativeTable._checkedRows, [editable.id]);
  assert.equal(nativeTable.updated, true);
});

test("coherence mobile metadata includes the target and correct is available without an Open link", () => {
  const panel = new Panel();
  panel._hass = { user: { is_admin: true } };
  const row = {
    index: 0, entity: "sensor.old", target: "sensor.current", type: "File",
    source: "Source", file: "config.yaml", line: "4",
  };
  const cell = panel._nativeCoherenceEntityCell(row, true);
  assert.match(cell.children[1].textContent, /sensor.current/);
  const action = panel._nativeCoherenceActionCell(row);
  assert.equal(action.tagName, "HA-BUTTON");
  assert.equal(action.textContent, panel._t("coherence.correction.button"));
  assert.equal(typeof action.listeners.click, "function");
});

test("coherence opens the exact Home Assistant target only through the Open button", () => {
  const panel = new Panel();
  const tablePage = {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
  panel.shadowRoot.querySelector = (selector) => (
    selector === "[data-coherence-table-page]" ? tablePage : null
  );
  panel._hass = {};
  panel._coherence = coherenceResult();
  panel._hydrateCoherenceTable();

  let navigated = null;
  panel._navigate = (path, newTab) => { navigated = [path, newTab]; };
  assert.equal(tablePage.listeners["row-click"], undefined);
  const button = tablePage.columns.action.template(tablePage.data[0]);
  button.listeners.click({ stopPropagation() {} });
  assert.deepEqual(navigated, ["/config/automation/edit/123", true]);

  let moreInfo = null;
  panel._openMoreInfo = (entityId) => { moreInfo = entityId; };
  tablePage.data[0].link = { type: "more_info", entity_id: "sensor.template_result" };
  const moreInfoButton = tablePage.columns.action.template(tablePage.data[0]);
  moreInfoButton.listeners.click({ stopPropagation() {} });
  assert.equal(moreInfo, "sensor.template_result");
});

test("coherence keeps legacy entity reports and renders IEEE references with their source link", async () => {
  const { coherenceTableRows, coherenceStatsMarkup } = await import("../frontend-src/views/coherence.js");
  const context = {
    _coherence: {
      results: [
        { entity_id: "sensor.old", file: "a.yaml", line: 1, source_type: "automation" },
        { reference_type: "zha_device_ieee", reference: "5c:02:72:ff:fe:d9:be:ec", file: "a.yaml", line: 2,
          source_type: "automation", link: { type: "navigate", path: "/config/automation/edit/remote" } },
      ],
      checks: { zha_device_ieee: "not_loaded" },
    },
    _t: (key) => key,
  };
  const rows = coherenceTableRows.call(context);
  assert.equal(rows[0].entity, "sensor.old");
  assert.equal(rows[0].message, "");
  assert.equal(rows[1].entity, "5c:02:72:ff:fe:d9:be:ec");
  assert.equal(rows[1].message, "coherence.zha_missing");
  assert.equal(rows[1].link.type, "navigate");
  assert.match(coherenceStatsMarkup.call(context), /coherence.zha_status.not_loaded/);
  delete context._coherence.checks;
  assert.doesNotMatch(coherenceStatsMarkup.call(context), /coherence.zha_status/);
});

test("coherence Open uses the rule editor and respects read-only access", () => {
  const panel = new Panel();
  panel._hass = { user: { is_admin: true } };
  const opened = [];
  panel._openRuleEditor = (...args) => opened.push(args);
  const row = { link: { type: "custom_rule", path: "rule-1" } };
  panel._nativeCoherenceActionCell(row).listeners.click({ stopPropagation() {} });
  assert.deepEqual(opened, [["rule-1", { navigate: true }]]);
  panel._hass.user.is_admin = false;
  panel._nativeCoherenceActionCell(row).listeners.click({ stopPropagation() {} });
  assert.equal(opened.length, 1);
});
