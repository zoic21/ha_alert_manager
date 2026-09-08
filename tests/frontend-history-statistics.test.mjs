import assert from "node:assert/strict";
import test from "node:test";
import { hydrateHistoryStatistics, handleHistoryAction, renderHistoryStatisticsLeaders, openHistoryStatisticsGroup, renderHistoryStatisticsSummary } from "../frontend-src/views/history.js";
import { activePeriodMatches, historyFacetOptions } from "../frontend-src/components/alert-table.js";
import { compactDurationText } from "../frontend-src/utils/formatting.js";
import { refreshHistory } from "../frontend-src/api/alert-manager-api.js";

function panel() {
  const table = { listeners: new Map(), addEventListener(name, callback) { this.listeners.set(name, callback); } };
  const controls = new Map();
  const summary = {};
  const leaders = {};
  const instance = {
    _activeTab: "history", _historyStatisticsOpen: true, isConnected: true,
    _hass: {}, _tabs: () => [], _t: (key, values) => key.startsWith("duration.") ? `${values.count}${({ days: "d", hours: "h", minutes: "m", seconds: "s" })[key.split(".")[1]]}` : key,
    _integrationLabel: (id) => id,
    _historyRuleName: (row) => row.rule_name || row.type,
    _historyDurationText: (value) => `${value}s`,
    _configureSelect: (id, options, value, changed) => { if (!controls.has(id)) controls.set(id, { options, value, changed }); },
    _refreshHistory: () => { instance.requests++; }, requests: 0,
    _refreshHistoryData() {}, _render() {},
    shadowRoot: { querySelector: (selector) => selector === "[data-history-statistics-page]" ? table : selector === "[data-history-statistics-summary]" ? summary : selector === "[data-history-statistics-leaders]" ? leaders : null },
    _history: { statistics: { days: 7, from: "2026-09-01T12:00:00Z", to: "2026-09-08T12:00:00Z", groups: {
      alert: [{ id: "a", name: "<unsafe>", rule_name: "Temperature", occurrences: 2, total_duration_seconds: 60, average_duration_seconds: 30 }],
      entity: [{ id: "sensor.a", name: "Probe", occurrences: 2, total_duration_seconds: 60, average_duration_seconds: 30 }],
    } } },
  };
  return { instance, controls, table, summary, leaders };
}

test("statistics refresh cards in place and reject stale periods", () => {
  const { instance, summary, leaders } = panel();
  hydrateHistoryStatistics(instance.shadowRoot, instance);
  const original = leaders.innerHTML;
  assert.match(original, /Probe/);
  hydrateHistoryStatistics(instance.shadowRoot, instance);
  assert.equal(leaders.innerHTML, original);
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "30" } });
  assert.equal(instance.requests, 1);
  assert.doesNotMatch(leaders.innerHTML, /Probe/);
  assert.match(leaders.innerHTML, /loading/);
  assert.match(summary.innerHTML, /—/);
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "30" } });
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "365" } });
  assert.equal(instance.requests, 1);
  handleHistoryAction.call(instance, "history-statistics-period", { dataset: { days: "7" } });
  assert.equal(instance.requests, 2);
  assert.equal(leaders.innerHTML, original);
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

test("new ranking cards use the matching native history facets", () => {
  const { instance } = panel();
  instance._tableState = { history: { filters: {} } };
  instance._selectedHistoryIds = new Set();
  instance._resetTableFilters = () => { instance._tableState.history.filters = {}; };
  for (const [kind, facet] of [["pack", "rule"], ["custom_rule", "rule"], ["profile", "profile"]]) {
    instance._history.statistics.groups[kind] = [{ id: "stable", name: "Name" }];
    openHistoryStatisticsGroup(instance, kind, "stable");
    assert.deepEqual(instance._tableState.history.filters[facet], ["id:stable"]);
  }
});

test("associated profiles have a single occurrence ranking and stable filter options", () => {
  const statistics = { groups: { profile: [{ id: "p1", name: "<Profile>", occurrences: 3 }] } };
  const html = renderHistoryStatisticsLeaders({ statistics, t: (key) => key });
  const card = html.slice(html.indexOf("history.statistics.top_profile"));
  assert.match(card, /history.statistics.associated/);
  assert.match(card, /&lt;Profile&gt;/);
  assert.doesNotMatch(card, /history.statistics.longest/);
  const rows = [{ source: { notifications: { alert: { profiles: { p1: "Same" } }, resolved: { profiles: { p1: "Same", p2: "Same" } } } } }];
  assert.deepEqual(historyFacetOptions(rows, "profile", (key) => key), [
    { value: "id:p1", label: "Same" }, { value: "id:p2", label: "Same" },
  ]);
});

