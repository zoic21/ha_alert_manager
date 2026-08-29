const panelModuleUrl = new URL("./alert-manager-panel.js", import.meta.url);
panelModuleUrl.search = new URL(import.meta.url).search;
const { AlertManagerPanel } = await import(panelModuleUrl.href);

const COHERENCE_TABLE_PREFERENCES_KEY = "alert-manager-coherence-table-preferences-v1";
const RULES_TABLE_PREFERENCES_KEY = "alert-manager-rules-table-preferences-v1";
const COHERENCE_STALE_MS = 48 * 60 * 60 * 1000;
const COHERENCE_COLUMNS = ["entity", "type", "source", "file", "line", "action"];
const COHERENCE_SECONDARY_COLUMNS = new Set(["type", "source", "file", "line"]);
const RULES_COLUMNS = ["name", "entities", "condition", "duration", "enabled"];
const RULES_SECONDARY_COLUMNS = new Set(["entities", "condition", "duration"]);
const DEFAULT_COHERENCE_TABLE_STATE = Object.freeze({
  columnOrder: Object.freeze([...COHERENCE_COLUMNS]),
  hiddenColumns: Object.freeze([]),
  sortBy: "entity",
  sortDirection: "asc",
  groupBy: "",
});
const DEFAULT_RULES_TABLE_STATE = Object.freeze({
  columnOrder: Object.freeze([...RULES_COLUMNS]),
  hiddenColumns: Object.freeze([]),
  sortBy: "name",
  sortDirection: "asc",
});
const ACTION_ICONS = Object.freeze({
  "save-automatic": "mdi:content-save",
  "save-rule": "mdi:content-save",
  "save-settings": "mdi:content-save",
  "scan-coherence": "mdi:refresh",
});

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const decorateActionIcons = (panel) => {
  if (!globalThis.document?.createElement) return;
  for (const [action, iconName] of Object.entries(ACTION_ICONS)) {
    const buttons = panel.shadowRoot?.querySelectorAll?.(`[data-action="${action}"]`) ?? [];
    for (const button of buttons) {
      if (button.querySelector?.("[data-alert-manager-action-icon]")) continue;
      const icon = document.createElement("ha-icon");
      icon.setAttribute("slot", "start");
      icon.setAttribute("icon", iconName);
      icon.setAttribute("data-alert-manager-action-icon", "");
      button.prepend(icon);
    }
  }
};

const ensureCoherenceTableState = (panel) => {
  if (panel._coherenceTableState) return panel._coherenceTableState;

  let stored = {};
  try {
    stored = JSON.parse(window.localStorage?.getItem(COHERENCE_TABLE_PREFERENCES_KEY) ?? "{}");
  } catch (_error) {
    stored = {};
  }

  const storedOrder = Array.isArray(stored.columnOrder)
    ? stored.columnOrder.filter((column, index, columns) => (
      COHERENCE_COLUMNS.includes(column) && columns.indexOf(column) === index
    ))
    : [];
  const columnOrder = [
    ...storedOrder,
    ...COHERENCE_COLUMNS.filter((column) => !storedOrder.includes(column)),
  ];
  const hiddenColumns = Array.isArray(stored.hiddenColumns)
    ? stored.hiddenColumns.filter((column) => (
      COHERENCE_COLUMNS.includes(column) && column !== "entity"
    ))
    : [];
  const sortBy = COHERENCE_COLUMNS.includes(stored.sortBy)
    && stored.sortBy !== "action"
    ? stored.sortBy
    : DEFAULT_COHERENCE_TABLE_STATE.sortBy;
  const sortDirection = ["asc", "desc"].includes(stored.sortDirection)
    ? stored.sortDirection
    : DEFAULT_COHERENCE_TABLE_STATE.sortDirection;

  panel._coherenceTableState = {
    search: "",
    columnOrder,
    hiddenColumns,
    sortBy,
    sortDirection,
    groupBy: stored.groupBy === "entity" ? "entity" : "",
  };
  return panel._coherenceTableState;
};

