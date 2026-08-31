import { MDI_PLUS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { DEFAULT_RULES_TABLE_STATE, RULES_COLUMNS, RULES_SECONDARY_COLUMNS } from "../utils/table-preferences.js";

const RULES_TABLE_CONTEXT = Symbol("alert-manager-rules-table-context");
const RULES_TABLE_HYDRATED = Symbol("alert-manager-rules-table-hydrated");
const RULES_FILTER_HYDRATED = Symbol("alert-manager-rules-filter-hydrated");

async function applyRuleTableEditorLayout(tablePage) {
    if (tablePage.updateComplete) await tablePage.updateComplete;
    tablePage.shadowRoot?.querySelector?.("ha-data-table")?.style?.setProperty(
      "width",
      "var(--alert-manager-rule-table-width, 100%)",
    );
}

export function refreshRulesData() {
    if (this._activeTab !== "rules") return;
    const tablePage = this.shadowRoot?.querySelector?.("[data-rules-table-page]");
    if (!tablePage || !this._config) {
      this._render();
      return;
    }
    const state = this._ensureRulesTableState();
    const sourceRows = this._ruleTableRows();
    const enabledFilters = new Set(this._filterValues(state.filters.enabled));
    const visibleRows = sourceRows.filter((row) => (
      !enabledFilters.size || enabledFilters.has(row.enabledKey)
    ));
    tablePage.hass = this._hass;
    tablePage.data = visibleRows;
    tablePage._alertManagerRows = visibleRows;
    tablePage.filters = enabledFilters.size ? 1 : 0;
    tablePage.noDataText = sourceRows.length
      ? this._t("rules.empty_filtered")
      : this._t("rules.empty");
    this._refreshUiState();
}

export function ruleTableColumns(context) {
    const { t, narrow, renderNameCell, renderEntitiesCell, renderToggleCell } = context;
    return {
      name: {
        title: t("rules.name"),
        label: t("rules.name"),
        main: true,
        sortable: true,
        hideable: false,
        moveable: false,
        minWidth: "180px",
        flex: 1.2,
        template: (row) => renderNameCell(row, narrow),
      },
      entities: {
        title: t("rules.entities"),
        sortable: true,
        minWidth: "220px",
        flex: 1.4,
        template: (row) => renderEntitiesCell(row),
      },
      condition: {
        title: t("rules.condition"),
        minWidth: "260px",
        flex: 1.7,
      },
      duration: {
        title: t("rules.duration"),
        sortable: true,
        valueColumn: "durationSort",
        type: "numeric",
        minWidth: "120px",
        flex: 0.7,
      },
      enabled: {
        title: t("rules.status"),
        label: t("rules.status"),
        sortable: true,
        valueColumn: "enabledSort",
        type: "icon",
        showNarrow: true,
        hideable: false,
        moveable: false,
        minWidth: "88px",
        flex: 0.5,
        template: (row) => renderToggleCell(row),
      },
      search_index: {
        title: "",
        hidden: true,
        filterable: true,
      },
    };
}

export function hydrateRules(root, context) {
    const tablePage = root?.querySelector?.("[data-rules-table-page]");
    if (!tablePage) return;
    tablePage[RULES_TABLE_CONTEXT] = context;
    const { state, sourceRows, visibleRows, selectedFilters } = context;
    tablePage.hass = context.hass;
    tablePage.narrow = context.narrow;
    tablePage.tabs = context.tabs;
    tablePage.route = { prefix: "", path: "/alert-manager/rules" };
    tablePage.mainPage = true;
    tablePage.backPath = undefined;
    tablePage.backCallback = undefined;
    tablePage.id = "id";
    tablePage.clickable = true;
    tablePage.searchLabel = context.t("rules.search");
    tablePage.filter = state.search;
    tablePage.filters = selectedFilters.length ? 1 : 0;
    tablePage.showFilters = context.filterPaneOpen;
    tablePage.columns = ruleTableColumns(context);
    tablePage.columnOrder = [...state.columnOrder];
    tablePage.hiddenColumns = [...state.hiddenColumns];
    tablePage.initialSorting = { column: state.sortBy, direction: state.sortDirection };
    tablePage.data = visibleRows;
    tablePage._alertManagerRows = visibleRows;
    tablePage.noDataText = sourceRows.length
      ? context.t("rules.empty_filtered")
      : context.t("rules.empty");
    if (!tablePage[RULES_TABLE_HYDRATED]) {
      tablePage.addEventListener("search-changed", (event) => {
        tablePage[RULES_TABLE_CONTEXT].onSearch(String(event.detail?.value ?? ""));
      });
      tablePage.addEventListener("clear-filter", () => {
        tablePage[RULES_TABLE_CONTEXT].onClearFilter();
      });
      tablePage.addEventListener("sorting-changed", (event) => {
        tablePage[RULES_TABLE_CONTEXT].onSortingChanged(event.detail ?? {});
      });
      tablePage.addEventListener("columns-changed", (event) => {
        tablePage[RULES_TABLE_CONTEXT].onColumnsChanged(event.detail ?? {});
      });
      tablePage.addEventListener("row-click", (event) => {
        tablePage[RULES_TABLE_CONTEXT].onRowClick(event.detail?.id);
      });
      tablePage[RULES_TABLE_HYDRATED] = true;
    }
    tablePage.querySelectorAll?.("ha-checkbox[data-table-filter-option]").forEach((checkbox) => {
      const value = checkbox.dataset.filterValue;
      checkbox.checked = selectedFilters.includes(value);
      checkbox[RULES_TABLE_CONTEXT] = context;
      if (checkbox[RULES_FILTER_HYDRATED]) return;
      checkbox.addEventListener("change", (event) => {
        event.stopPropagation();
        checkbox[RULES_TABLE_CONTEXT].onFilterChanged(value, checkbox.checked);
      });
      checkbox[RULES_FILTER_HYDRATED] = true;
    });
    void applyRuleTableEditorLayout(tablePage);
}

export function hydrateRuleTable() {
    if (!this._config) return;
    const state = this._ensureRulesTableState();
    const sourceRows = this._ruleTableRows();
    const selectedFilters = this._filterValues(state.filters.enabled);
    const enabledFilters = new Set(selectedFilters);
    const visibleRows = sourceRows.filter((row) => (
      !enabledFilters.size || enabledFilters.has(row.enabledKey)
    ));
    hydrateRules(this.shadowRoot, {
      hass: this._hass,
      narrow: Boolean(this._narrow),
      tabs: this._tabs(),
      state,
      sourceRows,
      visibleRows,
      selectedFilters,
      filterPaneOpen: this._filterPaneKind === "rules",
      t: (key, replacements) => this._t(key, replacements),
      renderNameCell: (row, narrow) => this._nativeRuleNameCell(row, narrow),
      renderEntitiesCell: (row) => this._nativeRuleEntitiesCell(row),
      renderToggleCell: (row) => this._nativeRuleToggleCell(row),
      onSearch: (search) => { state.search = search; },
      onClearFilter: () => {
        state.filters.enabled = [];
        this._filterPaneKind = "rules";
        this._render();
      },
      onSortingChanged: ({ column, direction }) => {
        if (!RULES_COLUMNS.includes(column) || !["asc", "desc"].includes(direction)) return;
        state.sortBy = column;
        state.sortDirection = direction;
        this._saveRulesTableState();
      },
      onColumnsChanged: ({ columnOrder, hiddenColumns }) => {
        const order = Array.isArray(columnOrder)
          ? columnOrder.filter((column) => RULES_SECONDARY_COLUMNS.has(column))
          : DEFAULT_RULES_TABLE_STATE.columnOrder.filter(
            (column) => RULES_SECONDARY_COLUMNS.has(column),
          );
        state.columnOrder = [
          "name",
          ...order,
          ...RULES_COLUMNS.filter((column) => (
            RULES_SECONDARY_COLUMNS.has(column) && !order.includes(column)
          )),
          "enabled",
        ];
        state.hiddenColumns = (hiddenColumns ?? [])
          .filter((column) => RULES_SECONDARY_COLUMNS.has(column));
        this._saveRulesTableState();
      },
      onRowClick: (ruleId) => {
        this._openRuleEditor(ruleId);
      },
      onFilterChanged: (value, checked) => {
        const selected = new Set(this._filterValues(state.filters.enabled));
        if (checked) selected.add(value);
        else selected.delete(value);
        state.filters.enabled = [...selected];
        this._filterPaneKind = "rules";
        this._render();
      },
    });
}

export function nativeRuleEntitiesCell(row) {
    if (!globalThis.document?.createElement) return row.entityIds.join(", ");
    const entities = document.createElement("span");
    entities.className = "rule-entities";
    for (const entityId of row.entityIds) {
      const entity = document.createElement("code");
      entity.textContent = entityId;
      entities.append(entity);
    }
    return entities;
}

export function nativeRuleToggleCell(row) {
    if (!globalThis.document?.createElement) return row.enabled;
    const toggle = document.createElement("ha-switch");
    toggle.checked = row.enabled;
    toggle.disabled = this._busy;
    toggle.haptic = true;
    toggle.setAttribute(
      "aria-label",
      this._t(row.enabled ? "rules.aria_disable" : "rules.aria_enable", { name: row.name }),
    );
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!this._busy) void this._toggleRule(row.id);
    });
    return toggle;
}

