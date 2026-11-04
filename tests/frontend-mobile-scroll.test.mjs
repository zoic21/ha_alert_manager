import assert from "node:assert/strict";
import test from "node:test";

test("mobile tables scroll as a page and follow filtered and collapsed native rows", async () => {
  const { syncMobileTableLayout, disconnectMobileTableLayout } = await import("../frontend-src/components/alert-table.js");
  const originalDocument = globalThis.document;
  globalThis.document = { createElement: () => ({ setAttribute() {} }) };
  const originalObserver = globalThis.MutationObserver;
  const observers = [];
  globalThis.MutationObserver = class {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(root, options) { this.root = root; this.options = options; }
    disconnect() { this.disconnected = true; }
  };
  const makeRoot = (query) => ({
    styles: [],
    querySelector(selector) {
      if (selector === "[data-mobile-table-layout-style]") return this.styles[0];
      return query(selector);
    },
    append(style) { this.styles.push(style); },
  });
  let items = [...Array(60).fill({}), { empty: true }];
  const tableRoot = makeRoot((selector) => selector === "lit-virtualizer" ? { items } : null);
  const values = new Map();
  const nativeTable = {
    shadowRoot: tableRoot,
    style: {
      getPropertyValue: (key) => values.get(key),
      setProperty: (key, value) => values.set(key, value),
    },
  };
  const pageRoot = makeRoot((selector) => selector === "ha-data-table" ? nativeTable : null);
  const page = { shadowRoot: pageRoot };
  const context = {
    _narrow: true,
    shadowRoot: {
      querySelector: (selector) => selector === "hass-tabs-subpage-data-table" ? page : null,
    },
  };
  try {
    await syncMobileTableLayout.call(context);
    assert.equal(nativeTable.autoHeight, true);
    assert.equal(values.get("--alert-manager-table-rows"), "60");
    assert.match(pageRoot.styles[0].textContent, /:host\(\[narrow\]\) ha-data-table\s*\{\s*height: auto;/);
    assert.match(tableRoot.styles[0].textContent, /overflow: visible !important/);
    items = [{ groupHeader: "sensor.a" }, {}, { groupHeader: "sensor.b" }, { empty: true }];
    observers[0].callback();
    assert.equal(values.get("--alert-manager-table-rows"), "3");
    items = [];
    observers[0].callback();
    assert.equal(values.get("--alert-manager-table-rows"), "1");
    await syncMobileTableLayout.call(context);
    assert.equal(observers[0].disconnected, true);
    assert.equal(pageRoot.styles.length, 1);
    assert.equal(tableRoot.styles.length, 1);
    context._narrow = false;
    await syncMobileTableLayout.call(context);
    assert.equal(observers[1].disconnected, true);
    assert.equal(nativeTable.autoHeight, false);
    assert.equal(context._mobileTableLayoutObserver, null);
    context._narrow = true;
    const pending = syncMobileTableLayout.call(context);
    disconnectMobileTableLayout.call(context);
    await pending;
    assert.equal(context._mobileTableLayoutObserver, null);
    context.shadowRoot.querySelector = () => null;
    await syncMobileTableLayout.call(context);
    assert.equal(context._mobileTableLayoutToken, null);
  } finally {
    disconnectMobileTableLayout.call(context);
    globalThis.MutationObserver = originalObserver;
    globalThis.document = originalDocument;
  }
});

test("all four table pages use the shared native scroll layout with their headers", async () => {
  const { renderAlertTable } = await import("../frontend-src/components/alert-table.js");
  const { renderOverview } = await import("../frontend-src/views/overview.js");
  const { renderHistory } = await import("../frontend-src/views/history.js");
  const { renderRules } = await import("../frontend-src/views/rules.js");
  const { renderCoherence } = await import("../frontend-src/views/coherence.js");
  const t = (key) => key;
  const tableContext = {
    _tableState: { overview: { columns: ["entity"] }, history: { columns: ["entity"] } },
    _tableColumns: () => ({ entity: {} }),
    _renderFilterPane: () => "",
    _selectedAlertIds: new Set(),
    _readOnly: true,
    _t: t,
  };
  const shared = {
    t, pageMessages: "", rows: [],
    renderAlertTable: (...args) => renderAlertTable.call(tableContext, ...args),
  };
  const pages = {
    overview: renderOverview({
      ...shared, selectedStatuses: [], durationText: String,
      alerts: { active_count: 0, pending_count: 0, tracked_count: 5 },
    }),
    history: renderHistory({ ...shared, readOnly: true, limit: 100 }),
    rules: renderRules({ ...shared, editorWidth: 560, editor: "", renderFacetFilter: () => "" }),
    coherence: renderCoherence({ ...shared, result: { results: [] } }),
  };
  for (const [name, markup] of Object.entries(pages)) {
    assert.equal((markup.match(/<hass-tabs-subpage-data-table\b/g) ?? []).length, 1, name);
    assert.match(markup, /slot="top-header"/, name);
  }
});

