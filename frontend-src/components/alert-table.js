import { MDI_ALERT_CIRCLE_OUTLINE, MDI_CHECK_CIRCLE_OUTLINE, MDI_CLOCK_OUTLINE, MDI_FILTER_VARIANT_REMOVE, TABS } from "../utils/constants.js";
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
      const message = source.type === "rule"
        ? (source.message || "")
        : (source.condition_key ? condition : (source.message || ""));
      const finalLabel = history
        ? this._t(source.acknowledged ? "history.resolved_acknowledged" : "history.resolved")
        : this._t(`table.status.${status}`);
      const row = {
        id: history ? source.event_id : source.id,
        source,
        status,
        statusLabel: finalLabel,
        entityId: source.entity_id || "",
        entityName: entityName || source.entity_id || "—",
        deviceId: source.device_id || "",
        device: source.device_name || "",
        area: source.area || "",
        ruleId: source.rule_id || "",
        customRule: source.type === "rule",
        rule,
        integration: metadata.integration,
        integrationLabel: this._integrationLabel(metadata.integration),
        domain: metadata.domain,
        labels: metadata.labels,
        labelIds: metadata.labels.map((label) => label.id),
        message,
        value: this._displayValue(value, source.unit),
        rawValue: value,
        condition,
        detected: source.detected_at || "",
        activated: history ? source.active_at : source.active_since,
        resolved: history ? source.resolved_at : "",
        due: history ? "" : source.due_at,
        duration: history ? Number(source.total_duration_seconds ?? 0) : 0,
        acknowledged: history ? source.acknowledged === true : status === "acknowledged",
        acknowledgedAt: source.acknowledged_at || "",
        acknowledgedBy: source.acknowledged_by || "",
      };
      row.search = [
        row.rule, row.entityName, row.entityId, row.device, row.area, row.message,
        row.condition, row.value, row.statusLabel, row.integration, row.integrationLabel,
        row.domain, ...row.labels.flatMap((label) => [label.id, label.name]),
      ].join(" ").toLocaleLowerCase(this._language);
      return row;
    };
    if (kind === "history") {
      return historyEvents.map((event) => create(event, "resolved", true));
    }
    return [
      ...(this._alerts.alerts ?? []).map((alert) => create(alert, "active")),
      ...(this._alerts.pending ?? []).map((alert) => create(alert, "pending")),
      ...(this._alerts.acknowledge ?? []).map((alert) => create(alert, "acknowledged")),
    ];
}

export function filterCount(kind) {
    const filters = this._tableState[kind].filters;
    const facets = ["status", "device", "area", "rule", "integration", "labels", "domain", "entity"]
      .filter((key) => this._filterValues(filters[key]).length > 0).length;
    const detected = filters.detectedFrom || filters.detectedTo ? 1 : 0;
    const resolved = kind === "history" && (filters.resolvedFrom || filters.resolvedTo) ? 1 : 0;
    return facets + detected + resolved;
}

export function filterValues(value) {
    if (Array.isArray(value)) return value.map(String).filter(Boolean);
    return value === undefined || value === null || value === "" ? [] : [String(value)];
}

export function resetTableFilters(kind) {
    Object.keys(this._tableState[kind].filters).forEach((key) => {
      this._tableState[kind].filters[key] = ["detectedFrom", "detectedTo", "resolvedFrom", "resolvedTo"].includes(key)
        ? ""
        : [];
    });
}

export function filteredTableRows(kind, rows, includeSearch = true) {
    const state = this._tableState[kind];
    const query = includeSearch ? state.search.trim().toLocaleLowerCase(this._language) : "";
    const filters = state.filters;
    const selected = Object.fromEntries(
      ["status", "device", "area", "rule", "integration", "labels", "domain", "entity"]
        .map((key) => [key, new Set(this._filterValues(filters[key]))]),
    );
    const filtered = rows.filter((row) => {
      if (query && !row.search.includes(query)) return false;
      if (selected.status.size && !selected.status.has(row.status)) return false;
      if (selected.device.size && !selected.device.has(row.device)) return false;
      if (selected.area.size && !selected.area.has(row.area)) return false;
      if (selected.rule.size && !selected.rule.has(row.rule)) return false;
      if (selected.integration.size && !selected.integration.has(row.integration)) return false;
      if (selected.labels.size && !row.labelIds.some((label) => selected.labels.has(label))) return false;
      if (selected.domain.size && !selected.domain.has(row.domain)) return false;
      if (selected.entity.size && !selected.entity.has(row.entityId)) return false;
      if (!this._dateMatches(row.detected, filters.detectedFrom, filters.detectedTo)) return false;
      if (kind === "history" && !this._dateMatches(row.resolved, filters.resolvedFrom, filters.resolvedTo)) return false;
      return true;
    });
    const direction = state.sortDirection === "asc" ? 1 : -1;
    return filtered.sort((left, right) => direction * this._compareTableRows(left, right, state.sortBy));
}

