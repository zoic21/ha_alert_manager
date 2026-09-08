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
    const { busy, limit, pageMessages, rows, renderAlertTable, t, statisticsOpen = false } = context;
    if (limit === 0) {
      return `<ha-card outlined class="history-empty"><div class="empty"><h2>${esc(t("history.disabled_title"))}</h2><p>${esc(t("history.disabled_help"))}</p><ha-button appearance="plain" data-action="open-history-settings">${esc(t("history.open_settings"))}</ha-button></div></ha-card>`;
    }
    const statisticsControls = statisticsOpen ? `
      <div class="history-statistics-controls">
        <ha-select id="history-statistics-period" label="${esc(t("history.statistics.period"))}"></ha-select>
        <ha-select id="history-statistics-group" label="${esc(t("history.statistics.group"))}"></ha-select>
      </div>
      <p>${esc(t("history.statistics.help"))}</p>` : "";
    const header = `${pageMessages}<ha-card outlined class="panel history-panel">
      <div class="history-header">
        <div><h2>${esc(t(statisticsOpen ? "history.statistics.title" : "history.title"))}</h2></div>
        <div class="history-page-actions">
          <ha-button appearance="plain" data-action="toggle-history-statistics">${esc(t(statisticsOpen ? "history.title" : "history.statistics.title"))}</ha-button>
          ${statisticsOpen ? "" : `<ha-button appearance="plain" variant="danger" data-action="clear-history" ${busy || !rows.length ? "disabled" : ""}>${esc(t("settings.history_clear"))}</ha-button>`}
        </div>
      </div>
      ${statisticsControls}
    </ha-card>`;
    if (statisticsOpen) return `<hass-tabs-subpage-data-table id="panel-shell" data-history-statistics-page main-page>
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

export async function handleHistoryAction(action) {
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
  context._configureSelect("history-statistics-period", [7, 30].map((value) => ({
    value: String(value), label: context._t("history.statistics.days", { days: value }),
  })), String(days), (selected) => {
    const value = Number(selected);
    if (![7, 30].includes(value) || value === (context._historyStatisticsDays ?? 7)) return;
    context._historyStatisticsDays = value;
    hydrateHistoryStatistics(root, context);
    void context._refreshHistory();
  });
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
  table.searchLabel = context._t("table.search");
  if (!table.initialSorting) table.initialSorting = { column: "occurrences", direction: "desc" };
  table.columns = {
    name: { title: context._t(`history.statistics.${kind}`), main: true, sortable: true, filterable: true, minWidth: "180px", flex: 2, template: (row) => historyStatisticsNameCell(row, context._narrow, (key) => context._t(key)) },
    occurrences: { title: context._t("history.statistics.occurrences"), type: "numeric", sortable: true, minWidth: "100px", flex: 1 },
    total: { title: context._t("history.statistics.total"), sortable: true, valueColumn: "total_duration_seconds", minWidth: "120px", flex: 1 },
    average: { title: context._t("history.statistics.average"), sortable: true, valueColumn: "average_duration_seconds", minWidth: "120px", flex: 1 },
  };
  const statistics = context._history?.statistics;
  const ready = statistics?.days === days;
  table.data = ready ? (statistics.groups[kind] ?? []).map((row) => {
    const ruleName = context._historyRuleName(row);
    let name = row.name || row.id || context._t("history.statistics.unknown");
    if (kind === "rule") name = context._historyRuleName({ ...row, rule_name: row.name });
    if (kind === "alert") name = `${name} · ${ruleName}`;
    return { ...row, name, total: context._historyDurationText(row.total_duration_seconds), average: context._historyDurationText(row.average_duration_seconds) };
  }) : [];
  table.noDataText = context._t(ready ? "history.empty" : "loading");
}

export function historyStatisticsNameCell(row, narrow, t) {
  if (!narrow || !globalThis.document?.createElement) return row.name;
  const cell = document.createElement("div");
  cell.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";
  const name = document.createElement("div");
  name.textContent = row.name;
  cell.append(name);
  for (const [key, value] of [["occurrences", row.occurrences], ["total", row.total], ["average", row.average]]) {
    const line = document.createElement("small");
    line.textContent = `${t(`history.statistics.${key}`)}: ${value}`;
    line.style.cssText = "color:var(--secondary-text-color);font-size:12px";
    cell.append(line);
  }
  return cell;
}
