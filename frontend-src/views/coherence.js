import { handleEntityReplacementAction, renderEntityReplacement } from "./entity-replacement.js";
import { MDI_CLOSE } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { renderSideDrawer } from "../components/configuration-drawer.js";
import { downloadTextPayload } from "../components/config-backups.js";
import { COHERENCE_COLUMNS, COHERENCE_SECONDARY_COLUMNS, COHERENCE_STALE_MS, DEFAULT_COHERENCE_TABLE_STATE } from "../utils/table-preferences.js";

export function coherenceStatsMarkup() {
    const result = this._coherence;
    if (!result) return "";
    const scannedAt = result.scanned_at ? new Date(result.scanned_at).getTime() : NaN;
    const scanIsStale = Number.isFinite(scannedAt)
      && Date.now() - scannedAt > COHERENCE_STALE_MS;
    const zhaStatus = result.checks?.zha_device_ieee;
    const zhaSkipped = ["not_loaded", "metadata_error"].includes(zhaStatus);
    return `${zhaSkipped ? `<span class="warning">${esc(this._t(`coherence.zha_status.${zhaStatus}`))}</span>` : ""}
      ${result.scanned_at ? `<span class="coherence-scan-date${scanIsStale ? " stale" : ""}">${esc(this._t("coherence.stats.scanned_at", { date: this._date(result.scanned_at) }))}</span>` : ""}
      <span>${esc(this._t("coherence.stats.missing", { count: result.missing_count ?? 0 }))}</span>
      <span>${esc(this._t("coherence.stats.files", { count: result.files_scanned ?? 0 }))}</span>
      <span>${esc(this._t("coherence.stats.references", { count: result.references_checked ?? 0 }))}</span>
      <span>${esc(this._t("coherence.stats.duration", { duration: result.duration_ms ?? 0 }))}</span>
      ${result.files_skipped ? `<span class="warning">${esc(this._t("coherence.stats.skipped", { count: result.files_skipped }))}</span>` : ""}`;
}

export function coherenceTableRows() {
    return (this._coherence?.results ?? []).map((result, index) => {
      const reference = result.reference ?? result.entity_id;
      const row = {
        id: `${reference}:${result.file}:${result.line}:${index}`,
        entity: reference,
        message: result.reference_type === "zha_device_ieee"
          ? this._t("coherence.zha_missing") : "",
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
}

export function refreshCoherenceData() {
    if (this._activeTab !== "coherence") return;
    const exportButton = this.shadowRoot?.querySelector?.('[data-action="export-entities"]');
    if (exportButton) {
      exportButton.disabled = Boolean(this._entityExportLoading);
      const label = exportButton.querySelector?.("[data-action-label]");
      if (label) label.textContent = this._t(
        this._entityExportLoading ? "coherence.export.loading" : "coherence.export.button",
      );
    }
    const tablePage = this.shadowRoot?.querySelector?.("[data-coherence-table-page]");
    if (!tablePage || !this._coherence) {
      this._render();
      return;
    }
    const stats = tablePage.querySelector?.("[data-coherence-stats]");
    if (stats) stats.innerHTML = this._coherenceStatsMarkup();
    const button = tablePage.querySelector?.('[data-action="scan-coherence"]');
    if (button) {
      button.disabled = this._coherenceLoading;
      const label = button.querySelector?.("[data-action-label]");
      if (label) label.textContent = this._t(
        this._coherenceLoading ? "coherence.scanning" : "coherence.scan",
      );
    }
    const data = this._coherenceTableRows();
    tablePage.hass = this._hass;
    tablePage.data = data;
    tablePage._alertManagerRows = data;
    tablePage.noDataText = this._t("coherence.empty");
    this._refreshUiState();
}

export function hydrateCoherenceTable() {
    const tablePage = this.shadowRoot?.querySelector?.("[data-coherence-table-page]");
    if (!tablePage || !this._coherence) return;
    const state = this._ensureCoherenceTableState();
    tablePage.hass = this._hass;
    tablePage.narrow = Boolean(this._narrow);
    tablePage.tabs = this._tabs();
    tablePage.route = { prefix: "", path: "/alert-manager/coherence" };
    tablePage.mainPage = true;
    tablePage.backPath = undefined;
    tablePage.backCallback = undefined;
    tablePage.id = "id";
    tablePage.clickable = false;
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
    const data = this._coherenceTableRows();
    tablePage.columnOrder = [...state.columnOrder];
    tablePage.hiddenColumns = [...state.hiddenColumns];
    tablePage.initialSorting = { column: state.sortBy, direction: state.sortDirection };
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
      this._saveCoherenceTableState();
    });
    tablePage.addEventListener("grouping-changed", (event) => {
      state.groupBy = event.detail?.value === "entity" ? "entity" : "";
      this._saveCoherenceTableState();
    });
    tablePage.addEventListener("columns-changed", (event) => {
      const order = Array.isArray(event.detail?.columnOrder)
        ? event.detail.columnOrder.filter((column) => COHERENCE_COLUMNS.includes(column))
        : [...DEFAULT_COHERENCE_TABLE_STATE.columnOrder];
      state.columnOrder = [
        ...order,
        ...COHERENCE_COLUMNS.filter((column) => !order.includes(column)),
      ];
      state.hiddenColumns = (event.detail?.hiddenColumns ?? [])
        .filter((column) => COHERENCE_COLUMNS.includes(column) && column !== "entity");
      this._saveCoherenceTableState();
    });
}

export function nativeCoherenceEntityCell(row, narrow = false) {
    if (!globalThis.document?.createElement) return row.entity;
    if (!narrow) {
      const content = document.createElement("span");
      content.textContent = row.entity;
      if (row.message) content.title = row.message;
      return content;
    }
    const state = this._ensureCoherenceTableState();
    const hiddenColumns = new Set(state.hiddenColumns);
    const secondaryColumns = state.columnOrder.filter((column) => (
      COHERENCE_SECONDARY_COLUMNS.has(column) && !hiddenColumns.has(column)
    ));
    const content = document.createElement("span");
    content.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";
    const primary = document.createElement("span");
    primary.textContent = row.entity;
    if (row.message) content.title = row.message;
    primary.style.cssText = "overflow:hidden;color:var(--primary-text-color,#212121);font-weight:var(--ha-font-weight-medium,500);text-overflow:ellipsis;white-space:nowrap";
    content.append(primary);
    if (row.message) {
      const message = document.createElement("span");
      message.textContent = row.message;
      content.append(message);
    }
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

export function openCoherenceLink(link) {
    if (link?.type === "custom_rule") {
      if (!this._readOnly) this._openRuleEditor(link.path, { navigate: true });
    } else if (link?.type === "more_info") this._openMoreInfo(link.entity_id);
    else if (link?.type === "navigate") this._navigate(link.path, true);
}

export function nativeCoherenceActionCell(row) {
    if (!row.link || !globalThis.document?.createElement) return "";
    const button = document.createElement("ha-button");
    button.setAttribute("appearance", "plain");
    button.textContent = this._t("coherence.open");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      this._openCoherenceLink(row.link);
    });
    return button;
}