const saveCoherenceTableState = (panel) => {
  const state = ensureCoherenceTableState(panel);
  try {
    window.localStorage?.setItem(COHERENCE_TABLE_PREFERENCES_KEY, JSON.stringify({
      columnOrder: state.columnOrder,
      hiddenColumns: state.hiddenColumns,
      sortBy: state.sortBy,
      sortDirection: state.sortDirection,
      groupBy: state.groupBy,
    }));
  } catch (_error) {
    // Private browsing or a full storage quota must not make the panel unusable.
  }
};

const ensureRulesTableState = (panel) => {
  if (panel._tableState?.rules) return panel._tableState.rules;

  let stored = {};
  try {
    stored = JSON.parse(window.localStorage?.getItem(RULES_TABLE_PREFERENCES_KEY) ?? "{}");
  } catch (_error) {
    stored = {};
  }

  const storedOrder = Array.isArray(stored.columnOrder)
    ? stored.columnOrder.filter((column, index, columns) => (
      RULES_COLUMNS.includes(column) && columns.indexOf(column) === index
    ))
    : [];
  const optionalOrder = storedOrder.filter((column) => RULES_SECONDARY_COLUMNS.has(column));
  const columnOrder = [
    "name",
    ...optionalOrder,
    ...RULES_COLUMNS.filter((column) => (
      RULES_SECONDARY_COLUMNS.has(column) && !optionalOrder.includes(column)
    )),
    "enabled",
  ];
  const hiddenColumns = Array.isArray(stored.hiddenColumns)
    ? stored.hiddenColumns.filter((column) => RULES_SECONDARY_COLUMNS.has(column))
    : [];
  const sortBy = RULES_COLUMNS.includes(stored.sortBy)
    ? stored.sortBy
    : DEFAULT_RULES_TABLE_STATE.sortBy;
  const sortDirection = ["asc", "desc"].includes(stored.sortDirection)
    ? stored.sortDirection
    : DEFAULT_RULES_TABLE_STATE.sortDirection;

  panel._tableState ??= {};
  panel._tableState.rules = {
    search: "",
    filters: { enabled: [] },
    columnOrder,
    hiddenColumns,
    sortBy,
    sortDirection,
  };
  return panel._tableState.rules;
};

const saveRulesTableState = (panel) => {
  const state = ensureRulesTableState(panel);
  try {
    window.localStorage?.setItem(RULES_TABLE_PREFERENCES_KEY, JSON.stringify({
      columnOrder: state.columnOrder,
      hiddenColumns: state.hiddenColumns,
      sortBy: state.sortBy,
      sortDirection: state.sortDirection,
    }));
  } catch (_error) {
    // Private browsing or a full storage quota must not make the panel unusable.
  }
};

const narrowDescriptor = Object.getOwnPropertyDescriptor(AlertManagerPanel.prototype, "narrow");

Object.defineProperty(AlertManagerPanel.prototype, "narrow", {
  configurable: true,
  set(value) {
    narrowDescriptor?.set?.call(this, value);
    for (const selector of ["[data-coherence-table-page]", "[data-rules-table-page]"]) {
      const table = this.shadowRoot?.querySelector?.(selector);
      if (table) table.narrow = Boolean(this._narrow);
    }
  },
});

const baseTabs = AlertManagerPanel.prototype._tabs;
AlertManagerPanel.prototype._tabs = function() {
  const tabs = baseTabs.call(this);
  const automaticIndex = tabs.findIndex((tab) => tab.path === "/alert-manager/automatic");
  const rulesIndex = tabs.findIndex((tab) => tab.path === "/alert-manager/rules");
  if (automaticIndex < 0 || rulesIndex < 0 || rulesIndex < automaticIndex) return tabs;

  const reorderedTabs = [...tabs];
  const [rulesTab] = reorderedTabs.splice(rulesIndex, 1);
  reorderedTabs.splice(automaticIndex, 0, rulesTab);
  return reorderedTabs;
};

