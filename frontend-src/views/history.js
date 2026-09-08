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
    const { busy, limit, pageMessages, rows, renderAlertTable, t, statisticsOpen = false, statisticsDays = 7 } = context;
    if (limit === 0) {
      return `<ha-card outlined class="history-empty"><div class="empty"><h2>${esc(t("history.disabled_title"))}</h2><p>${esc(t("history.disabled_help"))}</p><ha-button appearance="plain" data-action="open-history-settings">${esc(t("history.open_settings"))}</ha-button></div></ha-card>`;
    }
    const statisticsControls = statisticsOpen ? `
      <div class="history-statistics-period" role="group" aria-label="${esc(t("history.statistics.period"))}">
        <span>${esc(t("history.statistics.period"))}</span>
        ${[7, 30].map((days) => `<ha-button size="s" appearance="${days === statisticsDays ? "accent" : "plain"}" variant="brand" aria-pressed="${days === statisticsDays}" data-action="history-statistics-period" data-days="${days}">${esc(t("history.statistics.short_days", { days }))}</ha-button>`).join("")}
      </div>` : "";
    if (statisticsOpen) return `<section data-history-statistics-page aria-label="${esc(t("history.statistics.title"))}">
      <ha-card outlined class="panel history-statistics-banner">
        <div class="history-statistics-toolbar">
          ${statisticsControls}
          <ha-button size="s" appearance="plain" data-action="toggle-history-statistics">${esc(t("history.statistics.back"))}</ha-button>
        </div>
        <div class="history-statistics-summary" data-history-statistics-summary></div>
      </ha-card>
      <div class="history-statistics-cards">
        <div class="history-statistics-leaders" data-history-statistics-leaders></div>
      </div>
    </section>`;
    const header = `${pageMessages}<ha-card outlined class="panel history-panel">
      <div class="history-header">
        <div><h2>${esc(t("history.title"))}</h2></div>
        <div class="history-page-actions">
          <ha-button appearance="plain" data-action="toggle-history-statistics">${esc(t("history.statistics.title"))}</ha-button>
          <ha-button appearance="plain" variant="danger" data-action="clear-history" ${busy || !rows.length ? "disabled" : ""}>${esc(t("settings.history_clear"))}</ha-button>
        </div>
      </div>
    </ha-card>`;
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
  if (action === "history-statistics-leader") {
    openHistoryStatisticsGroup(this, button?.dataset.kind, button?.dataset.id);
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
  if (!root?.querySelector?.("[data-history-statistics-page]")) return;
  const days = context._historyStatisticsDays ?? 7;
  for (const button of root.querySelectorAll?.('[data-action="history-statistics-period"]') ?? []) {
    const selected = Number(button.dataset.days) === days;
    button.setAttribute("aria-pressed", String(selected));
    button.setAttribute("appearance", selected ? "accent" : "plain");
  }
  const statistics = context._history?.statistics;
  const ready = statistics?.days === days;
  const summary = root.querySelector("[data-history-statistics-summary]");
  if (summary) summary.innerHTML = renderHistoryStatisticsSummary({
    statistics: ready ? statistics : null,
    t: (key) => context._t(key),
    duration: (seconds) => compactDurationText.call(context, seconds),
    exactDuration: (seconds) => context._historyDurationText(seconds),
  });
  const leaders = root.querySelector("[data-history-statistics-leaders]");
  if (leaders) leaders.innerHTML = renderHistoryStatisticsLeaders({
    statistics: ready ? statistics : null,
    t: (key, values) => context._t(key, values),
    integrationLabel: (id) => context._integrationLabel(id),
    duration: (seconds) => compactDurationText.call(context, seconds),
    exactDuration: (seconds) => context._historyDurationText(seconds),
  });
}

export function renderHistoryStatisticsSummary({ statistics, t, duration, exactDuration }) {
  const devices = statistics?.groups.device?.filter((row) => row.id).length ?? 0;
  const items = [
    ["occurrences", statistics?.occurrences ?? 0],
    ["entities", statistics?.groups.entity?.filter((row) => row.id).length ?? 0],
    ["devices", devices],
    ["cumulative", statistics ? duration(statistics.total_duration_seconds) : "—"],
  ];
  return `<dl>${items.map(([key, value]) => `<div><dt>${esc(t(`history.statistics.${key}`))}</dt><dd${key === "cumulative" && statistics ? ` title="${esc(exactDuration(statistics.total_duration_seconds))}"` : ""}>${statistics ? esc(value) : "—"}</dd></div>`).join("")}</dl>`;
}

export function openHistoryStatisticsGroup(context, kind, id) {
  if (!["alert", "entity", "device", "integration", "rule"].includes(kind)) return;
  const statistics = context._history?.statistics;
  if (statistics?.days !== (context._historyStatisticsDays ?? 7)) return;
  const row = statistics.groups[kind]?.find((item) => String(item.id) === String(id));
  if (!row) return;
  context._resetTableFilters("history");
  const state = context._tableState.history;
  state.search = "";
  state.filters[kind] = [kind === "alert" ? row.id : `id:${row.id}`];
  state.filters.activeFrom = statistics.from;
  state.filters.activeTo = statistics.to;
  context._selectedHistoryIds.clear();
  context._historyStatisticsOpen = false;
  context._render();
}

export function renderHistoryStatisticsLeaders({ statistics, t, integrationLabel, duration, exactDuration }) {
  return ["entity", "device", "integration"].map((kind) => {
    const rows = (statistics?.groups[kind] ?? []).filter((row) => row.id);
    return `<ha-card outlined class="history-statistics-ranking">
      <h2>${esc(t(`history.statistics.top_${kind}`))}</h2>
      ${[["frequent", "occurrences"], ["longest", "total_duration_seconds"]].map(([label, metric]) => {
        const ranked = [...rows].sort((a, b) => b[metric] - a[metric]
          || String(a.id).localeCompare(String(b.id))).slice(0, 5);
        return `<section><h3>${esc(t(`history.statistics.${label}`))}</h3>
          ${ranked.length ? `<ol>${ranked.map((row) => {
            const name = kind === "integration" ? integrationLabel(row.id) : row.name || row.id;
            const value = metric === "occurrences" ? row.occurrences : duration(row.total_duration_seconds);
            const exact = metric === "occurrences" ? value : exactDuration(row.total_duration_seconds);
            return `<li><ha-button appearance="plain" data-action="history-statistics-leader" data-kind="${kind}" data-id="${esc(row.id)}" title="${esc(name)} — ${esc(exact)}"><span class="history-statistics-leader-name">${esc(name)}</span><span class="history-statistics-leader-value">${esc(value)}</span></ha-button></li>`;
          }).join("")}</ol>` : `<p>${esc(t(statistics ? "history.statistics.empty" : "loading"))}</p>`}
        </section>`;
      }).join("")}
    </ha-card>`;
  }).join("");
}