function renderCoherenceHistoryDrawer({ kind, translationKey, content, useBottomSheet, t }) {
    const drawer = `<ha-card outlined class="side-drawer ${kind}-drawer" role="dialog" aria-modal="false" aria-label="${esc(t(`${translationKey}.title`))}">
        <ha-dialog-header show-border>
          <ha-icon-button slot="navigationIcon" path="${MDI_CLOSE}" data-action="close-${kind}" aria-label="${esc(t(`${translationKey}.close`))}"></ha-icon-button>
          <span slot="title">${esc(t(`${translationKey}.title`))}</span>
        </ha-dialog-header>
        <div class="side-drawer-form"><section class="side-drawer-section">${content}</section></div>
      </ha-card>`;
    return renderSideDrawer({
      drawer,
      backdropClass: `${kind}-drawer-backdrop`,
      closeAction: `close-${kind}`,
      useBottomSheet,
    });
}

export function renderDeletedEntitiesDrawer({
  data, loading, error, formatDate, useBottomSheet = false, t,
}) {
    const entities = data?.entities ?? [];
    const content = loading
      ? `<div class="loading compact">${esc(t("coherence.deleted_entities.loading"))}</div>`
      : error
        ? `<ha-alert alert-type="error">${esc(error)}</ha-alert>`
        : `<p class="deleted-entities-description">${esc(t("coherence.deleted_entities.description"))}</p>
          ${entities.length
            ? `<div class="deleted-entities-list" role="list">${entities.map((entry) => `
              <div class="deleted-entity-row" role="listitem">
                <div class="deleted-entity-primary">
                  <code>${esc(entry.entity_id)}</code>
                  ${entry.name ? `<span>${esc(entry.name)}</span>` : ""}
                </div>
                <div class="deleted-entity-metadata">
                  <span>${esc(entry.platform)}</span>
                  <time datetime="${esc(entry.deleted_at)}">${esc(formatDate(entry.deleted_at))}</time>
                </div>
              </div>`).join("")}</div>`
            : `<div class="empty compact">${esc(t("coherence.deleted_entities.empty"))}</div>`}`;
    return renderCoherenceHistoryDrawer({
      kind: "deleted-entities",
      translationKey: "coherence.deleted_entities",
      content,
      useBottomSheet,
      t,
    });
}