const baseHandleClick = AlertManagerPanel.prototype._handleClick;
AlertManagerPanel.prototype._handleClick = async function(event) {
  const button = event.target?.closest?.("[data-action]");
  if (button?.dataset.action === "filter-summary-status") {
    const status = button.dataset.status;
    if (["active", "pending", "acknowledged"].includes(status)) {
      const selectedStatuses = this._filterValues(this._tableState.overview.filters.status);
      if (selectedStatuses.length === 1 && selectedStatuses[0] === status) {
        this._tableState.overview.filters.status = [];
        this._render();
        return;
      }
    }
  }
  await baseHandleClick.call(this, event);
};

const baseStyles = AlertManagerPanel.prototype._styles;
AlertManagerPanel.prototype._styles = function() {
  return `${baseStyles.call(this)}
    .automatic-grid{width:100%;max-width:1120px;margin-inline:auto}
    .rules-header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
    .rules-header>div{min-width:0}.rules-header ha-button{flex:none}
    .rules-layout.has-editor [data-rules-table-page]{width:auto;margin-inline-end:calc(var(--rule-editor-width) + 8px)}
    @media(max-width:1000px){.rules-layout.has-editor [data-rules-table-page]{width:100%;margin-inline-end:0}}
    @media(max-width:700px){.rules-header{align-items:stretch;flex-direction:column}.rules-header ha-button{width:100%}}
  `;
};

AlertManagerPanel.prototype._nativeCoherenceEntityCell = function(row, narrow = false) {
  if (!narrow || !globalThis.document?.createElement) return row.entity;
  const state = ensureCoherenceTableState(this);
  const hiddenColumns = new Set(state.hiddenColumns);
  const secondaryColumns = state.columnOrder.filter((column) => (
    COHERENCE_SECONDARY_COLUMNS.has(column) && !hiddenColumns.has(column)
  ));

  const content = document.createElement("span");
  content.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";

  const primary = document.createElement("span");
  primary.textContent = row.entity;
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
};

AlertManagerPanel.prototype._openCoherenceLink = function(link) {
  if (link?.type === "more_info") {
    this._openMoreInfo(link.entity_id);
  } else if (link?.type === "navigate") {
    this._navigate(link.path, true);
  }
};

const baseRenderCoherence = AlertManagerPanel.prototype._renderCoherence;
AlertManagerPanel.prototype._renderCoherence = function() {
  const result = this._coherence;
  if (!result) return baseRenderCoherence.call(this);

  const scannedAt = result.scanned_at ? new Date(result.scanned_at).getTime() : NaN;
  const scanIsStale = Number.isFinite(scannedAt)
    && Date.now() - scannedAt > COHERENCE_STALE_MS;
  const stats = `<div class="coherence-stats">
    ${result.scanned_at ? `<span class="coherence-scan-date${scanIsStale ? " stale" : ""}">${escapeHtml(this._t("coherence.stats.scanned_at", { date: this._date(result.scanned_at) }))}</span>` : ""}
    <span>${escapeHtml(this._t("coherence.stats.missing", { count: result.missing_count ?? 0 }))}</span>
    <span>${escapeHtml(this._t("coherence.stats.files", { count: result.files_scanned ?? 0 }))}</span>
    <span>${escapeHtml(this._t("coherence.stats.references", { count: result.references_checked ?? 0 }))}</span>
    <span>${escapeHtml(this._t("coherence.stats.duration", { duration: result.duration_ms ?? 0 }))}</span>
    ${result.files_skipped ? `<span class="warning">${escapeHtml(this._t("coherence.stats.skipped", { count: result.files_skipped }))}</span>` : ""}
  </div>`;

  return `<hass-tabs-subpage-data-table
    id="panel-shell"
    data-coherence-table-page
    clickable
    main-page
  >
    <div slot="top-header" class="table-page-top">
      ${this._renderPageMessages()}
      <ha-card outlined class="panel coherence-panel">
        <div class="coherence-header">
          <div><h2>${escapeHtml(this._t("coherence.title"))}</h2><p>${escapeHtml(this._t("coherence.description"))}</p></div>
          <ha-button appearance="accent" variant="brand" data-action="scan-coherence" ${this._coherenceLoading ? "disabled" : ""}>${escapeHtml(this._t(this._coherenceLoading ? "coherence.scanning" : "coherence.scan"))}</ha-button>
        </div>
        ${stats}
      </ha-card>
    </div>
  </hass-tabs-subpage-data-table>`;
};