export function dateMatches(value, from, to) {
    if (!from && !to) return true;
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return false;
    const boundary = (date, endOfDay) => {
      if (!date) return undefined;
      const valueToParse = /^\d{4}-\d{2}-\d{2}$/.test(date)
        ? `${date}T${endOfDay ? "23:59:59.999" : "00:00:00"}`
        : date;
      const parsed = Date.parse(valueToParse);
      return Number.isFinite(parsed) ? parsed : undefined;
    };
    const start = boundary(from, false);
    const end = boundary(to, true);
    if (start !== undefined && timestamp < start) return false;
    if (end !== undefined && timestamp > end) return false;
    return true;
}

export function compareTableRows(left, right, key) {
    if (key === "status") {
      const rank = { active: 0, pending: 1, acknowledged: 2, resolved: 3 };
      return (rank[left.status] ?? 99) - (rank[right.status] ?? 99);
    }
    if (["detected", "activated", "resolved", "due"].includes(key)) {
      return (Date.parse(left[key]) || 0) - (Date.parse(right[key]) || 0);
    }
    if (key === "remaining") return (Date.parse(left.due) || 0) - (Date.parse(right.due) || 0);
    if (key === "value") {
      const leftNumber = typeof left.rawValue === "number" ? left.rawValue : Number(left.rawValue);
      const rightNumber = typeof right.rawValue === "number" ? right.rawValue : Number(right.rawValue);
      if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) return leftNumber - rightNumber;
    }
    return String(left[key] ?? "").localeCompare(String(right[key] ?? ""), this._language, {
      numeric: true,
      sensitivity: "base",
    });
}

export function renderAlertTable(kind, sourceRows, topHeader = "") {
    const state = this._tableState[kind];
    const columns = this._tableColumns(kind);
    state.columns = state.columns.filter((column) => columns[column]);
    for (const required of REQUIRED_COLUMNS) {
      if (!state.columns.includes(required)) state.columns.push(required);
    }
    const selectedRows = kind === "overview"
      ? sourceRows.filter((row) => this._selectedAlertIds.has(row.id))
      : [];
    const acknowledgeCount = selectedRows.filter((row) => row.status === "active").length;
    const unacknowledgeCount = selectedRows.filter((row) => row.status === "acknowledged").length;
    return `<hass-tabs-subpage-data-table
      id="panel-shell"
      data-alert-table-page="${kind}"
      has-filters
      ${kind === "overview" ? "selectable" : ""}
      clickable
      main-page
    >
      ${topHeader ? `<div slot="top-header" class="table-page-top">${topHeader}</div>` : ""}
      <div slot="filter-pane" class="filter-pane-content">${this._renderFilterPane(kind, sourceRows)}</div>
      ${kind === "overview" ? `<div slot="selection-bar" class="selection-actions">
        <ha-button appearance="plain" variant="brand" data-action="bulk-acknowledge" data-selection-action="acknowledge" ${acknowledgeCount ? "" : "hidden"} ${this._busy ? "disabled" : ""}>${esc(this._t("table.selection.acknowledge", { count: acknowledgeCount }))}</ha-button>
        <ha-button appearance="plain" variant="danger" data-action="bulk-unacknowledge" data-selection-action="unacknowledge" ${unacknowledgeCount ? "" : "hidden"} ${this._busy ? "disabled" : ""}>${esc(this._t("table.selection.unacknowledge", { count: unacknowledgeCount }))}</ha-button>
      </div>` : ""}
    </hass-tabs-subpage-data-table>`;
}

export function facetOptions(rows, key) {
    return [...new Set(rows.map((row) => row[key]).filter(Boolean))]
      .sort((left, right) => String(left).localeCompare(String(right), this._language, { numeric: true }));
}