export function renderEntityRenamesDrawer({
  data, loading, error, formatDate, useBottomSheet = false, t,
}) {
    const renames = data?.renames ?? [];
    const content = loading
      ? `<div class="loading compact">${esc(t("coherence.entity_renames.loading"))}</div>`
      : error
        ? `<ha-alert alert-type="error">${esc(error)}</ha-alert>`
        : `<p class="deleted-entities-description">${esc(t("coherence.entity_renames.description"))}</p>
          ${renames.length
            ? `<div class="deleted-entities-list" role="list">${renames.map((entry) => `
              <div class="deleted-entity-row entity-rename-row" role="listitem">
                <div class="entity-rename-ids">
                  <code title="${esc(t("coherence.entity_renames.old"))}">${esc(entry.old_entity_id)}</code>
                  <div class="entity-rename-new">
                    <ha-icon icon="mdi:arrow-right" aria-hidden="true"></ha-icon>
                    <code title="${esc(t("coherence.entity_renames.new"))}">${esc(entry.new_entity_id)}</code>
                  </div>
                </div>
                <time class="deleted-entity-metadata" datetime="${esc(entry.renamed_at)}">${esc(formatDate(entry.renamed_at))}</time>
                <ha-icon-button data-action="more-info" data-entity-id="${esc(entry.current_entity_id ?? "")}" ${entry.current_entity_id ? "" : "disabled"} aria-label="${esc(t("coherence.entity_renames.more_info"))}" title="${esc(t("coherence.entity_renames.more_info"))}"><ha-icon icon="mdi:information-outline"></ha-icon></ha-icon-button>
              </div>`).join("")}</div>`
            : `<div class="empty compact">${esc(t("coherence.entity_renames.empty"))}</div>`}`;
    return renderCoherenceHistoryDrawer({
      kind: "entity-renames",
      translationKey: "coherence.entity_renames",
      content,
      useBottomSheet,
      t,
    });
}

function coherenceActionsMarkup({ loading, deletedEntitiesLoading, entityExportLoading, t }) {
    return `<div class="coherence-actions">
      <div class="coherence-action-column">
      <ha-button appearance="accent" variant="brand" data-action="scan-coherence" ${loading ? "disabled" : ""}><span data-action-label>${esc(t(loading ? "coherence.scanning" : "coherence.scan"))}</span></ha-button>
      <ha-button appearance="outlined" data-action="open-deleted-entities" ${deletedEntitiesLoading ? "disabled" : ""}>${esc(t("coherence.deleted_entities.button"))}</ha-button>
      <ha-button appearance="outlined" data-action="export-entities" ${entityExportLoading ? "disabled" : ""}>
        <span class="coherence-export-label">
          <span aria-hidden="true">${esc(t("coherence.export.button"))}</span>
          <span aria-hidden="true">${esc(t("coherence.export.loading"))}</span>
          <span data-action-label>${esc(t(entityExportLoading ? "coherence.export.loading" : "coherence.export.button"))}</span>
        </span>
      </ha-button>
      </div>
      <div class="coherence-action-column">
        <ha-button appearance="outlined" data-action="open-entity-renames">${esc(t("coherence.entity_renames.button"))}</ha-button>
        <ha-button appearance="outlined" data-action="open-entity-replacement">${esc(t("coherence.replacement.button"))}</ha-button>
      </div>
    </div>`;
}

