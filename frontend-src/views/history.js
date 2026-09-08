import { compactDurationText } from "../utils/formatting.js";
import { esc } from "../utils/escaping.js";

export function refreshHistoryData() {
    if (this._activeTab !== "history") return;
    if (this._historyStatisticsOpen && Number(this._historyConfig?.retention_limit ?? 100) !== 0
      && this.shadowRoot?.querySelector?.("[data-history-statistics-page]")) {
      hydrateHistoryStatistics(this.shadowRoot, this);
      this._refreshUiState();
      return;
    }
    const tablePage = this.shadowRoot?.querySelector?.('[data-alert-table-page="history"]');
    const historyEnabled = Number(
      this._historyConfig?.retention_limit ?? this._history?.retention_limit ?? 100,
    ) !== 0;
    if (!tablePage || !historyEnabled) {
      this._render();
      return;
    }
    this._refreshAlertTableData("history", tablePage);
    this._updateSelectionToolbar();
    this._refreshUiState();
}

export function renderHistory(context) {
    const { busy, limit, pageMessages, rows, renderAlertTable, t, statisticsOpen = false, statisticsDays = 7, statisticsFilter = null } = context;
    if (limit === 0) {
      return `<ha-card outlined class="history-empty"><div class="empty"><h2>${esc(t("history.disabled_title"))}</h2><p>${esc(t("history.disabled_help"))}</p><ha-button appearance="plain" data-action="open-history-settings">${esc(t("history.open_settings"))}</ha-button></div></ha-card>`;
    }
    const statisticsControls = statisticsOpen ? `
      <div class="history-statistics-dashboard">
      <div class="history-statistics-controls">
        <div class="history-statistics-period" role="group" aria-label="${esc(t("history.statistics.period"))}">
          ${[7, 30].map((days) => `<ha-button size="s" appearance="${days === statisticsDays ? "accent" : "plain"}" variant="brand" aria-pressed="${days === statisticsDays}" data-action="history-statistics-period" data-days="${days}">${esc(t("history.statistics.short_days", { days }))}</ha-button>`).join("")}
        </div>
        <ha-select id="history-statistics-group" label="${esc(t("history.statistics.group"))}"></ha-select>
      </div>
      <div class="history-statistics-summary" data-history-statistics-summary></div>
      </div>
      <div class="history-statistics-note">
        <span>${esc(t("history.statistics.retained"))}</span>
        <ha-icon-button data-action="history-statistics-help" label="${esc(t("history.statistics.about"))}" aria-label="${esc(t("history.statistics.about"))}" title="${esc(t("history.statistics.help"))}" aria-expanded="false"><ha-icon icon="mdi:information-outline"></ha-icon></ha-icon-button>
      </div>
      <ha-alert alert-type="info" data-history-statistics-help hidden>${esc(t("history.statistics.help"))}</ha-alert>` : "";
    const drilldown = !statisticsOpen && statisticsFilter ? `<div class="history-statistics-drilldown">
      <span>${esc(t("history.statistics.selection", { name: statisticsFilter.name, days: statisticsFilter.days }))}</span>
      <ha-button appearance="plain" data-action="clear-history-statistics-filter">${esc(t("table.filters.reset"))}</ha-button>
    </div>` : "";
    const header = `${pageMessages}<ha-card outlined class="panel history-panel">
      <div class="history-header">
        <div><h2>${esc(t(statisticsOpen ? "history.statistics.title" : "history.title"))}</h2></div>
        <div class="history-page-actions">
          <ha-button appearance="plain" data-action="toggle-history-statistics">${esc(t(statisticsOpen ? "history.statistics.back" : "history.statistics.title"))}</ha-button>
          ${statisticsOpen ? "" : `<ha-button appearance="plain" variant="danger" data-action="clear-history" ${busy || !rows.length ? "disabled" : ""}>${esc(t("settings.history_clear"))}</ha-button>`}
        </div>
      </div>
      ${statisticsControls}${drilldown}
    </ha-card>`;
    if (statisticsOpen) return `<hass-tabs-subpage-data-table id="panel-shell" data-history-statistics-page main-page clickable>
      <div slot="top-header" class="table-page-top">${header}</div>
    </hass-tabs-subpage-data-table>`;
    return renderAlertTable(
      "history",
      rows,
      header,
    );
}