export function renderFacetFilter(kind, key, label, options) {
    const normalized = options.map((option) => ({
      value: String(option.value ?? option),
      label: String(option.label ?? option),
    }));
    const selected = new Set(this._filterValues(this._tableState[kind].filters[key]));
    return `<ha-expansion-panel left-chevron ${selected.size ? "expanded" : ""}>
      <div slot="header" class="filter-section-header">
        <span>${esc(label)}</span>
        ${selected.size ? `<span class="filter-badge">${selected.size}</span><ha-icon-button data-action="clear-filter-section" data-table-kind="${kind}" data-filter-keys="${key}" aria-label="${esc(this._t("table.filters.reset"))}"><ha-svg-icon path="${MDI_FILTER_VARIANT_REMOVE}"></ha-svg-icon></ha-icon-button>` : ""}
      </div>
      <div class="facet-filter-options" role="group" aria-label="${esc(label)}">
        ${normalized.length ? normalized.map((option) => `<div class="filter-option" data-action="toggle-filter-option" data-table-kind="${kind}" data-filter-key="${key}" data-filter-value="${esc(option.value)}"><ha-checkbox data-table-filter-option="${key}" data-filter-value="${esc(option.value)}" ${selected.has(option.value) ? "checked" : ""} aria-label="${esc(option.label)}"></ha-checkbox><span>${esc(option.label)}</span></div>`).join("") : `<span class="filter-empty">${esc(this._t("table.filters.no_options"))}</span>`}
      </div>
    </ha-expansion-panel>`;
}

export function dateRangeDefaults(rows, prefix) {
    const property = prefix === "resolved" ? "resolved" : "detected";
    const timestamps = rows
      .map((row) => Date.parse(row[property]))
      .filter(Number.isFinite);
    if (timestamps.length) {
      return {
        start: new Date(Math.min(...timestamps)).toISOString(),
        end: new Date(Math.max(...timestamps)).toISOString(),
      };
    }
    const end = new Date();
    const start = new Date(end);
    start.setHours(0, 0, 0, 0);
    return { start: start.toISOString(), end: end.toISOString() };
}

export function renderDateFilter(kind, prefix, label, rows) {
    const filters = this._tableState[kind].filters;
    const fromKey = `${prefix}From`;
    const toKey = `${prefix}To`;
    const active = filters[fromKey] || filters[toKey] ? 1 : 0;
    const defaults = this._dateRangeDefaults(rows, prefix);
    return `<ha-expansion-panel left-chevron ${active ? "expanded" : ""}>
      <div slot="header" class="filter-section-header">
        <span>${esc(label)}</span>
        ${active ? `<span class="filter-badge">${active}</span><ha-icon-button data-action="clear-filter-section" data-table-kind="${kind}" data-filter-keys="${fromKey},${toKey}" aria-label="${esc(this._t("table.filters.reset"))}"><ha-svg-icon path="${MDI_FILTER_VARIANT_REMOVE}"></ha-svg-icon></ha-icon-button>` : ""}
      </div>
      <div class="date-filter-fields"><ha-date-range-picker
        data-table-date-range="${prefix}"
        data-table-range-start="${esc(filters[fromKey] || defaults.start)}"
        data-table-range-end="${esc(filters[toKey] || defaults.end)}"
        data-table-kind="${kind}"
        extended-presets
        time-picker
        backdrop
      ></ha-date-range-picker></div>
    </ha-expansion-panel>`;
}

export function renderFilterPane(kind, rows) {
    const statuses = ["active", "pending", "acknowledged"]
      .map((value) => ({ value, label: this._t(`overview.status_${value}`) }));
    return `${kind === "overview" ? this._renderFacetFilter(kind, "status", this._t("table.columns.status"), statuses) : ""}
      ${this._renderFacetFilter(kind, "device", this._t("table.columns.device"), this._facetOptions(rows, "device"))}
      ${this._renderFacetFilter(kind, "rule", this._t("table.columns.rule"), this._facetOptions(rows, "rule"))}
      ${this._renderFacetFilter(kind, "integration", this._t("table.filters.integration"), this._facetOptions(rows, "integration").map((integration) => ({ value: integration, label: rows.find((row) => row.integration === integration)?.integrationLabel || integration })))}
      ${this._renderFacetFilter(kind, "labels", this._t("table.filters.labels"), [...new Map(rows.flatMap((row) => row.labels).map((label) => [label.id, { value: label.id, label: label.name }])).values()])}
      ${this._renderFacetFilter(kind, "domain", this._t("table.filters.domain"), this._facetOptions(rows, "domain"))}
      ${this._renderFacetFilter(kind, "area", this._t("table.columns.area"), this._facetOptions(rows, "area"))}
      ${this._renderFacetFilter(kind, "entity", this._t("table.columns.entity"), this._facetOptions(rows, "entityId").map((entityId) => ({ value: entityId, label: rows.find((row) => row.entityId === entityId)?.entityName || entityId })))}
      ${this._renderDateFilter(kind, "detected", this._t("table.columns.detected"), rows)}
      ${kind === "history" ? this._renderDateFilter(kind, "resolved", this._t("table.columns.resolved"), rows) : ""}`;
}