AlertManagerPanel.prototype._ruleTableRows = function() {
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
};

AlertManagerPanel.prototype._nativeRuleNameCell = function(row, narrow = false) {
  if (!narrow || !globalThis.document?.createElement) return row.name;
  const state = ensureRulesTableState(this);
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
};

AlertManagerPanel.prototype._renderRules = function() {
  ensureRulesTableState(this);
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
            <div><h2>${escapeHtml(this._t("rules.title"))}</h2><p>${escapeHtml(this._t("rules.description"))}</p></div>
            <ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start" path="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"></ha-svg-icon>${escapeHtml(this._t("rules.new"))}</ha-button>
          </div>
        </ha-card>
      </div>
      <div slot="filter-pane" class="filter-pane-content">
        ${this._renderFacetFilter("rules", "enabled", this._t("rules.status"), statuses)}
      </div>
    </hass-tabs-subpage-data-table>
    ${editor}
  </div>`;
};

const baseRender = AlertManagerPanel.prototype._render;
AlertManagerPanel.prototype._render = function() {
  if (
    this._activeTab !== "coherence"
    || this._loading
    || !this._config
    || !this._coherence
  ) {
    baseRender.call(this);
    decorateActionIcons(this);
    return;
  }
  if (!this.shadowRoot) return;

  this.shadowRoot.innerHTML = `
    <style>${this._styles()}</style>
    ${this._renderCoherence()}`;
  this._hydrateSelectors();
  this._hydrateDataTables();
  this._hydrateRuleTable();
  this._hydrateCoherenceTable();
  this._hydrateYamlEditor();
  this._updateCountdowns();
  decorateActionIcons(this);
};

AlertManagerPanel.prototype._hydrateCoherenceTable = function() {
  const tablePage = this.shadowRoot?.querySelector?.("[data-coherence-table-page]");
  if (!tablePage || !this._coherence) return;

  const state = ensureCoherenceTableState(this);
  tablePage.hass = this._hass;
  tablePage.narrow = Boolean(this._narrow);
  tablePage.tabs = this._tabs();
  tablePage.route = { prefix: "", path: "/alert-manager/coherence" };
  tablePage.mainPage = true;
  tablePage.backPath = undefined;
  tablePage.backCallback = undefined;
  tablePage.id = "id";
  tablePage.clickable = true;
  tablePage.searchLabel = this._t("table.search");
  tablePage.filter = state.search;
  tablePage.columns = {
    entity: {
      title: this._t("coherence.columns.entity"),
      label: this._t("coherence.columns.entity"),
      main: true,
      sortable: true,
      groupable: true,
      hideable: false,
      minWidth: "190px",
      flex: 1.2,
      template: (row) => this._nativeCoherenceEntityCell(row, Boolean(this._narrow)),
    },
    type: {
      title: this._t("coherence.columns.type"),
      sortable: true,
      minWidth: "130px",
      flex: 0.8,
    },
    source: {
      title: this._t("coherence.columns.source"),
      sortable: true,
      minWidth: "180px",
      flex: 1.1,
    },
    file: {
      title: this._t("coherence.columns.file"),
      sortable: true,
      minWidth: "220px",
      flex: 1.4,
    },
    line: {
      title: this._t("coherence.columns.line"),
      sortable: true,
      valueColumn: "lineSort",
      type: "numeric",
      minWidth: "72px",
      flex: 0.4,
    },
    action: {
      title: "",
      label: this._t("coherence.open"),
      minWidth: "100px",
      flex: 0.5,
      template: (row) => this._nativeCoherenceActionCell(row),
    },
    search_index: {
      title: "",
      hidden: true,
      filterable: true,
    },
  };

  const data = (this._coherence.results ?? []).map((result, index) => {
    const row = {
      id: `${result.entity_id}:${result.file}:${result.line}:${index}`,
      entity: result.entity_id,
      type: this._t(`coherence.types.${result.source_type}`),
      source: result.source_name || "—",
      file: result.file,
      line: String(result.line),
      lineSort: Number(result.line),
      link: result.link ?? null,
    };
    row.search_index = [row.entity, row.type, row.source, row.file, row.line].join(" ");
    return row;
  });

  tablePage.columnOrder = [...state.columnOrder];
  tablePage.hiddenColumns = [...state.hiddenColumns];
  tablePage.initialSorting = {
    column: state.sortBy,
    direction: state.sortDirection,
  };
  tablePage.initialGroupColumn = state.groupBy || undefined;
  tablePage.data = data;
  tablePage._alertManagerRows = data;
  tablePage.noDataText = this._t("coherence.empty");

  tablePage.addEventListener("search-changed", (event) => {
    state.search = String(event.detail?.value ?? "");
  });
  tablePage.addEventListener("sorting-changed", (event) => {
    const column = event.detail?.column;
    const direction = event.detail?.direction;
    if (!COHERENCE_COLUMNS.includes(column) || column === "action") return;
    if (!["asc", "desc"].includes(direction)) return;
    state.sortBy = column;
    state.sortDirection = direction;
    saveCoherenceTableState(this);
  });
  tablePage.addEventListener("grouping-changed", (event) => {
    state.groupBy = event.detail?.value === "entity" ? "entity" : "";
    saveCoherenceTableState(this);
  });
  tablePage.addEventListener("columns-changed", (event) => {
    const order = Array.isArray(event.detail?.columnOrder)
      ? event.detail.columnOrder.filter((column) => COHERENCE_COLUMNS.includes(column))
      : [...DEFAULT_COHERENCE_TABLE_STATE.columnOrder];
    state.columnOrder = [
      ...order,
      ...COHERENCE_COLUMNS.filter((column) => !order.includes(column)),
    ];
    const hidden = new Set(
      (event.detail?.hiddenColumns ?? [])
        .filter((column) => COHERENCE_COLUMNS.includes(column) && column !== "entity"),
    );
    state.hiddenColumns = [...hidden];
    saveCoherenceTableState(this);
  });
  tablePage.addEventListener("row-click", (event) => {
    const row = tablePage._alertManagerRows?.find(
      (item) => String(item.id) === String(event.detail?.id),
    );
    if (row?.link) this._openCoherenceLink(row.link);
  });
};

AlertManagerPanel.prototype._hydrateRuleTable = function() {
  const tablePage = this.shadowRoot?.querySelector?.("[data-rules-table-page]");
  if (!tablePage || !this._config) return;

  const state = ensureRulesTableState(this);
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
      sortable: true,
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
  tablePage.initialSorting = {
    column: state.sortBy,
    direction: state.sortDirection,
  };
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
    if (!RULES_COLUMNS.includes(column)) return;
    if (!["asc", "desc"].includes(direction)) return;
    state.sortBy = column;
    state.sortDirection = direction;
    saveRulesTableState(this);
  });
  tablePage.addEventListener("columns-changed", (event) => {
    const order = Array.isArray(event.detail?.columnOrder)
      ? event.detail.columnOrder.filter((column) => RULES_SECONDARY_COLUMNS.has(column))
      : DEFAULT_RULES_TABLE_STATE.columnOrder.filter((column) => RULES_SECONDARY_COLUMNS.has(column));
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
    saveRulesTableState(this);
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
};