export function renderHistoryPanel() {
    const limit = Number(this._historyConfig?.retention_limit
      ?? this._history?.retention_limit ?? 100);
    const events = Array.isArray(this._history?.events) ? this._history.events : [];
    return renderHistory({
      busy: this._busy,
      statisticsOpen: this._historyStatisticsOpen,
      statisticsDays: this._historyStatisticsDays ?? 7,
      statisticsFilter: this._historyStatisticsFilter,
      limit,
      pageMessages: this._renderPageMessages(),
      rows: this._tableRows("history", events),
      renderAlertTable: (...args) => this._renderAlertTable(...args),
      t: (key, replacements) => this._t(key, replacements),
    });
}

export function historyRuleName(event) {
    if (event.rule_name && event.rule_name !== event.type) return event.rule_name;
    const pack = this._packs.find((item) => item.id === event.type);
    return pack ? this._t(`packs.${pack.translation_key}.name`) : (event.rule_name || event.type);
}

export function historyConditionText(event) {
    if (event.condition_key) return this._conditionText(event);
    if (!event.source || !event.operator) return event.condition ?? "";
    const source = this._t(
      event.source === "attribute"
        ? "conditions.sources.attribute"
        : event.source === "attribute_variation"
        ? "conditions.sources.attribute_variation"
        : ["state_variation", "variation"].includes(event.source)
        ? "conditions.sources.state_variation"
        : "conditions.sources.state",
      { attribute: event.attribute ?? "" },
    );
    const expected = Array.isArray(event.comparison_value)
      ? event.comparison_value.join(" / ")
      : event.comparison_value;
    return `${source} ${this._t(`operators.${event.operator}`)} ${expected ?? ""}${event.unit ? ` ${event.unit}` : ""}`;
}

export async function handleHistoryAction(action, button) {
  if (action === "history-statistics-period") {
    const days = Number(button?.dataset.days);
    if (![7, 30].includes(days) || days === (this._historyStatisticsDays ?? 7)) return true;
    this._historyStatisticsDays = days;
    hydrateHistoryStatistics(this.shadowRoot, this);
    void this._refreshHistory();
    return true;
  }
  if (action === "history-statistics-help") {
    const help = this.shadowRoot.querySelector("[data-history-statistics-help]");
    if (help) {
      help.hidden = !help.hidden;
      button.setAttribute("aria-expanded", String(!help.hidden));
    }
    return true;
  }
  if (action === "clear-history-statistics-filter") {
    this._historyStatisticsFilter = null;
    this._render();
    return true;
  }
  if (action === "toggle-history-statistics") {
    this._historyStatisticsOpen = !this._historyStatisticsOpen;
    this._render();
    void this._refreshHistory();
    return true;
  }
  if (["clear-history", "delete-history", "delete-history-detail"].includes(action)) {
    if (this._busy) return true;
    const fromDetails = action === "delete-history-detail";
    const dialog = fromDetails ? this._alertDetailsDialog : null;
    if (fromDetails && dialog?.alertKind !== "history") return true;
    const deleting = action !== "clear-history";
    const eventIds = (this._history?.events ?? [])
      .filter((event) => fromDetails
        ? event.event_id === dialog.alertId
        : this._selectedHistoryIds.has(event.event_id))
      .map((event) => event.event_id);
    if (deleting && !eventIds.length) return true;
    if (!window.confirm(this._t(deleting
      ? "history.delete_confirm"
      : "settings.history_clear_confirm", { count: eventIds.length }))) return true;
    const result = await this._call(
      {
        type: deleting ? "alert_manager/history/delete" : "alert_manager/history/clear",
        confirmed: true,
        ...(deleting ? { event_ids: eventIds } : {}),
      },
      fromDetails ? "" : this._t(deleting ? "history.deleted" : "success.history_cleared"),
    );
    if (result) {
      this._history = result;
      if (fromDetails) {
        if (this._alertDetailsDialog === dialog) this._closeAlertDetailsDialog();
        this._pageNotice = { kind: "success", text: this._t("history.deleted") };
      }
      const tablePage = this.shadowRoot?.querySelector?.('[data-alert-table-page="history"]');
      tablePage?.shadowRoot?.querySelector?.("ha-data-table")?.select?.([...this._selectedHistoryIds], false);
      this._selectedHistoryIds.clear();
      this._refreshHistoryData();
      if (this._historyRefreshPromise || this._historyStatisticsOpen) await this._refreshHistory();
    }
    return true;
  }
  if (action === "open-history-settings") {
    this._activeTab = "settings";
    this._notice = null;
    window.history?.pushState?.(null, "", "/alert-manager/settings");
    this._render();
    return true;
  }
  return false;
}

