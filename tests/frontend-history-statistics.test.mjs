import assert from "node:assert/strict";
import test from "node:test";
import { hydrateHistoryStatistics, handleHistoryAction, historyStatisticsNameCell } from "../frontend-src/views/history.js";
import { refreshHistory } from "../frontend-src/api/alert-manager-api.js";

function panel() {
  const table = {};
  const controls = new Map();
  const instance = {
    _activeTab: "history", _historyStatisticsOpen: true, isConnected: true,
    _hass: {}, _tabs: () => [], _t: (key) => key,
    _historyRuleName: (row) => row.rule_name || row.type,
    _historyDurationText: (value) => `${value}s`,
    _configureSelect: (id, options, value, changed) => { if (!controls.has(id)) controls.set(id, { options, value, changed }); },
    _refreshHistory: () => { instance.requests++; }, requests: 0,
    _refreshHistoryData() {}, _render() {},
    shadowRoot: { querySelector: (selector) => selector === "[data-history-statistics-page]" ? table : null },
    _history: { statistics: { days: 7, groups: {
      alert: [{ id: "a", name: "<unsafe>", rule_name: "Temperature", occurrences: 2, total_duration_seconds: 60, average_duration_seconds: 30 }],
      entity: [{ id: "sensor.a", name: "Probe", occurrences: 2, total_duration_seconds: 60, average_duration_seconds: 30 }],
    } } },
  };
  return { instance, controls, table };
}

test("statistics hydrate native numeric sorting, regroup locally and reject stale periods", () => {
  const { instance, controls, table } = panel();
  hydrateHistoryStatistics(instance.shadowRoot, instance);
  hydrateHistoryStatistics(instance.shadowRoot, instance);
  assert.equal(controls.size, 2);
  assert.equal(table.data[0].name, "<unsafe> · Temperature");
  assert.equal(table.columns.total.valueColumn, "total_duration_seconds");
  assert.equal(table.columns.average.valueColumn, "average_duration_seconds");
  assert.equal(table.data[0].average, "30s");
  controls.get("history-statistics-group").changed("entity");
  assert.equal(table.data[0].name, "Probe");
  assert.equal(instance.requests, 0);
  controls.get("history-statistics-period").changed("30");
  assert.equal(instance.requests, 1);
  assert.deepEqual(table.data, []);
  controls.get("history-statistics-period").changed("30");
  controls.get("history-statistics-period").changed("365");
  assert.equal(instance.requests, 1);
  controls.get("history-statistics-period").changed("7");
  assert.equal(instance.requests, 2);
  assert.equal(table.data[0].name, "Probe");
});

test("history requests ask for statistics only in the open History statistics view", async () => {
  for (const [tab, open, expected] of [["overview", true, false], ["history", false, false], ["history", true, true]]) {
    const { instance } = panel();
    instance._activeTab = tab;
    instance._historyStatisticsOpen = open;
    instance._historyStatisticsDays = 30;
    let request;
    instance._api = { call: async (message) => { request = message; return { events: [], retention_limit: 100 }; } };
    await refreshHistory.call(instance);
    assert.equal(request.statistics_days, expected ? 30 : undefined);
  }
});

test("statistics toggle returns to occurrences and requests fresh data", async () => {
  const { instance } = panel();
  await handleHistoryAction.call(instance, "toggle-history-statistics");
  assert.equal(instance._historyStatisticsOpen, false);
  assert.equal(instance.requests, 1);
});

test("mobile statistics expose occurrence and duration values safely", () => {
  const original = globalThis.document;
  globalThis.document = { createElement: () => ({ style: {}, children: [], append(child) { this.children.push(child); } }) };
  try {
    const cell = historyStatisticsNameCell({ name: "<script>", occurrences: 2, total: "1h", average: "30m" }, true, (key) => key);
    assert.equal(cell.children[0].textContent, "<script>");
    assert.match(cell.children.map((child) => child.textContent).join(" "), /2.*1h.*30m/);
  } finally { globalThis.document = original; }
});
