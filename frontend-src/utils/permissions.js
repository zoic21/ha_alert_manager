import { TABS } from "./constants.js";

const readOnlyTabs = new Set(["overview", "history"]);
const readOnlyActions = new Set([
  "tab", "filter-summary-status", "clear-filter-section", "toggle-filter-option",
  "open-alert-history", "toggle-alert-timestamp", "copy-alert-id", "close-alert-details",
  "toggle-history-statistics", "history-statistics-period", "history-statistics-leader",
]);

export function canViewTab(readOnly, tab) {
  return !readOnly || readOnlyTabs.has(tab);
}

export function canUsePanelAction(readOnly, action, tab) {
  return !readOnly || (readOnlyActions.has(action) && (action !== "tab" || readOnlyTabs.has(tab)));
}

export function panelTabs() {
  return TABS.filter((tab) => canViewTab(this._readOnly, tab.id)).map(({ path, translationKey, iconPath }) => ({
    path, name: this._t(translationKey), iconPath,
  }));
}