export function nativeTableColumns(kind) {
    const widths = {
      status: ["48px", 1],
      device: ["150px", 1],
      entity: ["180px", 1.4],
      entity_id: ["190px", 1],
      value: ["110px", 1],
      condition: ["260px", 2],
      detected: ["170px", 1],
      timeline: ["210px", 1.2],
      resolved: ["170px", 1],
      duration: ["120px", 1],
      area: ["130px", 1],
      rule: ["160px", 1],
      integration: ["150px", 1],
      message: ["220px", 1.5],
    };
    const sortable = new Set(["status", "device", "entity", "value", "detected", "resolved", "rule", "integration"]);
    const valueColumns = {
      status: "statusSort",
      entity: "entityName",
      value: "valueSort",
      detected: "detectedSort",
      resolved: "resolvedSort",
      integration: "integrationLabel",
    };
    const columns = Object.fromEntries(Object.entries(this._tableColumns(kind)).map(([column, definition]) => {
      const [minWidth, flex] = widths[column] ?? ["120px", 1];
      return [column, {
        title: column === "status" ? "" : definition.label,
        label: definition.label,
        main: column === "entity",
        type: column === "status" ? "icon" : undefined,
        showNarrow: column === "status",
        moveable: column === "status" ? false : undefined,
        hideable: REQUIRED_COLUMNS.has(column) ? false : undefined,
        defaultHidden: !DEFAULT_TABLE_STATE[kind].columns.includes(column),
        minWidth,
        flex,
        sortable: sortable.has(column),
        valueColumn: valueColumns[column],
        template: (row) => this._nativeTableCell(kind, row, column),
      }];
    }));
    columns.activated = { title: this._t("table.sort.activated"), hidden: true, sortable: true, valueColumn: "activatedSort" };
    columns.remaining = { title: this._t("table.sort.remaining"), hidden: true, sortable: true, valueColumn: "remainingSort" };
    columns.device_group = { title: this._t("table.columns.device"), hidden: true, groupable: true };
    columns.area_group = { title: this._t("table.columns.area"), hidden: true, groupable: true };
    columns.rule_group = { title: this._t("table.columns.rule"), hidden: true, groupable: true };
    columns.status_group = { title: this._t("table.columns.status"), hidden: true, groupable: true };
    columns.search_index = { title: "", hidden: true, filterable: true };
    return columns;
}

export function nativeTableData(kind, visibleRows) {
    const statusRank = { active: 0, pending: 1, acknowledged: 2, resolved: 3 };
    return visibleRows.map(({ source: _source, ...row }) => ({
      ...row,
      statusSort: statusRank[row.status] ?? 99,
      valueSort: String(row.rawValue ?? ""),
      detectedSort: Date.parse(row.detected) || 0,
      activatedSort: Date.parse(row.activated) || 0,
      resolvedSort: Date.parse(row.resolved) || 0,
      remainingSort: Date.parse(row.due) || 0,
      device_group: row.device || this._t("table.groups.without_device"),
      area_group: row.area || this._t("table.groups.without_area"),
      rule_group: row.rule || "—",
      status_group: row.statusLabel,
      search_index: row.search,
    }));
}

export function nativeGroupColumn(groupBy) {
    return groupBy === "none" ? undefined : `${groupBy}_group`;
}

export function tableStateGroupColumn(column) {
    const match = String(column ?? "").match(/^(device|area|rule|status)_group$/);
    return match?.[1] ?? "none";
}

export function nativeSortColumn(column) {
    return column === "entityName" ? "entity" : column;
}

export function tableSortStateColumn(column) {
    return column === "entity" ? "entityName" : column;
}

export function nativeTableCell(kind, row, column) {
    if (column === "status") return this._nativeStatusCell(row, kind);
    if (column === "entity") return this._nativeEntityCell(row, Boolean(this._narrow), kind);
    if (column === "entity_id") return this._nativeEntityIdCell(row);
    if (column === "device") return this._nativeDeviceCell(row);
    if (column === "area") return row.area || "—";
    if (column === "rule") return this._nativeRuleCell(row);
    if (column === "integration") return row.integrationLabel || row.integration || "—";
    if (column === "message") return row.message || "—";
    if (column === "value") return row.value;
    if (column === "condition") return row.condition || "—";
    if (column === "detected") return this._date(row.detected);
    if (column === "resolved") return this._date(row.resolved);
    if (column === "duration") return this._historyDurationText(row.duration);
    if (column === "timeline") return this._nativeTimelineCell(row);
    return "—";
}

