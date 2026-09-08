import assert from "node:assert/strict";
import test from "node:test";
import { hydrateHistoryStatistics, handleHistoryAction, historyStatisticsNameCell, matchesHistoryStatisticsFilter, renderHistoryStatisticsSummary } from "../frontend-src/views/history.js";
import { compactDurationText } from "../frontend-src/utils/formatting.js";
import { refreshHistory } from "../frontend-src/api/alert-manager-api.js";

function panel() {
  const table = { listeners: new Map(), addEventListener(name, callback) { this.listeners.set(name, callback); } };
  const controls = new Map();
  const instance = {
    _activeTab: "history", _historyStatisticsOpen: true, isConnected: true,
    _hass: {}, _tabs: () => [], _t: (key, values) => key.startsWith("duration.") ? `${values.count}${({ days: "d", hours: "h", minutes: "m", seconds: "s" })[key.split(".")[1]]}` : key,
    _historyRuleName: (row) => row.rule_name || row.type,
    _historyDurationText: (value) => `${value}s`,
    _configureSelect: (id, options, value, changed) => { if (!controls.has(id)) controls.set(id, { options, value, changed }); },
    _refreshHistory: () => { instance.requests++; }, requests: 0,
    _refreshHistoryData() {}, _render() {},
    shadowRoot: { querySelector: (selector) => selector === "[data-history-statistics-page]" ? table : null },
    _history: { statistics: { days: 7, from: "2026-09-01T12:00:00Z", to: "2026-09-08T12:00:00Z", groups: {
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
  assert.equal(controls.size, 1);
  assert.deepEqual(table.initialSorting, { column: "occurrences", direction: "desc" });
  assert.equal(table.listeners.size, 1);
  assert.equal(table.data[0].name, "<unsafe>");
  assert.equal(table.data[0].subtitle, "Temperature");
  assert.equal(table.columns.total.valueColumn, "total_duration_seconds");
  assert.equal(table.columns.average.valueColumn, "average_duration_seconds");
  assert.equal(table.data[0].average, "30s");
  controls.get("history-statistics-group").changed("entity");
  assert.equal(table.data[0].name, "Probe");
  assert.equal(instance.requests, 0);
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "30" } });
  assert.equal(instance.requests, 1);
  assert.deepEqual(table.data, []);
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "30" } });
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "365" } });
  assert.equal(instance.requests, 1);
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "7" } });
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

test("mobile statistics show compact metrics and preserve exact duration help", () => {
  const original = globalThis.document;
  globalThis.document = { createElement: (tag) => ({ tag, style: {}, children: [], append(...children) { this.children.push(...children); } }) };
  try {
    const cell = historyStatisticsNameCell({ name: "<script>", subtitle: "Temperature", icon: "mdi:alert", occurrences: 2, total: "1h", averageExact: "30m" }, true, (key) => key);
    assert.equal(cell.children[0].tag, "ha-icon");
    const lines = cell.children[1].children;
    assert.equal(lines[0].textContent, "<script>");
    assert.equal(lines[1].textContent, "Temperature");
    assert.match(lines[2].textContent, /2.*1h/);
    assert.match(lines[2].title, /30m/);
  } finally { globalThis.document = original; }
});

test("durations use two significant components without losing full precision elsewhere", () => {
  const { instance } = panel();
  assert.equal(compactDurationText.call(instance, 4 * 86400 + 4 * 3600 + 43 * 60 + 29), "4d 4h");
  assert.equal(compactDurationText.call(instance, 3601), "1h 1s");
  assert.equal(compactDurationText.call(instance, 0), "0s");
  assert.equal(compactDurationText.call(instance, -1), "0s");
  assert.equal(compactDurationText.call(instance, 59.8), "1m");
});

test("summary counts known devices once and shows missing data as pending", () => {
  const args = { t: (key) => key, duration: () => "4d 4h", exactDuration: () => "4d 4h 43m 29s" };
  const html = renderHistoryStatisticsSummary({ ...args, statistics: {
    occurrences: 14, total_duration_seconds: 1,
    groups: { device: [{ id: "d1" }, { id: "" }, { id: "d2" }] },
  } });
  assert.match(html, /<dd>14<\/dd>/);
  assert.match(html, /<dd>2<\/dd>/);
  assert.match(html, /title="4d 4h 43m 29s">4d 4h/);
  assert.equal((renderHistoryStatisticsSummary({ ...args, statistics: null }).match(/—/g) ?? []).length, 3);
});

test("drilldown matches stable identifiers and exactly the backend overlap period", () => {
  const entry = { id: "a", entity_id: "sensor.a", device_id: "d1", rule_id: "r1", integration: "mqtt", active_at: "2026-08-29T12:00:00Z", resolved_at: "2026-09-02T12:00:00Z" };
  const period = { from: "2026-09-01T12:00:00Z", to: "2026-09-08T12:00:00Z" };
  for (const [kind, id] of [["alert", "a"], ["entity", "sensor.a"], ["device", "d1"], ["rule", "r1"], ["integration", "mqtt"]]) {
    const filter = { ...period, kind, id };
    assert.equal(matchesHistoryStatisticsFilter(entry, filter), true);
    assert.equal(matchesHistoryStatisticsFilter(entry, { ...filter, id: "different" }), false);
    assert.equal(matchesHistoryStatisticsFilter({ ...entry, resolved_at: period.from }, filter), false);
    assert.equal(matchesHistoryStatisticsFilter({ ...entry, active_at: period.from, resolved_at: period.from }, filter), true);
    assert.equal(matchesHistoryStatisticsFilter({ ...entry, active_at: period.to }, filter), false);
    assert.equal(matchesHistoryStatisticsFilter({ ...entry, active_at: "invalid" }, filter), false);
  }
  assert.equal(matchesHistoryStatisticsFilter(entry, null), true);
  assert.equal(matchesHistoryStatisticsFilter({ ...entry, device_id: null }, { ...period, kind: "device", id: "" }), true);
});

test("clicking a ranking clears old filters and opens its exact period; reset removes it", async () => {
  const { instance, table } = panel();
  instance._tableState = { history: { search: "old search" } };
  instance._selectedHistoryIds = new Set(["old"]);
  let reset = false;
  instance._resetTableFilters = () => { reset = true; };
  hydrateHistoryStatistics(instance.shadowRoot, instance);
  table.listeners.get("row-click")({ detail: { id: "a" } });
  assert.equal(reset, true);
  assert.equal(instance._tableState.history.search, "");
  assert.equal(instance._selectedHistoryIds.size, 0);
  assert.equal(instance._historyStatisticsOpen, false);
  assert.deepEqual(instance._historyStatisticsFilter, {
    kind: "alert", id: "a", name: "<unsafe>", days: 7,
    from: "2026-09-01T12:00:00Z", to: "2026-09-08T12:00:00Z",
  });
  await handleHistoryAction.call(instance, "clear-history-statistics-filter");
  assert.equal(instance._historyStatisticsFilter, null);
});