export function hydrateHistoryStatistics(root, context) {
  const table = root?.querySelector?.("[data-history-statistics-page]");
  if (!table) return;
  const days = context._historyStatisticsDays ?? 7;
  const kind = context._historyStatisticsGroup ?? "alert";
  for (const button of root.querySelectorAll?.('[data-action="history-statistics-period"]') ?? []) {
    const selected = Number(button.dataset.days) === days;
    button.setAttribute("aria-pressed", String(selected));
    button.setAttribute("appearance", selected ? "accent" : "plain");
  }
  context._configureSelect("history-statistics-group", ["alert", "entity", "device", "integration", "rule"].map((value) => ({
    value, label: context._t(`history.statistics.${value}`),
  })), kind, (value) => {
    if (!["alert", "entity", "device", "integration", "rule"].includes(value)
      || value === (context._historyStatisticsGroup ?? "alert")) return;
    context._historyStatisticsGroup = value;
    hydrateHistoryStatistics(root, context);
  });
  table.hass = context._hass;
  table.narrow = Boolean(context._narrow);
  table.tabs = context._tabs();
  table.route = { prefix: "", path: "/alert-manager/history" };
  table.mainPage = true;
  table.id = "id";
  table.searchLabel = context._t("history.statistics.search");
  table.clickable = true;
  table.columnOrder = ["name", "occurrences", "total", "average"];
  if (!table.initialSorting) table.initialSorting = { column: "occurrences", direction: "desc" };
  table.columns = {
    name: {
      title: context._t(`history.statistics.${kind}`), main: true,
      sortable: true, filterable: true, minWidth: "220px", maxWidth: context._narrow ? undefined : "440px", flex: 1,
      template: (row) => historyStatisticsNameCell(row, context._narrow, (key) => context._t(key)),
    },
    occurrences: {
      title: context._t("history.statistics.occurrences"), type: "numeric",
      sortable: true, minWidth: "100px", maxWidth: "150px", flex: 0.5,
    },
    total: {
      title: context._t("history.statistics.total"), sortable: true,
      valueColumn: "total_duration_seconds", minWidth: "130px", maxWidth: "190px", flex: 0.6,
      template: (row) => historyStatisticsDurationCell(row.total, row.totalExact),
    },
    average: {
      title: context._t("history.statistics.average"), sortable: true,
      valueColumn: "average_duration_seconds", minWidth: "130px", maxWidth: "190px", flex: 0.6,
      template: (row) => historyStatisticsDurationCell(row.average, row.averageExact),
    },
  };
  const statistics = context._history?.statistics;
  const ready = statistics?.days === days;
  table.data = ready ? (statistics.groups[kind] ?? []).map((row) => {
    let name = row.name || row.id || context._t("history.statistics.unknown");
    if (kind === "rule") name = context._historyRuleName({ ...row, rule_name: row.name });
    const subtitle = kind === "alert" ? context._historyRuleName(row) : "";
    const icon = { alert: "mdi:alert-circle-outline", entity: "mdi:format-list-bulleted", device: "mdi:devices", integration: "mdi:puzzle-outline", rule: "mdi:format-list-checks" }[kind];
    return {
      ...row, name, subtitle, icon, search: `${name} ${subtitle} ${row.id}`,
      total: compactDurationText.call(context, row.total_duration_seconds),
      average: compactDurationText.call(context, row.average_duration_seconds),
      totalExact: context._historyDurationText(row.total_duration_seconds),
      averageExact: context._historyDurationText(row.average_duration_seconds),
    };
  }) : [];
  table.columns.search = { title: "", hidden: true, filterable: true };
  table.noDataText = context._t(ready ? "history.statistics.empty" : "loading");
  const summary = root.querySelector("[data-history-statistics-summary]");
  if (summary) summary.innerHTML = renderHistoryStatisticsSummary({
    statistics: ready ? statistics : null,
    t: (key) => context._t(key),
    duration: (seconds) => compactDurationText.call(context, seconds),
    exactDuration: (seconds) => context._historyDurationText(seconds),
  });
  // Keep one native row listener across data refreshes and regrouping.
  table._historyStatisticsOpenRow = (id) => {
    const row = table.data.find((item) => String(item.id) === String(id));
    if (!row || !ready) return;
    context._resetTableFilters("history");
    context._tableState.history.search = "";
    context._selectedHistoryIds.clear();
    context._historyStatisticsFilter = {
      kind, id: row.id, name: row.name, days,
      from: statistics.from, to: statistics.to,
    };
    context._historyStatisticsOpen = false;
    context._render();
  };
  if (!table._historyStatisticsRowListener) {
    table.addEventListener("row-click", (event) => table._historyStatisticsOpenRow(event.detail?.id));
    table._historyStatisticsRowListener = true;
  }
}