export function nativeStatusCell(row, kind) {
    if (!globalThis.document?.createElement) return row.statusLabel;
    let path = MDI_ALERT_CIRCLE_OUTLINE;
    let color = "var(--error-color,#db4437)";
    let background = "color-mix(in srgb,var(--error-color,#db4437) 12%,transparent)";
    if (row.status === "pending") {
      path = MDI_CLOCK_OUTLINE;
      color = "var(--warning-color,#f5a623)";
      background = "color-mix(in srgb,var(--warning-color,#f5a623) 14%,transparent)";
    } else if (row.status === "acknowledged") {
      path = MDI_CHECK_CIRCLE_OUTLINE;
      color = "var(--blue-color,var(--primary-color,#03a9f4))";
      background = "color-mix(in srgb,var(--blue-color,var(--primary-color,#03a9f4)) 12%,transparent)";
    } else if (kind === "history") {
      path = MDI_CHECK_CIRCLE_OUTLINE;
      color = row.acknowledged
        ? "color-mix(in srgb,var(--blue-color,var(--primary-color,#03a9f4)) 70%,var(--secondary-text-color,#727272))"
        : "var(--secondary-text-color,#727272)";
      background = row.acknowledged
        ? "color-mix(in srgb,var(--blue-color,var(--primary-color,#03a9f4)) 9%,transparent)"
        : "var(--secondary-background-color,#f5f5f5)";
    }
    const status = document.createElement("span");
    status.setAttribute("role", "img");
    status.setAttribute("aria-label", row.statusLabel);
    status.title = row.statusLabel;
    status.style.cssText = `position:relative;display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;width:32px;height:32px;min-width:32px;min-height:32px;border-radius:50%;line-height:0;vertical-align:middle;color:${color};background:${background}`;
    const icon = document.createElement("ha-svg-icon");
    icon.path = path;
    icon.style.cssText = "position:absolute;inset:50% auto auto 50%;display:block;width:20px;height:20px;min-width:20px;min-height:20px;margin:0;padding:0;line-height:0;transform:translate(-50%,-50%)";
    status.append(icon);
    return status;
}

export function nativeEntityCell(row, narrow = false, kind = this._activeTab) {
    if (!globalThis.document?.createElement) return row.entityName;
    const content = document.createElement("span");
    content.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";
    const name = row.entityId ? document.createElement("a") : document.createElement("span");
    name.textContent = row.entityName;
    name.style.cssText = "overflow:hidden;font-weight:var(--ha-font-weight-medium,500);text-overflow:ellipsis;white-space:nowrap";
    if (row.entityId) {
      name.href = "#";
      name.className = "table-cell-link";
      name.title = row.entityId;
      name.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this._openMoreInfo(row.entityId);
      });
    }
    content.append(name);
    if (!narrow && row.labels?.length) {
      const labels = document.createElement("span");
      labels.style.cssText = "display:flex;min-width:0;gap:4px;overflow:hidden;align-items:center";
      for (const metadata of row.labels) {
        const label = document.createElement(customElements.get("ha-label") ? "ha-label" : "span");
        label.textContent = metadata.name;
        label.title = metadata.description || metadata.name;
        if (label.tagName === "HA-LABEL") {
          label.setAttribute("dense", "");
          if (metadata.color) label.setAttribute("color", metadata.color);
          if (metadata.description) label.setAttribute("description", metadata.description);
          label.className = "text-ellipsis";
        } else {
          label.style.cssText = "display:inline-flex;max-width:100%;height:20px;align-items:center;padding:0 8px;border:1px solid var(--outline-color,var(--divider-color,#ddd));border-radius:var(--ha-border-radius-md,6px);background:var(--secondary-background-color,#f5f5f5);font-size:var(--ha-font-size-s,12px);font-weight:var(--ha-font-weight-medium,500);overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
        }
        labels.append(label);
      }
      content.append(labels);
    }
    if (narrow) {
      const secondaryColumns = (this._tableState[kind]?.columns ?? [])
        .filter((column) => !REQUIRED_COLUMNS.has(column));
      if (secondaryColumns.length) {
        const secondary = document.createElement("span");
        secondary.style.cssText = "display:block;min-width:0;overflow:hidden;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400);text-overflow:ellipsis;white-space:nowrap";
        secondaryColumns.forEach((column, index) => {
          if (index) secondary.append(" · ");
          let item;
          if (column === "timeline" && row.status === "pending" && this._monitoringEnabled) {
            item = document.createElement("span");
            item.dataset.due = row.due;
            item.textContent = this._remaining(row.due);
          } else if (column === "timeline") {
            item = document.createElement("span");
            item.textContent = row.status === "pending"
              ? this._t("table.monitoring_suspended")
              : this._date(row.activated);
          } else {
            const rendered = this._nativeTableCell(kind, row, column);
            item = typeof rendered === "object" && rendered !== null
              ? rendered
              : document.createElement("span");
            if (typeof rendered !== "object" || rendered === null) {
              item.textContent = String(rendered);
            }
          }
          secondary.append(item);
        });
        content.append(secondary);
      }
    }
    return content;
}

