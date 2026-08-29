const panelModuleUrl = new URL("./alert-manager-panel.js", import.meta.url);
panelModuleUrl.search = new URL(import.meta.url).search;
const { AlertManagerPanel } = await import(panelModuleUrl.href);

const COHERENCE_TABLE_PREFERENCES_KEY = "alert-manager-coherence-table-preferences-v1";
const COHERENCE_STALE_MS = 48 * 60 * 60 * 1000;
const COHERENCE_COLUMNS = ["entity", "type", "source", "file", "line", "action"];
const COHERENCE_SECONDARY_COLUMNS = new Set(["type", "source", "file", "line"]);
const DEFAULT_COHERENCE_TABLE_STATE = Object.freeze({
  columnOrder: Object.freeze([...COHERENCE_COLUMNS]),
  hiddenColumns: Object.freeze([]),
  sortBy: "entity",
  sortDirection: "asc",
  groupBy: "",
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

const narrowDescriptor = Object.getOwnPropertyDescriptor(AlertManagerPanel.prototype, "narrow");

Object.defineProperty(AlertManagerPanel.prototype, "narrow", {
  configurable: true,
  set(value) {
    narrowDescriptor?.set?.call(this, value);
    const table = this.shadowRoot?.querySelector?.("[data-coherence-table-page]");
    if (table) table.narrow = Boolean(this._narrow);
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
