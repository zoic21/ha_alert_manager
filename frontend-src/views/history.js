import { esc } from "../utils/escaping.js";

export function refreshHistoryData() {
    if (this._activeTab !== "history") return;
    const tablePage = this.shadowRoot?.querySelector?.('[data-alert-table-page="history"]');
    const historyEnabled = Number(
      this._historyConfig?.retention_limit ?? this._history?.retention_limit ?? 100,
    ) !== 0;
    if (!tablePage || !historyEnabled) {
      this._render();
      return;
    }
    this._refreshAlertTableData("history", tablePage);
    const clearButton = tablePage.querySelector?.('[data-action="clear-history"]');
    if (clearButton) clearButton.disabled = !(this._history?.events?.length);
    this._refreshUiState();
}

export function renderHistory(context) {
    const { busy, limit, pageMessages, rows, renderAlertTable, t } = context;
    if (limit === 0) {
      return `<ha-card outlined class="history-empty"><div class="empty"><h2>${esc(t("history.disabled_title"))}</h2><p>${esc(t("history.disabled_help"))}</p><ha-button appearance="plain" data-action="open-history-settings">${esc(t("history.open_settings"))}</ha-button></div></ha-card>`;
    }
    const header = `${pageMessages}<ha-card outlined class="panel history-panel">
      <div class="history-header">
        <div><h2>${esc(t("history.title"))}</h2></div>
        <div class="history-page-actions"><ha-button appearance="plain" variant="danger" data-action="clear-history" ${busy || !rows.length ? "disabled" : ""}>${esc(t("settings.history_clear"))}</ha-button></div>
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
  if (action === "clear-history") {
    if (!window.confirm(this._t("settings.history_clear_confirm"))) return true;
    const result = await this._call(
      { type: "alert_manager/history/clear", confirmed: true },
      this._t("success.history_cleared"),
    );
    if (result) {
      this._history = result;
      this._refreshHistoryData();
      if (this._historyRefreshPromise) await this._refreshHistory();
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