export function nativeEntityIdCell(row) {
    return this._nativeAlertLink(row.entityId, {
      action: () => this._openMoreInfo(row.entityId),
      href: "#",
    });
}

export function nativeDeviceCell(row) {
    if (!row.deviceId) return row.device || "—";
    const path = `/config/devices/device/${encodeURIComponent(row.deviceId)}`;
    return this._nativeAlertLink(row.device || row.deviceId, {
      action: () => this._navigate(path),
      href: path,
    });
}

export function nativeRuleCell(row) {
    const ruleExists = row.customRule && row.ruleId && (this._config?.rules ?? []).some(
      (rule) => String(rule.id) === String(row.ruleId),
    );
    if (!ruleExists) return row.rule || "—";
    return this._nativeAlertLink(row.rule, {
      action: () => this._openRuleEditor(row.ruleId, { navigate: true }),
      href: "/alert-manager/rules",
    });
}

export function nativeAlertLink(label, { action, href }) {
    if (!label) return "—";
    if (!globalThis.document?.createElement) return label;
    const link = document.createElement("a");
    link.className = "table-cell-link";
    link.href = href;
    link.textContent = label;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      action();
    });
    return link;
}

export function alertDetailsItems(kind, row) {
    const linked = (key, label, value, action, data = {}) => ({
      key,
      label,
      value,
      action,
      data,
    });
    const items = [
      { key: "message", label: this._t("table.columns.message"), value: row.message },
      { key: "condition", label: this._t("table.columns.condition"), value: row.condition },
      linked("entity-id", this._t("table.columns.entity_id"), row.entityId, "more-info", {
        entityId: row.entityId,
      }),
      row.deviceId
        ? linked("device", this._t("table.columns.device"), row.device || row.deviceId, "open-alert-device", {
          deviceId: row.deviceId,
        })
        : { key: "device", label: this._t("table.columns.device"), value: row.device },
      { key: "area", label: this._t("table.columns.area"), value: row.area },
      row.customRule && row.ruleId && (this._config?.rules ?? []).some(
        (rule) => String(rule.id) === String(row.ruleId),
      )
        ? linked("rule", this._t("table.columns.rule"), row.rule, "open-alert-rule", {
          ruleId: row.ruleId,
        })
        : { key: "rule", label: this._t("table.columns.rule"), value: row.rule },
      {
        key: "integration",
        label: this._t("table.columns.integration"),
        value: row.integrationLabel || row.integration,
      },
      { key: "value", label: this._t("table.columns.value"), value: row.value },
      { key: "detected", label: this._t("table.columns.detected"), value: this._date(row.detected) },
    ];
    if (kind === "history") {
      items.push(
        {
          key: "activated",
          label: this._t("overview.active_since"),
          value: this._date(row.activated),
        },
        {
          key: "resolved",
          label: this._t("table.columns.resolved"),
          value: this._date(row.resolved),
        },
        {
          key: "duration",
          label: this._t("table.columns.duration"),
          value: this._historyDurationText(row.duration),
        },
      );
    } else if (row.status === "pending") {
      items.push({
        key: "remaining",
        label: this._t("overview.remaining"),
        value: this._monitoringEnabled
          ? this._remaining(row.due)
          : this._t("table.monitoring_suspended"),
      });
    } else {
      items.push({
        key: "activated",
        label: this._t("overview.active_since"),
        value: this._date(row.activated),
      });
    }
    if (row.acknowledged) {
      const acknowledgement = row.acknowledgedAt
        ? this._t("overview.acknowledged_details", {
          date: this._date(row.acknowledgedAt),
          author: row.acknowledgedBy || this._t("overview.acknowledged_system"),
        })
        : this._t("overview.acknowledged");
      items.push({
        key: "acknowledged",
        label: this._t("overview.acknowledged"),
        value: acknowledgement,
      });
    }
    items.push({
      key: "alert-id",
      label: this._t("alert_details.alert_id"),
      value: row.id,
    });
    return items.filter((item) => item.value !== undefined && item.value !== null && item.value !== "");
}