export function renderHistoryStatisticsSummary({ statistics, t, duration, exactDuration }) {
  const devices = statistics?.groups.device?.filter((row) => row.id).length ?? 0;
  const items = [
    ["occurrences", statistics?.occurrences ?? 0],
    ["devices", devices],
    ["cumulative", statistics ? duration(statistics.total_duration_seconds) : "—"],
  ];
  return `<dl>${items.map(([key, value]) => `<div><dt>${esc(t(`history.statistics.${key}`))}</dt><dd${key === "cumulative" && statistics ? ` title="${esc(exactDuration(statistics.total_duration_seconds))}"` : ""}>${statistics ? esc(value) : "—"}</dd></div>`).join("")}</dl>`;
}

export function historyStatisticsDurationCell(value, exact) {
  if (!globalThis.document?.createElement) return value;
  const cell = document.createElement("span");
  cell.textContent = value;
  cell.title = exact;
  cell.style.cssText = "font-variant-numeric:tabular-nums";
  return cell;
}

export function historyStatisticsNameCell(row, narrow, t) {
  if (!globalThis.document?.createElement) return row.name;
  const cell = document.createElement("div");
  cell.style.cssText = "display:flex;align-items:center;gap:12px;min-width:0";
  const icon = document.createElement("ha-icon");
  icon.icon = row.icon;
  icon.style.cssText = "flex:none;color:var(--secondary-text-color);--mdc-icon-size:24px";
  const content = document.createElement("div");
  content.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";
  const name = document.createElement("span");
  name.textContent = row.name;
  name.title = row.name;
  name.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500";
  content.append(name);
  if (row.subtitle) {
    const subtitle = document.createElement("small");
    subtitle.textContent = row.subtitle;
    subtitle.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--secondary-text-color)";
    content.append(subtitle);
  }
  if (narrow) {
    const metrics = document.createElement("small");
    metrics.textContent = `${row.occurrences} ${t("history.statistics.occurrences").toLocaleLowerCase()} · ${row.total}`;
    metrics.title = `${t("history.statistics.average")}: ${row.averageExact}`;
    metrics.style.cssText = "color:var(--secondary-text-color)";
    content.append(metrics);
  }
  cell.append(icon, content);
  return cell;
}

export function matchesHistoryStatisticsFilter(entry, filter) {
  if (!filter) return true;
  const field = { alert: "id", entity: "entity_id", device: "device_id", integration: "integration", rule: "rule_id" }[filter.kind];
  if (!field || (entry[field] || "") !== filter.id) return false;
  const start = Date.parse(filter.from);
  const end = Date.parse(filter.to);
  const active = Date.parse(entry.active_at);
  const resolved = Date.parse(entry.resolved_at);
  return [start, end, active, resolved].every(Number.isFinite)
    && active < end && resolved >= start && !(resolved === start && active < start);
}
