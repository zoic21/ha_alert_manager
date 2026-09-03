import { MDI_ALERT_CIRCLE_OUTLINE, MDI_CHECK_CIRCLE_OUTLINE, MDI_CLOCK_OUTLINE, MDI_DOTS_VERTICAL, MDI_FILTER_VARIANT_REMOVE, TABS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { DEFAULT_TABLE_STATE, REQUIRED_COLUMNS } from "../utils/table-preferences.js";

export function refreshAlertTableData(kind, tablePage) {
    const sourceRows = kind === "overview"
      ? this._tableRows("overview")
      : this._tableRows("history", this._history?.events ?? []);
    const visibleRows = this._filteredTableRows(kind, sourceRows, false);
    tablePage.hass = this._hass;
    tablePage.data = this._nativeTableData(kind, visibleRows);
    tablePage._alertManagerRows = tablePage.data;
    if (kind === "overview") tablePage.selected = this._selectedAlertIds.size;
    tablePage.noDataText = sourceRows.length
      ? this._t("table.empty_filtered")
      : this._t(kind === "history" ? "history.empty" : "table.empty_current");
}

export function loadNativeDateRangePicker() {
    if (customElements.get("ha-date-range-picker")) return Promise.resolve();
    if (this._dateRangePickerPromise) return this._dateRangePickerPromise;
    const homeAssistant = document.querySelector?.("home-assistant");
    const main = homeAssistant?.shadowRoot?.querySelector?.("home-assistant-main");
    const resolver = main?.shadowRoot?.querySelector?.("partial-panel-resolver");
    const historyPath = Object.values(this._hass?.panels ?? {})
      .find((panel) => panel.component_name === "history")?.url_path;
    const loadHistory = historyPath
      ? resolver?.routerOptions?.routes?.[historyPath]?.load
      : undefined;
    this._dateRangePickerPromise = typeof loadHistory === "function"
      ? Promise.resolve(loadHistory()).catch(() => undefined)
      : Promise.resolve();
    return this._dateRangePickerPromise;
}

export function configureDateRangePicker(kind, picker) {
    const prefix = picker.dataset.tableDateRange;
    if (!prefix) return;
    const fromKey = `${prefix}From`;
    const toKey = `${prefix}To`;
    picker.startDate = new Date(picker.dataset.tableRangeStart);
    picker.endDate = new Date(picker.dataset.tableRangeEnd);
    picker.extendedPresets = true;
    picker.timePicker = true;
    picker.backdrop = true;
    picker.addEventListener("value-changed", (event) => {
      const startDate = event.detail?.value?.startDate;
      const endDate = event.detail?.value?.endDate;
      if (!(startDate instanceof Date) || !Number.isFinite(startDate.getTime())
        || !(endDate instanceof Date) || !Number.isFinite(endDate.getTime())) return;
      this._tableState[kind].filters[fromKey] = startDate.toISOString();
      this._tableState[kind].filters[toKey] = endDate.toISOString();
      this._filterPaneKind = kind;
      this._render();
    });
}

export function hydrateDataTables() {
    for (const kind of ["overview", "history"]) {
      const tablePage = this.shadowRoot.querySelector(`[data-alert-table-page="${kind}"]`);
      if (!tablePage) continue;
      const sourceRows = kind === "overview"
        ? this._tableRows("overview")
        : this._tableRows("history", this._history?.events ?? []);
      const visibleRows = this._filteredTableRows(kind, sourceRows, false);
      const allowedColumns = Object.keys(this._tableColumns(kind));
      const hiddenColumns = allowedColumns.filter((column) => !this._tableState[kind].columns.includes(column));
      const orderedColumns = [...this._tableState[kind].columns, ...hiddenColumns];
      const data = this._nativeTableData(kind, visibleRows);
      tablePage.hass = this._hass;
      tablePage.narrow = Boolean(this._narrow);
      tablePage.tabs = this._tabs();
      tablePage.route = { prefix: "", path: TABS.find((tab) => tab.id === kind)?.path ?? TABS[0].path };
      tablePage.mainPage = true;
      tablePage.backPath = undefined;
      tablePage.backCallback = undefined;
      tablePage.id = "id";
      tablePage.columns = this._nativeTableColumns(kind);
      tablePage.columnOrder = orderedColumns;
      tablePage.hiddenColumns = hiddenColumns;
      tablePage.data = data;
      tablePage._alertManagerRows = data;
      tablePage.filter = this._tableState[kind].search;
      tablePage.searchLabel = this._t("table.search");
      tablePage.filters = this._filterCount(kind);
      tablePage.selected = kind === "overview" ? this._selectedAlertIds.size : undefined;
      tablePage.initialGroupColumn = this._nativeGroupColumn(this._tableState[kind].groupBy);
      tablePage.initialSorting = {
        column: this._nativeSortColumn(this._tableState[kind].sortBy),
        direction: this._tableState[kind].sortDirection,
      };
      tablePage.initialCollapsedGroups = [...this._collapsedTableGroups]
        .filter((key) => key.startsWith(`${kind}:`))
        .map((key) => key.slice(kind.length + 1));
      tablePage.selectable = kind === "overview";
      tablePage.clickable = true;
      tablePage.showFilters = this._filterPaneKind === kind;
      if (kind === "overview" && this._selectionMode) tablePage._selectMode = true;
      tablePage.noDataText = sourceRows.length
        ? this._t("table.empty_filtered")
        : this._t(kind === "history" ? "history.empty" : "table.empty_current");
      tablePage.addEventListener("search-changed", (event) => {
        this._tableState[kind].search = String(event.detail?.value ?? "");
      });
      tablePage.addEventListener("clear-filter", () => {
        this._resetTableFilters(kind);
        this._filterPaneKind = kind;
        this._render();
      });
      tablePage.addEventListener("collapsed-changed", (event) => {
        for (const key of [...this._collapsedTableGroups]) {
          if (key.startsWith(`${kind}:`)) this._collapsedTableGroups.delete(key);
        }
        for (const group of event.detail?.value ?? []) this._collapsedTableGroups.add(`${kind}:${group}`);
      });
      tablePage.addEventListener("sorting-changed", (event) => {
        const column = this._tableSortStateColumn(event.detail?.column);
        if (!column || !event.detail?.direction) return;
        this._tableState[kind].sortBy = column;
        this._tableState[kind].sortDirection = event.detail.direction;
        this._saveTablePreferences();
      });
      tablePage.addEventListener("grouping-changed", (event) => {
        this._tableState[kind].groupBy = this._tableStateGroupColumn(event.detail?.value);
        this._saveTablePreferences();
      });
      tablePage.addEventListener("columns-changed", (event) => {
        const order = event.detail?.columnOrder;
        const hidden = new Set(event.detail?.hiddenColumns ?? []);
        if (!Array.isArray(order)) {
          this._tableState[kind].columns = [...DEFAULT_TABLE_STATE[kind].columns];
        } else {
          this._tableState[kind].columns = order.filter((column) => (
            allowedColumns.includes(column) && !hidden.has(column)
          ));
          for (const required of REQUIRED_COLUMNS) {
            if (!this._tableState[kind].columns.includes(required)) {
              this._tableState[kind].columns.push(required);
            }
          }
        }
        this._saveTablePreferences();
      });
      tablePage.addEventListener("row-click", (event) => {
        const row = tablePage._alertManagerRows?.find(
          (item) => String(item.id) === String(event.detail?.id),
        );
        if (row) this._openAlertDetails(kind, row);
      });
      if (kind === "overview") {
        tablePage.addEventListener("selection-changed", (event) => {
          const selected = new Set((event.detail?.value ?? []).map(String));
          if (selected.size === this._selectedAlertIds.size
            && [...selected].every((id) => this._selectedAlertIds.has(id))) return;
          this._selectedAlertIds = selected;
          this._updateSelectionToolbar();
        });
        if (this._selectionMode && this._selectedAlertIds.size && tablePage.shadowRoot) {
          const restoreSelection = () => {
            const nativeTable = tablePage.shadowRoot?.querySelector?.("ha-data-table");
            nativeTable?.select?.([...this._selectedAlertIds], true);
          };
          Promise.resolve(tablePage.updateComplete).then(restoreSelection);
        }
      }
      tablePage.querySelectorAll("ha-checkbox[data-table-filter-option]").forEach((checkbox) => {
        const key = checkbox.dataset.tableFilterOption;
        const value = checkbox.dataset.filterValue;
        checkbox.checked = this._filterValues(this._tableState[kind].filters[key]).includes(value);
        checkbox.addEventListener("change", (event) => {
          event.stopPropagation();
          const selected = new Set(this._filterValues(this._tableState[kind].filters[key]));
          if (checkbox.checked) selected.add(value);
          else selected.delete(value);
          this._tableState[kind].filters[key] = [...selected];
          this._filterPaneKind = kind;
          this._render();
        });
      });
      tablePage.querySelectorAll("ha-date-range-picker[data-table-date-range]").forEach((picker) => {
        if (customElements.get("ha-date-range-picker") || typeof customElements.whenDefined !== "function") {
          this._configureDateRangePicker(kind, picker);
          return;
        }
        this._loadNativeDateRangePicker().then(() => {
          if (picker.isConnected && customElements.get("ha-date-range-picker")) {
            this._configureDateRangePicker(kind, picker);
          }
        });
      });
    }
}

export function updateSelectionToolbar() {
    const selectedRows = this._tableRows("overview").filter((row) => this._selectedAlertIds.has(row.id));
    const acknowledgeCount = selectedRows.filter((row) => row.status === "active").length;
    const unacknowledgeCount = selectedRows.filter((row) => row.status === "acknowledged").length;
    const count = this.shadowRoot.querySelector("[data-selection-count]");
    if (count) count.textContent = this._t("table.selection.count", { count: selectedRows.length });
    const acknowledge = this.shadowRoot.querySelector('[data-selection-action="acknowledge"]');
    if (acknowledge) {
      acknowledge.hidden = acknowledgeCount === 0;
      acknowledge.textContent = this._t("table.selection.acknowledge", { count: acknowledgeCount });
    }
    const unacknowledge = this.shadowRoot.querySelector('[data-selection-action="unacknowledge"]');
    if (unacknowledge) {
      unacknowledge.hidden = unacknowledgeCount === 0;
      unacknowledge.textContent = this._t("table.selection.unacknowledge", { count: unacknowledgeCount });
    }
    const tablePage = this.shadowRoot.querySelector('[data-alert-table-page="overview"]');
    if (tablePage) tablePage.selected = selectedRows.length;
}

export function tableColumns(kind) {
    const all = {
      status: { label: this._t("table.columns.status") },
      device: { label: this._t("table.columns.device") },
      entity: { label: this._t("table.columns.entity") },
      entity_id: { label: this._t("table.columns.entity_id") },
      value: { label: this._t("table.columns.value") },
      condition: { label: this._t("table.columns.condition") },
      detected: { label: this._t("table.columns.detected") },
      area: { label: this._t("table.columns.area") },
      rule: { label: this._t("table.columns.rule") },
      integration: { label: this._t("table.columns.integration") },
      message: { label: this._t("table.columns.message") },
      timeline: { label: this._t("table.columns.timeline") },
      resolved: { label: this._t("table.columns.resolved") },
      duration: { label: this._t("table.columns.duration") },
    };
    const allowed = kind === "overview"
      ? ["status", "entity", "device", "rule", "integration", "timeline", "entity_id", "value", "condition", "detected", "area", "message"]
      : ["status", "entity", "device", "rule", "integration", "detected", "entity_id", "value", "condition", "resolved", "duration", "area", "message"];
    return Object.fromEntries(allowed.map((column) => [column, all[column]]));
}

export function alertRuleName(alert) {
    if (alert.rule_name && alert.rule_name !== alert.type) return alert.rule_name;
    const pack = this._packs.find((item) => item.id === alert.type);
    return pack ? this._t(`packs.${pack.translation_key}.name`) : (alert.rule_name || alert.type || "—");
}

export function displayValue(value, unit) {
    if (value === undefined || value === null || value === "") return "—";
    const rendered = typeof value === "object" ? JSON.stringify(value) : String(value);
    return unit ? `${rendered} ${unit}` : rendered;
}

function attributeValue(attributes, path) {
    if (!attributes || !path) return [false, null];
    if (Object.hasOwn(attributes, path)) return [true, attributes[path]];
    if (!path.includes(".")) return [false, null];

    let values = [attributes];
    let usedWildcard = false;
    for (const segment of path.split(".")) {
      const nextValues = [];
      if (segment === "*") {
        usedWildcard = true;
        for (const value of values) {
          if (Array.isArray(value)) nextValues.push(...value);
        }
      } else {
        for (const value of values) {
          if (value && typeof value === "object" && Object.hasOwn(value, segment)) {
            nextValues.push(value[segment]);
          }
        }
      }
      if (!nextValues.length) return [false, null];
      values = nextValues;
    }
    return [true, usedWildcard ? values : values[0]];
}

function alertCurrentValue(row) {
    const state = this._hass?.states?.[row.entityId];
    if (!state) return "—";
    let value = state.state;
    const source = row.source?.source;
    if (["attribute", "attribute_variation"].includes(source)) {
      const [found, attribute] = attributeValue(
        state.attributes,
        row.source?.attribute,
      );
      if (!found) return "—";
      value = attribute;
    }
    const unit = state.attributes?.unit_of_measurement ?? row.source?.unit;
    return this._displayValue(value, unit);
}

export function entityMetadata(source, labelRegistry) {
    const entityId = source.entity_id || "";
    const entity = this._hass?.entities?.[entityId];
    const domain = entityId.includes(".") ? entityId.split(".", 1)[0] : "";
    const integration = source.integration || entity?.platform || "";
    const labelIds = [...new Set([
      ...(Array.isArray(source.labels) ? source.labels : []),
      ...(Array.isArray(entity?.labels) ? entity.labels : []),
    ].map(String).filter(Boolean))];
    const labels = labelIds.map((labelId) => {
      const entry = labelRegistry.get(labelId);
      return {
        id: labelId,
        name: entry?.name || labelId,
        color: entry?.color || "",
        description: entry?.description || "",
        icon: entry?.icon || "",
      };
    });
    return { domain, integration, labels };
}

export function integrationLabel(integration) {
    if (!integration) return "";
    return this._hass?.localize?.(`component.${integration}.title`)
      || String(integration).replaceAll("_", " ");
}

export function tableRows(kind, historyEvents = []) {
    const labelRegistry = new Map(
      (Array.isArray(this._labels) ? this._labels : []).map((label) => (
        [String(label.label_id), label]
      )),
    );
    const create = (source, status, history = false) => {
      const metadata = this._entityMetadata(source, labelRegistry);
      const entityName = history ? (source.entity_name || source.entity_id) : (source.name || source.entity_id);
      const value = history ? source.trigger_value : source.value;
      const condition = history ? this._historyConditionText(source) : this._conditionText(source);
      const rule = history ? this._historyRuleName(source) : this._alertRuleName(source);
      const renderedMessage = source.type === "rule"
        ? (source.message || "")
        : (source.condition_key ? condition : (source.message || ""));
      const message = String(renderedMessage).trim() === String(condition).trim()
        ? ""
        : renderedMessage;
      const finalLabel = history
        ? this._t(source.acknowledged ? "history.resolved_acknowledged" : "history.resolved")
        : this._t(`table.status.${status}`);
      const row = {
        id: history ? source.event_id 