export function renderRules(context) {
    const { editorOpen, editor, editorWidth, pageMessages, t, renderFacetFilter } = context;
    const statuses = [
      { value: "active", label: t("rules.status_active") },
      { value: "inactive", label: t("rules.status_inactive") },
    ];
    return `<div class="rules-layout ${editorOpen ? "has-editor" : ""}" style="--rule-editor-width:${editorWidth}px">
      <hass-tabs-subpage-data-table
        id="panel-shell"
        data-rules-table-page
        has-filters
        clickable
        main-page
      >
        <div slot="top-header" class="table-page-top">
          ${pageMessages}
          <ha-card outlined class="panel rules-list-panel">
            <div class="rules-header">
              <div><h2>${esc(t("rules.title"))}</h2><p>${esc(t("rules.description"))}</p></div>
              <ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("rules.new"))}</ha-button>
            </div>
          </ha-card>
        </div>
        <div slot="filter-pane" class="filter-pane-content">
          ${renderFacetFilter("rules", "enabled", t("rules.status"), statuses)}
        </div>
      </hass-tabs-subpage-data-table>
      ${editor}
    </div>`;
}

export function renderRulesPanel() {
    this._ensureRulesTableState();
    const editorOpen = this._editingRule !== null;
    return renderRules({
      editorOpen,
      editor: editorOpen ? this._renderRuleEditor() : "",
      editorWidth: this._ruleEditorWidth,
      pageMessages: this._renderPageMessages(),
      t: (key, replacements) => this._t(key, replacements),
      renderFacetFilter: (...args) => this._renderFacetFilter(...args),
    });
}