test("mobile history actions occupy two columns without affecting statistics cards", async () => {
  const { responsiveStyles } = await import("../frontend-src/styles/responsive-styles.js");
  assert.match(responsiveStyles, /:host\(\[narrow\]\) \.history-panel \.history-page-actions \{\s*grid-template-columns: minmax\(0, 1fr\) minmax\(0, 1\.4fr\);/);
  assert.match(responsiveStyles, /\.history-page-actions ha-button::part\(label\) \{\s*white-space: normal;/);
});

test("statistics toggle returns to occurrences and requests fresh data", async () => {
  const { instance } = panel();
  await handleHistoryAction.call(instance, "toggle-history-statistics");
  assert.equal(instance._historyStatisticsOpen, false);
  assert.equal(instance.requests, 1);
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
    groups: { device: [{ id: "d1" }, { id: "" }, { id: "d2" }], entity: [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "" }] },
  } });
  assert.match(html, /<dd>14<\/dd>/);
  assert.match(html, /<dd>2<\/dd>/);
  assert.match(html, /<dd>3<\/dd>/);
  assert.match(html, /title="4d 4h 43m 29s">4d 4h/);
  assert.equal((renderHistoryStatisticsSummary({ ...args, statistics: null }).match(/—/g) ?? []).length, 4);
});

test("native active-period filter preserves backend overlap and supports one-sided ranges", () => {
  const from = "2026-09-01T12:00:00Z";
  const to = "2026-09-08T12:00:00Z";
  const earlier = "2026-08-29T12:00:00Z";
  const within = "2026-09-02T12:00:00Z";
  assert.equal(activePeriodMatches(earlier, within, from, to), true);
  assert.equal(activePeriodMatches(earlier, from, from, to), false);
  assert.equal(activePeriodMatches(from, from, from, to), true);
  assert.equal(activePeriodMatches(to, to, from, to), false);
  assert.equal(activePeriodMatches("invalid", within, from, to), false);
  assert.equal(activePeriodMatches(earlier, within, from, ""), true);
  assert.equal(activePeriodMatches(earlier, within, "", to), true);
  assert.equal(activePeriodMatches(earlier, earlier, "", ""), true);
});

test("clicking a ranking clears old filters and sets native facets and active period", () => {
  const { instance, table } = panel();
  instance._tableState = { history: { search: "old search", filters: {} } };
  instance._selectedHistoryIds = new Set(["old"]);
  let reset = false;
  instance._resetTableFilters = () => { reset = true; };
  hydrateHistoryStatistics(instance.shadowRoot, instance);
  handleHistoryAction.call(instance, "history-statistics-leader", { dataset: { kind: "entity", id: "sensor.a" } });
  assert.equal(reset, true);
  assert.equal(instance._tableState.history.search, "");
  assert.equal(instance._selectedHistoryIds.size, 0);
  assert.equal(instance._historyStatisticsOpen, false);
  assert.deepEqual(instance._tableState.history.filters, {
    entity: ["id:sensor.a"], activeFrom: "2026-09-01T12:00:00Z", activeTo: "2026-09-08T12:00:00Z",
  });
});

test("all ranking categories use native stable-identity facets, including missing metadata", () => {
  const { instance } = panel();
  instance._tableState = { history: { filters: {} } };
  instance._selectedHistoryIds = new Set();
  instance._resetTableFilters = () => { instance._tableState.history.filters = {}; };
  for (const [kind, field] of [["entity", "entity_id"], ["device", "device_id"], ["rule", "rule_id"], ["integration", "integration"]]) {
    for (const id of ["stable-id", ""]) {
      instance._history.statistics.groups[kind] = [{ id, name: "Same name" }];
      openHistoryStatisticsGroup(instance, kind, id);
      assert.deepEqual(instance._tableState.history.filters[kind], [`id:${id}`]);
      const options = historyFacetOptions([{ source: { [field]: id } }], kind, () => "Unknown");
      assert.equal(options[0].value, `id:${id}`);
    }
  }
});