export function renderAlertDetails(context) {
    const { closeLabel, items, summary } = context;
    const attributes = (data) => Object.entries(data).map(([key, value]) => (
      ` data-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}="${esc(value)}"`
    )).join("");
    return `<section class="alert-details-summary alert-details-status-${esc(summary.status)}">
      <span class="alert-details-status-icon" aria-hidden="true"><ha-svg-icon path="${esc(summary.iconPath)}"></ha-svg-icon></span>
      <div class="alert-details-summary-text">
        <span class="alert-details-status-label">${esc(summary.statusLabel)}</span>
        <a class="alert-details-entity table-cell-link" href="#" data-action="more-info" data-entity-id="${esc(summary.entityId)}">${esc(summary.entityName)}</a>
      </div>
    </section>
    <dl class="alert-details-list">
      ${items.map((item) => `<div class="alert-details-item" data-detail-key="${esc(item.key)}">
        <dt>${esc(item.label)}</dt>
        <dd>${item.action
          ? `<a class="table-cell-link" href="#" data-action="${esc(item.action)}"${attributes(item.data)}>${esc(item.value)}</a>`
          : esc(item.value)}</dd>
      </div>`).join("")}
    </dl>
    <ha-button slot="primaryAction" appearance="accent" variant="brand" data-action="close-alert-details">${esc(closeLabel)}</ha-button>`;
}

export function renderAlertDetailsPanel(kind, row) {
    let iconPath = MDI_ALERT_CIRCLE_OUTLINE;
    if (row.status === "pending") iconPath = MDI_CLOCK_OUTLINE;
    if (row.status === "acknowledged" || kind === "history") {
      iconPath = MDI_CHECK_CIRCLE_OUTLINE;
    }
    return renderAlertDetails({
      closeLabel: this._t("buttons.close"),
      items: this._alertDetailsItems(kind, row),
      summary: {
        entityId: row.entityId,
        entityName: row.entityName,
        iconPath,
        status: row.status,
        statusLabel: row.statusLabel,
      },
    });
}

export function openAlertDetails(kind, row) {
    if (!globalThis.document?.createElement || !this.shadowRoot?.append) return;
    this._closeAlertDetailsDialog();
    const dialog = document.createElement("ha-dialog");
    dialog.className = "alert-details-dialog";
    dialog.hass = this._hass;
    dialog.heading = this._t("alert_details.title");
    dialog.scrimClickAction = "close";
    dialog.escapeKeyAction = "close";
    dialog.innerHTML = this._renderAlertDetails(kind, row);
    dialog.addEventListener("closed", () => {
      if (this._alertDetailsDialog === dialog) this._alertDetailsDialog = null;
      dialog.remove?.();
    });
    this._alertDetailsDialog = dialog;
    this.shadowRoot.append(dialog);
    dialog.open = true;
}

export function closeAlertDetailsDialog(afterClosed) {
    const dialog = this._alertDetailsDialog;
    const callback = typeof afterClosed === "function" ? afterClosed : null;
    if (!dialog) {
      callback?.();
      return;
    }
    this._alertDetailsDialog = null;
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      dialog.remove?.();
      callback?.();
    };
    dialog.addEventListener?.("closed", finish, { once: true });
    dialog.open = false;
}

export function nativeTimelineCell(row) {
    if (!globalThis.document?.createElement) {
      if (row.status === "pending") {
        return this._monitoringEnabled ? this._remaining(row.due) : this._t("table.monitoring_suspended");
      }
      return this._date(row.activated);
    }
    const timeline = document.createElement("span");
    timeline.style.cssText = "display:flex;flex-direction:column;line-height:1.35;white-space:nowrap";
    const label = document.createElement("small");
    label.style.cssText = "display:block;margin:0;color:var(--secondary-text-color,#727272)";
    if (row.status === "pending") {
      label.textContent = this._t("overview.remaining");
      timeline.append(label);
      const value = document.createElement("span");
      if (!this._monitoringEnabled) {
        timeline.style.color = "var(--warning-color,#9a6b00)";
        value.textContent = this._t("table.monitoring_suspended");
      } else {
        value.dataset.due = row.due;
        value.textContent = this._remaining(row.due);
      }
      timeline.append(value);
      return timeline;
    }
    label.textContent = this._t("overview.active_since");
    timeline.append(label, this._date(row.activated));
    return timeline;
}

export function openMoreInfo(entityId) {
    if (!this._hass?.states?.[entityId]) return;
    this._preserveOverviewScrollAfterMoreInfo();
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    }));
}

export function overviewContentScroller() {
    const tablePage = this.shadowRoot?.querySelector?.(
      '[data-alert-table-page="overview"]',
    );
    const subpage = tablePage?.shadowRoot?.querySelector?.("hass-tabs-subpage");
    return subpage?.shadowRoot?.querySelector?.(".content") ?? null;
}

export function dialogEventTarget() {
    return globalThis.document;
}