export function renderCoherence(context) {
    const {
      result,
      loading,
      pageMessages,
      statsMarkup,
      deletedEntities = null,
      deletedEntitiesLoading = false,
      deletedEntitiesError = null,
      deletedEntitiesOpen = false,
      entityRenames = null,
      entityRenamesLoading = false,
      entityRenamesError = null,
      entityRenamesOpen = false,
      entityExportLoading = false,
      entityReplacement = null,
      useBottomSheet = false,
      formatDate = (value) => value,
      t,
    } = context;
    const actions = coherenceActionsMarkup({ loading, deletedEntitiesLoading, entityExportLoading, t });
    const drawer = deletedEntitiesOpen
      ? renderDeletedEntitiesDrawer({
          data: deletedEntities,
          loading: deletedEntitiesLoading,
          error: deletedEntitiesError,
          formatDate,
          useBottomSheet,
          t,
        })
      : entityRenamesOpen
        ? renderEntityRenamesDrawer({
            data: entityRenames,
            loading: entityRenamesLoading,
            error: entityRenamesError,
            formatDate,
            useBottomSheet,
            t,
          })
        : "";
    const replacementDialog = renderEntityReplacement({ state: entityReplacement, t });
    if (!result) {
      return `<ha-card outlined class="panel coherence-panel">
        <div class="coherence-header">
          <div><h2>${esc(t("coherence.title"))}</h2><p>${esc(t("coherence.description"))}</p></div>
          ${actions}
        </div>
        <div class="empty compact">${esc(t("coherence.not_scanned"))}</div>
      </ha-card>${drawer}${replacementDialog}`;
    }
    return `<hass-tabs-subpage-data-table
      id="panel-shell"
      data-coherence-table-page
      main-page
    >
      <div slot="top-header" class="table-page-top">
        ${pageMessages}
        <ha-card outlined class="panel coherence-panel">
          <div class="coherence-header">
            <div><h2>${esc(t("coherence.title"))}</h2><p>${esc(t("coherence.description"))}</p></div>
            ${actions}
          </div>
          <div class="coherence-stats" data-coherence-stats>${statsMarkup}</div>
        </ha-card>
      </div>
    </hass-tabs-subpage-data-table>${drawer}${replacementDialog}`;
}

export function renderCoherencePanel() {
    return renderCoherence({
      result: this._coherence,
      loading: this._coherenceLoading,
      pageMessages: this._coherence ? this._renderPageMessages() : "",
      statsMarkup: this._coherence ? this._coherenceStatsMarkup() : "",
      deletedEntities: this._deletedEntitiesState.data,
      deletedEntitiesLoading: this._deletedEntitiesState.loading,
      deletedEntitiesError: this._deletedEntitiesState.error,
      deletedEntitiesOpen: this._configurationDrawer?.kind === "deleted-entities",
      entityRenames: this._entityRenamesState.data,
      entityRenamesLoading: this._entityRenamesState.loading,
      entityRenamesError: this._entityRenamesState.error,
      entityRenamesOpen: this._configurationDrawer?.kind === "entity-renames",
      entityExportLoading: this._entityExportLoading,
      entityReplacement: this._entityReplacement,
      useBottomSheet: this._useNativeBottomSheet(),
      formatDate: (value) => this._date(value),
      t: (key, replacements) => this._t(key, replacements),
    });
}

export async function handleCoherenceAction(action) {
  if (action.endsWith("-entity-replacement")) return handleEntityReplacementAction.call(this, action);
  if (action === "export-entities") {
    if (this._readOnly || this._entityExportLoading) return true;
    this._entityExportLoading = true;
    this._pageNotice = null;
    this._refreshCoherenceData();
    try {
      const payload = await this._api.exportEntities();
      if (!downloadTextPayload(payload)) throw new Error("entity_export_failed");
    } catch (_error) {
      this._pageNotice = { kind: "error", text: this._t("coherence.export.error") };
    } finally {
      this._entityExportLoading = false;
      this._refreshCoherenceData();
    }
    return true;
  }
  if (["close-deleted-entities", "close-entity-renames"].includes(action)) {
    if (this._configurationDrawer?.kind !== action.slice(6)) return false;
    this._configurationDrawer = null;
    this._render();
    return true;
  }
  if (["open-deleted-entities", "open-entity-renames"].includes(action)) {
    if (this._readOnly) return true;
    const isRenames = action === "open-entity-renames";
    const state = isRenames ? this._entityRenamesState : this._deletedEntitiesState;
    if (state.loading) return true;
    this._configurationDrawer = { kind: action.slice(5) };
    state.loading = true;
    state.error = null;
    this._render();
    try {
      state.data = isRenames
        ? await this._api.entityRenames()
        : await this._api.call({ type: "alert_manager/coherence/deleted_entities/list" });
    } catch (error) {
      state.error = this._errorText(error);
    } finally {
      state.loading = false;
      this._render();
    }
    return true;
  }
  if (action !== "scan-coherence") return false;
  if (this._coherenceLoading) return true;
  this._coherenceLoading = true;
  this._notice = null;
  this._refreshCoherenceData();
  try {
    this._coherence = await this._api.call({ type: "alert_manager/coherence/scan" });
    this._coherenceScannedAt = this._coherence?.scanned_at ?? this._coherenceScannedAt;
  } catch (error) {
    this._notice = { kind: "error", text: this._errorText(error) };
  } finally {
    this._coherenceLoading = false;
    this._refreshCoherenceData();
  }
  return true;
}