export function buildRuleTableRows(rules, context) {
    const { t, summarizeRule, formatDuration } = context;
    return rules.map((rule) => {
      const enabled = rule.enabled !== false;
      const row = {
        id: rule.id,
        name: rule.name,
        entityIds: [...(rule.entity_ids ?? [])],
        entities: (rule.entity_ids ?? []).join(", "),
        condition: summarizeRule(rule),
        duration: formatDuration(rule.duration),
        durationSort: Number(rule.duration),
        enabled,
        enabledSort: enabled ? 1 : 0,
        enabledKey: enabled ? "active" : "inactive",
        enabledLabel: t(enabled ? "rules.status_active" : "rules.status_inactive"),
      };
      row.search_index = [
        row.name,
        row.entities,
        row.condition,
        row.duration,
        row.enabledLabel,
      ].join(" ");
      return row;
    });
}

export function ruleTableRows() {
    return buildRuleTableRows(this._config?.rules ?? [], {
      t: (key, replacements) => this._t(key, replacements),
      summarizeRule: (rule) => this._ruleSummary(rule),
      formatDuration: (duration) => this._durationText(duration),
    });
}

export function nativeRuleNameCell(row, narrow = false) {
    if (!narrow || !globalThis.document?.createElement) return row.name;
    const state = this._ensureRulesTableState();
    const hiddenColumns = new Set(state.hiddenColumns);
    const secondaryColumns = state.columnOrder.filter((column) => (
      RULES_SECONDARY_COLUMNS.has(column) && !hiddenColumns.has(column)
    ));
    const content = document.createElement("span");
    content.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";
    const primary = document.createElement("span");
    primary.textContent = row.name;
    primary.style.cssText = "overflow:hidden;color:var(--primary-text-color,#212121);font-weight:var(--ha-font-weight-medium,500);text-overflow:ellipsis;white-space:nowrap";
    content.append(primary);
    if (secondaryColumns.length) {
      const secondary = document.createElement("span");
      secondary.textContent = secondaryColumns
        .map((column) => row[column])
        .filter((value) => value !== undefined && value !== null && value !== "")
        .join(" · ");
      secondary.style.cssText = "display:block;min-width:0;overflow:hidden;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400);text-overflow:ellipsis;white-space:nowrap";
      content.append(secondary);
    }
    return content;
}

