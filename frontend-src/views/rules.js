import { MDI_PLUS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { DEFAULT_RULES_TABLE_STATE, RULES_COLUMNS, RULES_SECONDARY_COLUMNS } from "../utils/table-preferences.js";

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

export function hydrateRuleTable() {
    const tablePage = this.shadowRoot?.querySelector?.("[data-rules-table-page]");
    if (!tablePage || !this._config) return;
    const state = this._ensureRulesTableState();
    const sourceRows = this._ruleTableRows();
    const enabledFilters = new Set(this._filterValues(state.filters.enabled));
    const visibleRows = sourceRows.filter((row) => (
      !enabledFilters.size || enabledFilters.has(row.enabledKey)
    ));
    tablePage.hass = this._hass;
    tablePage.narrow = Boolean(this._narrow);
    tablePage.tabs = this._tabs();
    tablePage.route = { prefix: "", path: "/alert-manager/rules" };
    tablePage.mainPage = true;
    tablePage.backPath = undefined;
    tablePage.backCallback = undefined;
    tablePage.id = "id";
    tablePage.clickable = true;
    tablePage.searchLabel = this._t("rules.search");
    tablePage.filter = state.search;
    tablePage.filters = enabledFilters.size ? 1 : 0;
    tablePage.showFilters = this._filterPaneKind === "rules";
    tablePage.columns = {
      name: {
        title: this._t("rules.name"),
        label: this._t("rules.name"),
        main: true,
        sortable: true,
        hideable: false,
        moveable: false,
        minWidth: "180px",
        flex: 1.2,
        template: (row) => this._nativeRuleNameCell(row, Boolean(this._narrow)),
      },
      entities: {
        title: this._t("rules.entities"),
        sortable: true,
        minWidth: "220px",
        flex: 1.4,
        template: (row) => this._nativeRuleEntitiesCell(row),
      },
      condition: {
        title: this._t("rules.condition"),
        minWidth: "260px",
        flex: 1.7,
      },
      duration: {
        title: this._t("rules.duration"),
        sortable: true,
        valueColumn: "durationSort",
        type: "numeric",
        minWidth: "120px",
        flex: 0.7,
      },
      enabled: {
        title: this._t("rules.status"),
        label: this._t("rules.status"),
        sortable: true,
        valueColumn: "enabledSort",
        type: "icon",
        showNarrow: true,
        hideable: false,
        moveable: false,
        minWidth: "88px",
        flex: 0.5,
        template: (row) => this._nativeRuleToggleCell(row),
      },
      search_index: {
        title: "",
        hidden: true,
        filterable: true,
      },
    };
    tablePage.columnOrder = [...state.columnOrder];
    tablePage.hiddenColumns = [...state.hiddenColumns];
    tablePage.initialSorting = { column: state.sortBy, direction: state.sortDirection };
    tablePage.data = visibleRows;
    tablePage._alertManagerRows = visibleRows;
    tablePage.noDataText = sourceRows.length
      ? this._t("rules.empty_filtered")
      : this._t("rules.empty");
    tablePage.addEventListener("search-changed", (event) => {
      state.search = String(event.detail?.value ?? "");
    });
    tablePage.addEventListener("clear-filter", () => {
      state.filters.enabled = [];
      this._filterPaneKind = "rules";
      this._render();
    });
    tablePage.addEventListener("sorting-changed", (event) => {
      const column = event.detail?.column;
      const direction = event.detail?.direction;
      if (!RULES_COLUMNS.includes(column) || !["asc", "desc"].includes(direction)) return;
      state.sortBy = column;
      state.sortDirection = direction;
      this._saveRulesTableState();
    });
    tablePage.addEventListener("columns-changed", (event) => {
      const order = Array.isArray(event.detail?.columnOrder)
        ? event.detail.columnOrder.filter((column) => RULES_SECONDARY_COLUMNS.has(column))
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
      state.hiddenColumns = (event.detail?.hiddenColumns ?? [])
        .filter((column) => RULES_SECONDARY_COLUMNS.has(column));
      this._saveRulesTableState();
    });
    tablePage.addEventListener("row-click", (event) => {
      const rule = (this._config?.rules ?? []).find(
        (item) => String(item.id) === String(event.detail?.id),
      );
      if (!rule) return;
      this._editingRule = { ...rule };
      this._ruleEditorMode = "visual";
      this._ruleYaml = "";
      this._ruleYamlError = null;
      this._ruleDirty = false;
      this._refreshRuleEditor();
    });
    tablePage.querySelectorAll?.("ha-checkbox[data-table-filter-option]").forEach((checkbox) => {
      const value = checkbox.dataset.filterValue;
      checkbox.checked = this._filterValues(state.filters.enabled).includes(value);
      checkbox.addEventListener("change", (event) => {
        event.stopPropagation();
        const selected = new Set(this._filterValues(state.filters.enabled));
        if (checkbox.checked) selected.add(value);
        else selected.delete(value);
        state.filters.enabled = [...selected];
        this._filterPaneKind = "rules";
        this._render();
      });
    });
    void applyRuleTableEditorLayout(tablePage);
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

export function renderRules() {
    this._ensureRulesTableState();
    const editorOpen = this._editingRule !== null;
    const editor = editorOpen ? this._renderRuleEditor() : "";
    const statuses = [
      { value: "active", label: this._t("rules.status_active") },
      { value: "inactive", label: this._t("rules.status_inactive") },
    ];
    return `<div class="rules-layout ${editorOpen ? "has-editor" : ""}" style="--rule-editor-width:${this._ruleEditorWidth}px">
      <hass-tabs-subpage-data-table
        id="panel-shell"
        data-rules-table-page
        has-filters
        clickable
        main-page
      >
        <div slot="top-header" class="table-page-top">
          ${this._renderPageMessages()}
          <ha-card outlined class="panel rules-list-panel">
            <div class="rules-header">
              <div><h2>${esc(this._t("rules.title"))}</h2><p>${esc(this._t("rules.description"))}</p></div>
              <ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(this._t("rules.new"))}</ha-button>
            </div>
          </ha-card>
        </div>
        <div slot="filter-pane" class="filter-pane-content">
          ${this._renderFacetFilter("rules", "enabled", this._t("rules.status"), statuses)}
        </div>
      </hass-tabs-subpage-data-table>
      ${editor}
    </div>`;
}

export function ruleTableRows() {
    return (this._config?.rules ?? []).map((rule) => {
      const enabled = rule.enabled !== false;
      const row = {
        id: rule.id,
        name: rule.name,
        entityIds: [...(rule.entity_ids ?? [])],
        entities: (rule.entity_ids ?? []).join(", "),
        condition: this._ruleSummary(rule),
        duration: this._durationText(rule.duration),
        durationSort: Number(rule.duration),
        enabled,
        enabledSort: enabled ? 1 : 0,
        enabledKey: enabled ? "active" : "inactive",
        enabledLabel: this._t(enabled ? "rules.status_active" : "rules.status_inactive"),
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
    this._editingRule = { ...rule };
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleDirty = false;
    this._refreshRuleEditor();
  } else if (action === "toggle-rule") {
    await this._toggleRule(rule.id);
  } else {
    await this._deleteRule(rule.id);
  }
  return true;
}