test("top fives sort independently without mutating data and escape names", () => {
  const rows = Array.from({ length: 7 }, (_, i) => ({ id: `id${i}`, name: i === 0 ? "<Probe>" : `Probe${i}`, occurrences: i + 1, total_duration_seconds: (7 - i) * 100 }));
  const statistics = { groups: { entity: [{ id: "", occurrences: 999 }, ...rows], device: [], integration: [{ id: "mqtt", occurrences: 1, total_duration_seconds: 10 }] } };
  const before = JSON.stringify(statistics);
  const args = { t: (key) => key, integrationLabel: () => "MQTT", duration: (n) => `${n}s`, exactDuration: (n) => `${n} seconds` };
  const html = renderHistoryStatisticsLeaders({ ...args, statistics });
  assert.equal(JSON.stringify(statistics), before);
  assert.equal((html.match(/<ha-card/g) ?? []).length, 6);
  const lists = [...html.matchAll(/<ol>(.*?)<\/ol>/gs)].map((match) => match[1]);
  assert.equal((lists[0].match(/<li>/g) ?? []).length, 5);
  assert.ok(lists[0].indexOf('data-id="id6"') < lists[0].indexOf('data-id="id5"'));
  assert.doesNotMatch(lists[0], /data-id="id0"/);
  assert.ok(lists[1].indexOf('data-id="id0"') < lists[1].indexOf('data-id="id1"'));
  assert.match(lists[1], /&lt;Probe&gt;/);
  assert.match(lists[1], /700 seconds/);
  assert.match(html, /MQTT/);
  assert.match(html, /history.statistics.empty/);
  assert.doesNotMatch(html, /data-id=""/);
  assert.match(renderHistoryStatisticsLeaders({ ...args, statistics: null }), /loading/);
});

test("statistics cards have no internal scroller or native data table", async () => {
  const { responsiveStyles } = await import("../frontend-src/styles/responsive-styles.js");
  const { settingsStyles } = await import("../frontend-src/styles/settings-styles.js");
  const { renderHistory } = await import("../frontend-src/views/history.js");
  const html = renderHistory({ limit: 100, rows: [], pageMessages: "", statisticsOpen: true, t: (key) => key });
  assert.match(html, /data-history-statistics-page/);
  assert.doesNotMatch(html, /hass-tabs-subpage-data-table|top-header|history-statistics-group/);
  for (const css of [responsiveStyles, settingsStyles]) {
    for (const rule of css.matchAll(/[^{}]*history-statistics[^{}]*\{([^}]*)\}/g)) {
      assert.doesNotMatch(rule[1], /overflow-y:|max-height:|height:/);
    }
  }
  assert.match(responsiveStyles, /history-statistics-ranking \{\s*width: 100%/);
});

test("desktop statistics center the dashboard and align ranking sections without fixed row heights", async () => {
  const { settingsStyles } = await import("../frontend-src/styles/settings-styles.js");
  const rules = [...settingsStyles.matchAll(/([^{}]+)\{([^}]*)\}/g)];
  const desktop = (selector) => rules.find(([, name]) => name.replace(/\/\*[\s\S]*?\*\//g, "").trim() === `:host(:not([narrow])) ${selector}`)?.[2] ?? "";
  assert.match(desktop("[data-history-statistics-page]"), /max-width: 1400px/);
  assert.match(desktop("[data-history-statistics-page]"), /margin-inline: auto/);
  assert.match(desktop("[data-history-statistics-page]"), /repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(desktop(".history-statistics-summary dl"), /repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(desktop(".history-statistics-cards"), /display: contents/);
  assert.match(desktop(".history-statistics-ranking"), /grid-template-rows: subgrid/);
  assert.match(desktop(".history-statistics-ranking"), /grid-row: span 3/);
  assert.doesNotMatch(desktop(".history-statistics-ranking"), /height:/);
});

test("period controls and summary share one card on desktop and mobile without a visible statistics title", async () => {
  const { renderHistory } = await import("../frontend-src/views/history.js");
  const html = renderHistory({ limit: 100, rows: [], pageMessages: "", statisticsOpen: true, t: (key) => key });
  const banner = html.match(/<ha-card[^>]*history-statistics-banner[^>]*>(.*?)<\/ha-card>/s)?.[1];
  assert.ok(banner);
  assert.match(banner, /history-statistics-period/);
  assert.match(banner, /history.statistics.back/);
  assert.match(banner, /data-history-statistics-summary/);
  assert.ok(banner.indexOf("history-statistics-period") < banner.indexOf("history.statistics.back"));
  assert.doesNotMatch(banner, /<h2>|history.statistics.title/);
  assert.equal((html.match(/data-history-statistics-summary/g) ?? []).length, 1);
});