export function cancelMoreInfoScrollRestore() {
    const pending = this._moreInfoScrollRestore;
    if (!pending) return;
    pending.target?.removeEventListener?.("dialog-closed", pending.listener, true);
    this._moreInfoScrollRestore = null;
}

export function preserveOverviewScrollAfterMoreInfo() {
    this._cancelMoreInfoScrollRestore();
    if (!this._narrow || this._activeTab !== "overview") return;
    const scroller = this._overviewContentScroller();
    const target = this._dialogEventTarget();
    if (!scroller || typeof target?.addEventListener !== "function") return;
    const scrollTop = scroller.scrollTop;
    const listener = (event) => {
      if (event.detail?.dialog !== "ha-more-info-dialog") return;
      this._cancelMoreInfoScrollRestore();
      const restore = () => {
        if (!this.isConnected) return;
        const currentScroller = this._overviewContentScroller();
        if (currentScroller) currentScroller.scrollTop = scrollTop;
      };
      restore();
      const schedule = globalThis.requestAnimationFrame
        ?? globalThis.window?.requestAnimationFrame;
      if (typeof schedule === "function") {
        schedule(() => schedule(restore));
      } else {
        globalThis.setTimeout?.(restore, 0);
      }
    };
    this._moreInfoScrollRestore = { target, listener };
    target.addEventListener("dialog-closed", listener, true);
}

export function navigate(path, newTabInBrowser = false) {
    if (!path) return;
    const inCompanionApp = Boolean(
      globalThis.window?.externalApp
      || globalThis.window?.externalAppV2
      || globalThis.window?.webkit?.messageHandlers?.externalBus
    );
    if (newTabInBrowser && !inCompanionApp && typeof window.open === "function") {
      window.open(path, "_blank", "noopener,noreferrer");
      return;
    }
    window.history?.pushState?.(null, "", path);
    window.dispatchEvent?.(new CustomEvent("location-changed", {
      detail: { replace: false },
    }));
}

export function syncNarrowTableHeaderBackgrounds() {
    if (!globalThis.document?.createElement) return;
    const styleId = "alert-manager-narrow-table-header-style";
    for (const selector of [
      '[data-alert-table-page="overview"]',
      '[data-alert-table-page="history"]',
      "[data-rules-table-page]",
      "[data-coherence-table-page]",
    ]) {
      const root = this.shadowRoot?.querySelector?.(selector)?.shadowRoot;
      if (!root || root.querySelector?.(`#${styleId}`)) continue;
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
        :host([narrow]) .narrow-header-row {
          background: var(--primary-background-color);
          border-bottom: 1px solid var(--divider-color);
          box-sizing: border-box;
        }
      `;
      root.append(style);
    }
}

export async function handleAlertTableAction(action, button, event) {
  if (action === "clear-filter-section") {
    event.preventDefault?.();
    event.stopPropagation?.();
    const kind = button.dataset.tableKind;
    for (const key of String(button.dataset.filterKeys ?? "").split(",").filter(Boolean)) {
      this._tableState[kind].filters[key] = Array.isArray(this._tableState[kind].filters[key]) ? [] : "";
    }
    this._filterPaneKind = kind;
    this._render();
    return true;
  }
  if (action === "toggle-filter-option") {
    if (event.target?.closest?.("ha-checkbox")) return true;
    const kind = button.dataset.tableKind;
    const key = button.dataset.filterKey;
    const value = button.dataset.filterValue;
    const selected = new Set(this._filterValues(this._tableState[kind].filters[key]));
    if (selected.has(value)) selected.delete(value);
    else selected.add(value);
    this._tableState[kind].filters[key] = [...selected];
    this._filterPaneKind = kind;
    this._render();
    return true;
  }
  if (action === "more-info") {
    event.preventDefault?.();
    event.stopPropagation?.();
    const entityId = button.dataset.entityId;
    this._closeAlertDetailsDialog(() => this._openMoreInfo(entityId));
    return true;
  }
  if (action === "open-alert-device") {
    event.preventDefault?.();
    event.stopPropagation?.();
    const path = `/config/devices/device/${encodeURIComponent(button.dataset.deviceId)}`;
    this._closeAlertDetailsDialog(() => this._navigate(path));
    return true;
  }
  if (action === "open-alert-rule") {
    event.preventDefault?.();
    event.stopPropagation?.();
    const ruleId = button.dataset.ruleId;
    this._closeAlertDetailsDialog(() => this._openRuleEditor(ruleId, { navigate: true }));
    return true;
  }
  if (action === "close-alert-details") {
    event.preventDefault?.();
    event.stopPropagation?.();
    this._closeAlertDetailsDialog();
    return true;
  }
  return false;
}
