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
    this._refreshUiState();
}

export function renderHistory() {
    const limit = Number(this._historyConfig?.retention_limit ?? this._history?.retention_limit ?? 100);
    if (limit === 0) {
      return `<ha-card outlined class="history-empty"><div class="empty"><h2>${esc(this._t("history.disabled_title"))}</h2><p>${esc(this._t("history.disabled_help"))}</p><ha-button appearance="plain" data-action="open-history-settings">${esc(this._t("history.open_settings"))}</ha-button></div></ha-card>`;
    }
    const events = Array.isArray(this._history?.events) ? this._history.events : [];
    return this._renderAlertTable(
      "history",
      this._tableRows("history", events),
      this._renderPageMessages(),
    );
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