export function openRuleEditor(ruleId, { navigate = false } = {}) {
    const rule = (this._config?.rules ?? []).find(
      (item) => String(item.id) === String(ruleId),
    );
    if (!rule) return false;
    if (navigate) {
      this._navigate("/alert-manager/rules");
      this._activeTab = "rules";
    }
    this._editingRule = { ...rule };
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleEditorError = null;
    this._ruleDirty = false;
    if (navigate) this._render();
    else this._refreshRuleEditor();
    return true;
}

export async function handleSelected(event) {
    const path = event.composedPath?.() ?? [event.target];
    const ruleMenu = path.find((node) => node?.dataset?.ruleEditorMenu !== undefined);
    const ruleValue = event.detail?.item?.value ?? event.detail?.value;
    if (!ruleMenu) return;
    if (ruleValue === "switch-editor") {
      await this._switchRuleEditor();
      return;
    }
    if (ruleValue === "duplicate-rule") {
      await this._duplicateRuleDraft();
      return;
    }
    if (ruleValue === "delete-rule" && this._editingRule?.id) {
      await this._deleteRule(this._editingRule.id);
    }
}

export async function deleteRule(ruleId) {
    const rule = (this._config?.rules ?? []).find((item) => item.id === ruleId);
    if (!rule) return;
    if (!window.confirm(this._t("rules.delete_confirm", { name: rule.name }))) return;
    const result = await this._call(
      { type: "alert_manager/rules/delete", rule_id: rule.id },
      this._t("success.rule_deleted"),
    );
    if (result !== null) {
      this._config.rules = this._config.rules.filter((item) => item.id !== rule.id);
      if (this._editingRule?.id === rule.id) this._editingRule = null;
      this._refreshRulesData();
      this._refreshRuleEditor();
    }
}

export async function toggleRule(ruleId) {
    const rule = (this._config?.rules ?? []).find((item) => item.id === ruleId);
    if (!rule || this._busy) return;
    const updated = await this._call(
      { type: "alert_manager/rules/update", rule_id: rule.id, rule: { enabled: !rule.enabled } },
      this._t(rule.enabled ? "success.rule_disabled" : "success.rule_enabled"),
    );
    if (updated) this._replaceRule(updated);
}

export function replaceRule(rule) {
    const index = this._config.rules.findIndex((item) => item.id === rule.id);
    if (index === -1) this._config.rules.push(rule);
    else this._config.rules[index] = rule;
    if (this._editingRule?.id === rule.id) {
      this._editingRule = { ...this._editingRule, enabled: rule.enabled };
    }
    this._refreshRulesData();
    if (this._editingRule === null) this._refreshRuleEditor();
}

export async function handleRulesAction(action, button) {
  if (action === "new-rule") {
    this._editingRule = {};
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleDirty = false;
    this._refreshRuleEditor();
    return true;
  }
  if (action === "cancel-rule") {
    this._cancelRuleEditor();
    return true;
  }
  if (action === "switch-rule-editor") {
    await this._switchRuleEditor();
    return true;
  }
  if (action === "add-rule-value") {
    this._captureRuleDraft();
    this._editingRule.value = [...this._ruleValueList(this._editingRule.value), ""];
    this._ruleDirty = true;
    this._refreshRuleEditor();
    return true;
  }
  if (action === "remove-rule-value") {
    this._captureRuleDraft();
    const values = this._ruleValueList(this._editingRule.value);
    values.splice(Number(button.dataset.index), 1);
    this._editingRule.value = values.length ? values : [""];
    this._ruleDirty = true;
    this._refreshRuleEditor();
    return true;
  }
  if (action === "save-rule") {
    const form = this.shadowRoot.querySelector("#rule-form");
    if (form && !this._busy) {
      if (this._ruleEditorMode === "yaml") await this._saveRuleYaml();
      else if (this._reportFormValidity(form)) await this._saveRule(form);
    }
    return true;
  }
  if (!["edit-rule", "toggle-rule", "delete-rule"].includes(action)) return false;
  const rule = (this._config.rules || []).find((item) => item.id === button.dataset.id);
  if (!rule) return true;
  if (action === "edit-rule") {
    this._openRuleEditor(rule.id);
  } else if (action === "toggle-rule") {
    await this._toggleRule(rule.id);
  } else {
    await this._deleteRule(rule.id);
  }
  return true;
}
