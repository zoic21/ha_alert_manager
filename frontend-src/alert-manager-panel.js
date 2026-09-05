import { hydrateDurationFields, renderDurationField, validateDurationFields } from "./components/duration-field.js";
import { AlertManagerApi, call, load, refreshAlerts, refreshCoherence, refreshHistory,
  refreshNotificationStats, refreshTabData, rememberPanelState, restorePanelState, setHass, syncSensor,
} from "./api/alert-manager-api.js";
import {
  alertDetailsItems, alertRuleName, cancelMoreInfoScrollRestore, closeAlertDetailsDialog,
  compareTableRows, configureDateRangePicker, dateMatches, dateRangeDefaults, dialogEventTarget,
  displayValue, entityMetadata, facetOptions, filterCount, filteredTableRows, filterValues,
  handleAlertDetailsSelection, handleAlertTableAction, hydrateAlertDetailTimestamps, hydrateDataTables, integrationLabel, loadNativeDateRangePicker,
  nativeDeviceCell, nativeEntityCell, nativeEntityIdCell, nativeGroupColumn,
  nativeRuleCell, nativeSortColumn, nativeStatusCell, nativeTableCell, nativeTableColumns,
  nativeTableData, nativeTimelineCell, navigate, openAlertDeepLink, openAlertDetails, openMoreInfo,
  overviewContentScroller, preserveOverviewScrollAfterMoreInfo, refreshAlertTableData,
  renderAlertDetailsPanel, renderAlertTable, renderDateFilter, renderFacetFilter, renderFilterPane,
  resetTableFilters, syncNarrowTableHeaderBackgrounds, tableColumns, tableRows,
  tableSortStateColumn, tableStateGroupColumn, updateSelectionToolbar,
} from "./components/alert-table.js";
import { applyCompleteConfiguration, handleConfigBackupAction, hydrateConfigBackups, renderBackupRestoreDialogPanel, renderConfigBackups } from "./components/config-backups.js";
import {
  handleBottomSheetClosed, isCompanionApp, loadNativeBottomSheet, SIDE_DRAWER_OPEN_ACTIONS,
  updateDrawerLayout, useNativeBottomSheet,
} from "./components/configuration-drawer.js";
import { captureNotificationProfileDraft, handleNotificationProfileAction } from "./components/notification-profiles.js";
import {
  cancelRuleEditor, captureRuleDraft, clearRuleEditorError, clearRuleTestResult,
  duplicateRuleDraft, duplicateRuleLabel, handleRuleInput, hydrateRuleEditorControls, refreshRuleAttributeSelector,
  refreshRuleConditionSection, refreshRuleEditor, renderRuleEditorPanel, renderRuleTestResultPanel,
  resetRuleEditorWidth, resizeRuleEditor, ruleAttributeOptions,
  ruleSummary, ruleValueList, saveRule, saveRuleYaml, setRuleEditorWidth, testRule,
  startRuleEditorResize, stopRuleEditorResize, switchRuleEditor, updateRuleTestDisplay,
} from "./components/rule-editor.js";
import { panelStyles } from "./styles/panel-styles.js";
import { ACTION_ICONS, TABS } from "./utils/constants.js";
import { esc } from "./utils/escaping.js";
import { conditionText, date, durationText, historyDurationText, lines, newRuleDefaults, remaining, updateCountdowns } from "./utils/formatting.js";
import {
  ensureCoherenceTableState, ensureRulesTableState, loadTablePreferences, makeTableState,
  saveCoherenceTableState, saveRulesTableState, saveTablePreferences,
} from "./utils/table-preferences.js";
import { fetchTranslations, reloadTranslations, t, errorText } from "./utils/translations.js";
import {
  applyOptimisticAcknowledgement, bulkAlertAction, handleOverviewAction,
  refreshOverviewData, refreshStartupBanner, renderOverviewPanel,
  updateAlertAcknowledgement,
} from "./views/overview.js";
import { handleHistoryAction, historyConditionText, historyRuleName, refreshHistoryData, renderHistoryPanel } from "./views/history.js";
import {
  coherenceStatsMarkup, coherenceTableRows, handleCoherenceAction, hydrateCoherenceTable,
  nativeCoherenceActionCell, nativeCoherenceEntityCell, openCoherenceLink,
  refreshCoherenceData, renderCoherencePanel,
} from "./views/coherence.js";
import {
  deleteRule, handleRulesAction, handleSelected, hydrateRuleTable, nativeRuleEntitiesCell,
  nativeRuleNameCell, nativeRuleToggleCell, openRuleEditor, refreshRulesData, renderRulesPanel,
  replaceRule, ruleTableRows, syncRuleTableEditingHighlight, toggleRule,
} from "./views/rules.js";
import { captureAutomaticConfigurationValues, captureAutomaticMapValues, ensureAutomaticDraft, handleAutomaticAction, hydrateAutomaticControls, renderAutomaticPanel, resetAutomaticDraft, saveAutomatic } from "./views/automatic.js";
import {
  captureEntityDelayValues, commitIgnoredReferenceInput, ensureSettingsDraft, exportConfiguration,
  handleImportSelection, handleSettingsAction, handleSettingsInput, hydrateSettingsControls, removeIgnoredReference,
  markConfigurationControlDirty, markConfigurationDirty, refreshNotificationProfileUsage, refreshSettingsConfigurationDrawer, renderSettingsPanel,
  resetSettingsDraft, saveConfiguration, saveSettings, setEntityDelayEntity, updateConfigurationSaveButton,
} from "./views/settings.js";
const ACTION_HANDLERS = [
  handleConfigBackupAction,
  handleAlertTableAction,
  handleOverviewAction,
  handleHistoryAction,
  handleCoherenceAction,
  handleAutomaticAction,
  handleNotificationProfileAction,
  handleSettingsAction,
  handleRulesAction,
];
class AlertManagerPanel extends HTMLElement {
  _load = load;
  _refreshHistory = refreshHistory;
  _refreshCoherence = refreshCoherence; _refreshNotificationStats = refreshNotificationStats;
  _refreshAlerts = refreshAlerts;
  _refreshTabData = refreshTabData;
  _rememberPanelState = rememberPanelState;
  _restorePanelState = restorePanelState;
  _applyCompleteConfiguration = applyCompleteConfiguration;
  _hydrateConfigBackups = hydrateConfigBackups;
  _renderConfigBackups = renderConfigBackups;
  _useNativeBottomSheet = useNativeBottomSheet;
  _loadNativeBottomSheet = loadNativeBottomSheet;
  _updateDrawerLayout = updateDrawerLayout;
  _renderBackupRestoreDialog = renderBackupRestoreDialogPanel;
  _call = call;
  _refreshOverviewData = refreshOverviewData;
  _refreshStartupBanner = refreshStartupBanner; _renderOverview = renderOverviewPanel;
  _bulkAlertAction = bulkAlertAction;
  _applyOptimisticAcknowledgement = applyOptimisticAcknowledgement;
  _updateAlertAcknowledgement = updateAlertAcknowledgement;
  _handleAlertDetailsSelection = handleAlertDetailsSelection; _hydrateAlertDetailTimestamps = hydrateAlertDetailTimestamps;
  _refreshHistoryData = refreshHistoryData;
  _renderHistory = renderHistoryPanel;
  _historyRuleName = historyRuleName;
  _historyConditionText = historyConditionText;
  _coherenceStatsMarkup = coherenceStatsMarkup;
  _coherenceTableRows = coherenceTableRows;
  _refreshCoherenceData = refreshCoherenceData;
  _hydrateCoherenceTable = hydrateCoherenceTable;
  _nativeCoherenceEntityCell = nativeCoherenceEntityCell;
  _openCoherenceLink = openCoherenceLink;
  _nativeCoherenceActionCell = nativeCoherenceActionCell;
  _renderCoherence = renderCoherencePanel;
  _refreshRulesData = refreshRulesData;
  _hydrateRuleTable = hydrateRuleTable;
  _nativeRuleEntitiesCell = nativeRuleEntitiesCell;
  _nativeRuleToggleCell = nativeRuleToggleCell;
  _renderRules = renderRulesPanel;
  _ruleTableRows = ruleTableRows;
  _nativeRuleNameCell = nativeRuleNameCell;
  _handleSelected = handleSelected;
  _deleteRule = deleteRule;
  _toggleRule = toggleRule;
  _replaceRule = replaceRule;
  _renderAutomatic = renderAutomaticPanel;
  _saveAutomatic = saveAutomatic;
  _resetAutomaticDraft = resetAutomaticDraft;
  _ensureAutomaticDraft = ensureAutomaticDraft;
  _captureAutomaticMapValues = captureAutomaticMapValues;
  _captureAutomaticConfigurationValues = captureAutomaticConfigurationValues;
  _renderSettings = renderSettingsPanel;
  _commitIgnoredReferenceInput = commitIgnoredReferenceInput;
  _removeIgnoredReference = removeIgnoredReference;
  _exportConfiguration = exportConfiguration;
  _handleImportSelection = handleImportSelection;
  _saveSettings = saveSettings; _saveConfiguration = saveConfiguration;
  _resetSettingsDraft = resetSettingsDraft; _markConfigurationDirty = markConfigurationDirty;
  _markConfigurationControlDirty = markConfigurationControlDirty; _updateConfigurationSaveButton = updateConfigurationSaveButton;
  _ensureSettingsDraft = ensureSettingsDraft;
  _captureEntityDelayValues = captureEntityDelayValues; _refreshNotificationProfileUsage = refreshNotificationProfileUsage;
  _captureNotificationProfileDraft() { captureNotificationProfileDraft(this); }
  _refreshSettingsConfigurationDrawer = refreshSettingsConfigurationDrawer;
  _setEntityDelayEntity = setEntityDelayEntity;
  _refreshAlertTableData = refreshAlertTableData;
  _loadNativeDateRangePicker = loadNativeDateRangePicker;
  _configureDateRangePicker = configureDateRangePicker;
  _hydrateDataTables = hydrateDataTables;
  _updateSelectionToolbar = updateSelectionToolbar;
  _tableColumns = tableColumns;
  _alertRuleName = alertRuleName;
  _displayValue = displayValue;
  _entityMetadata = entityMetadata;
  _integrationLabel = integrationLabel;
  _tableRows = tableRows;
  _filterCount = filterCount;
  _filterValues = filterValues;
  _resetTableFilters = resetTableFilters;
  _filteredTableRows = filteredTableRows;
  _dateMatches = dateMatches;
  _compareTableRows = compareTableRows;
  _renderAlertTable = renderAlertTable;
  _facetOptions = facetOptions;
  _renderFacetFilter = renderFacetFilter;
  _dateRangeDefaults = dateRangeDefaults;
  _renderDateFilter = renderDateFilter;
  _renderFilterPane = renderFilterPane;
  _nativeTableColumns = nativeTableColumns;
  _nativeTableData = nativeTableData;
  _nativeGroupColumn = nativeGroupColumn;
  _tableStateGroupColumn = tableStateGroupColumn;
  _nativeSortColumn = nativeSortColumn;
  _tableSortStateColumn = tableSortStateColumn;
  _nativeTableCell = nativeTableCell;
  _nativeStatusCell = nativeStatusCell;
  _nativeEntityCell = nativeEntityCell;
  _nativeEntityIdCell = nativeEntityIdCell;
  _nativeDeviceCell = nativeDeviceCell;
  _nativeRuleCell = nativeRuleCell;
  _nativeTimelineCell = nativeTimelineCell;
  _alertDetailsItems = alertDetailsItems;
  _renderAlertDetails = renderAlertDetailsPanel;
  _openAlertDetails = openAlertDetails;
  _openAlertDeepLink = openAlertDeepLink;
  _closeAlertDetailsDialog = closeAlertDetailsDialog;
  _openMoreInfo = openMoreInfo;
  _overviewContentScroller = overviewContentScroller;
  _dialogEventTarget = dialogEventTarget;
  _cancelMoreInfoScrollRestore = cancelMoreInfoScrollRestore;
  _preserveOverviewScrollAfterMoreInfo = preserveOverviewScrollAfterMoreInfo;
  _navigate = navigate;
  _syncNarrowTableHeaderBackgrounds = syncNarrowTableHeaderBackgrounds;
  _refreshRuleEditor = refreshRuleEditor;
  _refreshRuleConditionSection = refreshRuleConditionSection;
  _syncRuleTableEditingHighlight = syncRuleTableEditingHighlight;
  _openRuleEditor = openRuleEditor;
  _clearRuleEditorError = clearRuleEditorError;
  _clearRuleTestResult = clearRuleTestResult;
  _ruleAttributeOptions = ruleAttributeOptions;
  _refreshRuleAttributeSelector = refreshRuleAttributeSelector;
  _renderRuleEditor = renderRuleEditorPanel;
  _renderRuleTestResult = renderRuleTestResultPanel;
  _updateRuleTestDisplay = updateRuleTestDisplay;
  _ruleValueList = ruleValueList;
  _ruleSummary = ruleSummary;
  _duplicateRuleLabel = duplicateRuleLabel;
  _duplicateRuleDraft = duplicateRuleDraft;
  _handleRuleInput = handleRuleInput;
  _cancelRuleEditor = cancelRuleEditor;
  _switchRuleEditor = switchRuleEditor;
  _saveRuleYaml = saveRuleYaml;
  _startRuleEditorResize = startRuleEditorResize;
  _resizeRuleEditor = resizeRuleEditor;
  _setRuleEditorWidth = setRuleEditorWidth;
  _stopRuleEditorResize = stopRuleEditorResize;
  _resetRuleEditorWidth = resetRuleEditorWidth;
  _saveRule = saveRule;
  _testRule = testRule;
  _captureRuleDraft = captureRuleDraft;
  _date = date;
  _remaining = remaining;
  _durationText = durationText;
  _historyDurationText = historyDurationText;
  _conditionText = conditionText;
  _updateCountdowns = updateCountdowns;
  _fetchTranslations = fetchTranslations;
  _reloadTranslations = reloadTranslations;
  _t = t;
  _errorText = errorText;
  _loadTablePreferences = loadTablePreferences;
  _saveTablePreferences = saveTablePreferences;
  _ensureCoherenceTableState = ensureCoherenceTableState;
  _saveCoherenceTableState = saveCoherenceTableState;
  _ensureRulesTableState = ensureRulesTableState;
  _saveRulesTableState = saveRulesTableState;
  _hydrateRuleEditorControls = hydrateRuleEditorControls;
  _hydrateAutomaticControls = hydrateAutomaticControls;
  _hydrateSettingsControls = hydrateSettingsControls;
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._api = new AlertManagerApi(() => this._hass);
    this._language = "en";
    this._translations = {};
    this._englishTranslations = {};
    this._translationPromise = null;
    this._config = null;
    this._packs = [];
    this._alerts = {
      active_count: 0,
      acknowledge_count: 0,
      pending_count: 0,
      tracked_count: 0, startup: { in_progress: false, stabilization_until: null },
      alerts: [],
      pending: [],
      acknowledge: [],
    };
    this._history = { events: [], count: 0, retention_limit: 100, enabled: true };
    this._historyConfig = { retention_limit: 100, enabled: true };
    this._historyLoaded = false;
    this._configRecovery = { active: false, backups: [] };
    this._notificationStats = { last_24h: {} }; this._notificationStatsLoadPromise = null;
    this._backupRestoreCandidate = null;
    this._coherence = null;
    this._coherenceLoaded = false;
    this._coherenceLoading = false;
    this._coherenceLoadPromise = null;
    this._coherenceScannedAt = null;
    this._deletedEntitiesState = { data: null, loading: false, error: null };
    this._alertsRefreshPromise = null;
    this._alertsRefreshRequested = false;
    this._activeTab = "overview";
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleEditorError = null;
    this._ruleTestResult = null;
    this._ruleTestLoading = false;
    this._ruleTestSequence = 0;
    this._ruleDirty = false; this._automaticDirty = false;
    this._loading = true;
    this._cachedStateNeedsRefresh = false;
    this._busy = false;
    this._notice = null;
    this._monitoringEnabled = true;
    this._timer = null;
    this._entityStates = {};
    this._labels = [];
    this._tableState = this._loadTablePreferences();
    this._collapsedTableGroups = new Set();
    this._filterPaneKind = "";
    this._selectionMode = false;
    this._selectedAlertIds = new Set();
    this._selectedHistoryIds = new Set();
    this._historySelectionMode = false;
    resetSettingsDraft.call(this);
    this._automaticMapDraft = null;
    this._configurationDrawer = null;
    this._ruleEditorWidth = 560;
    this._ruleEditorResize = null;
    this._moreInfoScrollRestore = null;
    this._alertDetailsDialog = null;
    this._handledAlertDeepLink = null;
    this._nativeBottomSheetLoadPromise = null;
    this._configuredControls = new WeakSet();
    this.shadowRoot.addEventListener("click", (event) => this._handleClick(event));
    this.shadowRoot.addEventListener("keydown", (event) => this._handleKeydown(event));
    this.shadowRoot.addEventListener("pointerdown", (event) => this._startRuleEditorResize(event));
    this.shadowRoot.addEventListener("dblclick", (event) => this._resetRuleEditorWidth(event));
    this.shadowRoot.addEventListener("submit", (event) => this._handleSubmit(event));
    this.shadowRoot.addEventListener("input", (event) => this._handleInput(event));
    this.shadowRoot.addEventListener("change", (event) => this._handleChange(event));
    this.shadowRoot.addEventListener("bottom-sheet-closed", (event) => void handleBottomSheetClosed(this, ACTION_HANDLERS, event));
    this.shadowRoot.addEventListener("wa-select", (event) => {
      void this._handleMenuSelected(event);
    });
    this._ruleEditorResizeMove = (event) => this._resizeRuleEditor(event);
    this._ruleEditorResizeEnd = () => this._stopRuleEditorResize();
  }
  set hass(value) {
    setHass.call(this, value);
  }
  get hass() {
    return this._hass;
  }
  async _handleMenuSelected(event) {
    if (await this._handleAlertDetailsSelection(event)) return;
    await this._handleSelected(event);
  }
  set panel(value) {
    this._panel = value;
  }
  set route(value) {
    this._route = value;
    const activeTab = this._tabFromRoute(value);
    if (activeTab !== this._activeTab) {
      this._activeTab = activeTab;
      this._configurationDrawer = null;
      this._notice = null;
      if (this.isConnected) this._render();
      this._refreshTabData(activeTab);
    } else if (this.isConnected) {
      this._hydrateSelectors();
    }
  }

  set narrow(value) {
    const previousNarrow = this._narrow;
    this._narrow = Boolean(value);
    this.toggleAttribute?.("narrow", this._narrow);
    for (const selector of [
      "[data-alert-table-page]",
      "[data-coherence-table-page]",
      "[data-rules-table-page]",
    ]) {
      const tablePage = this.shadowRoot?.querySelector(selector);
      if (tablePage) tablePage.narrow = this._narrow;
    }
    this._updateDrawerLayout(previousNarrow);
  }
  _upgradeProperty(name) {
    if (!Object.prototype.hasOwnProperty.call(this, name)) return;
    const value = this[name];
    delete this[name];
    this[name] = value;
  }

  connectedCallback() {
    // On a direct page load Home Assistant can set panel properties before this
    // custom element is defined. Replay those values through their setters once
    // the element is upgraded, otherwise the own properties shadow the setters
    // and the initial WebSocket load never starts.
    for (const property of ["panel", "route", "narrow", "hass"]) {
      this._upgradeProperty(property);
    }
    this.toggleAttribute?.("companion-app", isCompanionApp());
    if (this._narrow) void this._loadNativeBottomSheet();
    this._render();
    if (
      this._hass
      && (!this._config || this._cachedStateNeedsRefresh)
      && !this._loadPromise
    ) this._load();
    this._refreshTabData(this._activeTab);
    if (!this._timer) {
      this._timer = window.setInterval(() => this._updateCountdowns(), 1000);
    }
  }

  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
    this._stopRuleEditorResize();
    this._cancelMoreInfoScrollRestore();
    this._closeAlertDetailsDialog();
  }
  _tabs() {
    return TABS.map(({ path, translationKey, iconPath }) => ({
      path,
      name: this._t(translationKey),
      iconPath,
    }));
  }

  _syncSensor = syncSensor;
  _render() {
    if (!this.shadowRoot) return;
    this._closeAlertDetailsDialog();
    const currentTablePage = this.shadowRoot.querySelector?.("[data-alert-table-page]");
    if (currentTablePage) {
      const kind = currentTablePage.dataset.alertTablePage;
      this._filterPaneKind = currentTablePage.showFilters ? kind : "";
      if (kind === "overview") this._selectionMode = Boolean(currentTablePage._selectMode);
      if (kind === "history") this._historySelectionMode = Boolean(currentTablePage._selectMode);
    }
    const content = this._loading
      ? `<div class="loading">${esc(this._t("loading"))}</div>`
      : this._renderTab();
    const nativeTablePage = !this._loading && this._config
      && (this._activeTab === "overview"
        || this._activeTab === "rules"
        || (this._activeTab === "coherence" && this._coherence)
        || (this._activeTab === "history" && Number(this._historyConfig?.retention_limit ?? 100) !== 0));
    const page = nativeTablePage ? content : `<main>${this._renderPageMessages()}${content}</main>`;
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      ${this._hass && !nativeTablePage ? `<hass-tabs-subpage id="panel-shell" main-page>${page}</hass-tabs-subpage>` : page}
      ${this._renderBackupRestoreDialog()}`;
    this._hydrateSelectors();
    this._hydrateDataTables();
    this._hydrateRuleTable();
    this._hydrateCoherenceTable();
    this._hydrateYamlEditor();
    this._hydrateConfigBackups();
    this._updateCountdowns();
    this._decorateActionIcons();
    this._syncNarrowTableHeaderBackgrounds();
  }

  _renderPageMessages() {
    return `<div class="page-messages" data-page-messages>${this._pageMessagesContent()}</div>`;
  }
  _pageMessagesContent() {
    return `${!this._monitoringEnabled && !this._configRecovery?.active ? `<ha-alert class="page-alert" alert-type="warning"><span>${esc(this._t("monitoring.disabled"))}</span><ha-button slot="action" size="s" appearance="accent" variant="brand" data-action="enable-monitoring" ${this._busy ? "disabled" : ""}>${esc(this._t("monitoring.enable"))}</ha-button></ha-alert>` : ""}
      ${this._notice ? `<ha-alert class="page-alert" alert-type="${esc(this._notice.kind)}">${esc(this._notice.text)}</ha-alert>` : ""}`;
  }

  _refreshUiState() {
    const messages = this.shadowRoot?.querySelector?.("[data-page-messages]");
    if (messages) messages.innerHTML = this._pageMessagesContent();
    const busyActions = new Set([
      "enable-monitoring",
      "clear-history",
      "delete-history",
      "bulk-acknowledge",
      "bulk-unacknowledge",
      "save-automatic",
      "save-rule",
      "save-settings", "save-configuration",
      "export-config",
      "choose-config-import",
      "download-config-backup",
      "restore-config-backup",
      "confirm-config-backup-restore",
    ]);
    for (const button of this.shadowRoot?.querySelectorAll?.("[data-action]") ?? []) {
      if (busyActions.has(button.dataset.action)) button.disabled = this._busy;
    }
    this._updateConfigurationSaveButton();
    this._decorateActionIcons();
  }

  _decorateActionIcons() {
    if (!globalThis.document?.createElement) return;
    for (const [action, iconName] of Object.entries(ACTION_ICONS)) {
      for (const button of this.shadowRoot?.querySelectorAll?.(`[data-action="${action}"]`) ?? []) {
        if (button.querySelector?.("[data-alert-manager-action-icon]")) continue;
        const icon = document.createElement("ha-icon");
        icon.setAttribute("slot", "start");
        icon.setAttribute("icon", iconName);
        icon.setAttribute("data-alert-manager-action-icon", "");
        button.prepend(icon);
      }
    }
  }

  _configureSelector(id, selector, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element) return;
    if (this._configuredControls.has(element)) return;
    element.hass = this._hass;
    element.selector = selector;
    element.value = value;
    element.addEventListener("value-changed", (event) => {
      const eventValue = event.detail && Object.hasOwn(event.detail, "value")
        ? event.detail.value
        : element.value;
      if (eventValue !== undefined) {
        // Home Assistant selectors are controlled components: their host
        // value is not updated automatically when the inner selector emits
        // value-changed. Mirror the value so later reads are never stale.
        element.value = eventValue;
        if (id.startsWith("rule-")) this._clearRuleEditorError();
        if (id.startsWith("rule-")) this._clearRuleTestResult();
        onChange(eventValue);
        this._markConfigurationControlDirty(element);
        if (id === "rule-entity-ids") this._refreshRuleAttributeSelector();
      }
    });
    this._configuredControls.add(element);
  }

  _multipleSelectorValue(value, current = []) {
    if (value === undefined) return [...current];
    const values = Array.isArray(value)
      ? value
      : value instanceof Set
        ? [...value]
        : typeof value === "string"
          ? (value ? [value] : [])
          : [];
    return [...new Set(values.filter((item) => typeof item === "string" && item))];
  }

  _configureSelect(id, options, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element || this._configuredControls.has(element)) return;
    element.options = options;
    element.value = value;
    element.addEventListener("selected", (event) => {
      element.value = event.detail?.value;
      if (id.startsWith("rule-")) this._clearRuleEditorError();
      if (id.startsWith("rule-")) this._clearRuleTestResult();
      onChange?.(event.detail?.value);
      this._markConfigurationControlDirty(element);
      if (id === "rule-source") this._refreshRuleAttributeSelector();
    });
    this._configuredControls.add(element);
  }

  _updateHassReferences() {
    this.shadowRoot?.querySelectorAll("ha-selector, #panel-shell, [data-alert-table-page], [data-rules-table-page], [data-coherence-table-page], ha-code-editor").forEach((element) => {
      element.hass = this._hass;
    });
  }

  _hydrateSelectors() {
    hydrateDurationFields(this.shadowRoot, this);
    this.shadowRoot.querySelectorAll("ha-icon-button[aria-label]").forEach((button) => {
      button.label = button.getAttribute("aria-label");
    });
    const shell = this.shadowRoot.querySelector("#panel-shell");
    if (shell && this._hass) {
      const activePage = TABS.find((tab) => tab.id === this._activeTab) ?? TABS[0];
      shell.hass = this._hass;
      shell.tabs = this._tabs();
      shell.route = { prefix: "", path: activePage.path };
      shell.mainPage = true;
      shell.backPath = undefined;
      shell.backCallback = undefined;
    }
    if (!this._hass || !this._config) return;
    if (this._editingRule !== null) {
      this._hydrateRuleEditorControls();
      if (this._ruleEditorMode !== "visual") return;
    }
    if (this._activeTab === "settings") {
      this._hydrateAutomaticControls();
      this._hydrateSettingsControls();
    }
  }

  _hydrateYamlEditor() {
    if (this._editingRule === null || this._ruleEditorMode !== "yaml") return;
    const editor = this.shadowRoot.querySelector("#rule-yaml-editor");
    if (!editor) return;
    editor.mode = "yaml";
    editor.value = this._ruleYaml;
    editor.lineNumbers = true;
    if (editor.dataset.configured) return;
    editor.addEventListener("value-changed", (event) => {
      this._ruleYaml = String(event.detail?.value ?? editor.value ?? "");
      this._ruleYamlError = null;
      this._ruleDirty = true;
    });
    editor.dataset.configured = "true";
  }

  _renderTab() {
    if (!this._config) return `<div class="empty">${esc(this._t("unavailable"))}</div>`;
    if (this._activeTab === "history" && !this._historyLoaded) {
      return `<div class="loading">${esc(this._t("loading"))}</div>`;
    }
    if (this._activeTab === "coherence" && !this._coherenceLoaded) {
      return `<div class="loading">${esc(this._t("loading"))}</div>`;
    }
    if (this._activeTab === "coherence") return this._renderCoherence();
    if (this._activeTab === "history") return this._renderHistory();
    if (this._activeTab === "rules") return this._renderRules();
    if (this._activeTab === "settings") return this._renderSettings();
    return this._renderOverview();
  }

  _tabFromRoute(route) {
    const path = `${route?.prefix ?? ""}${route?.path ?? ""}`.replace(/\/$/, "");
    if (path.endsWith("/automatic")) return "settings";
    return TABS.find((tab) => path.endsWith(`/${tab.id}`))?.id ?? "overview";
  }

  _numberField(id, label, value, suffix, min, max, options = {}) {
    if (suffix === "s" || suffix === this._t("units.seconds")) {
      return renderDurationField(id, label, value, min, max, options);
    }
    const {
      step = "1",
      nameMode = "id",
      required = true,
      help = "",
    } = options;
    const field = nameMode === "name" ? ` data-field="${esc(id)}"` : "";
    return `<div class="field"><span class="field-label">${esc(label)}</span><ha-input ${field} id="${esc(id)}" type="number" min="${min}" max="${max}" step="${step}" value="${esc(value ?? "")}" ${required ? "required" : ""} aria-label="${esc(label)}"><span slot="end">${esc(suffix)}</span></ha-input>${help ? `<small>${esc(help)}</small>` : ""}</div>`;
  }

  _textField(name, label, value, required = false, mode = "name", className = "") {
    const key = mode === "id" ? `id="${esc(name)}"` : `name="${esc(name)}"`;
    const field = mode === "name" ? `data-field="${esc(name)}"` : "";
    return `<div class="field${className ? ` ${esc(className)}` : ""}"><span class="field-label">${esc(label)}</span><ha-input ${key} ${field} type="text" value="${esc(value)}" ${required ? "required" : ""} aria-label="${esc(label)}"></ha-input></div>`;
  }

  async _handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (this._narrow && SIDE_DRAWER_OPEN_ACTIONS.has(action)) {
      await this._loadNativeBottomSheet();
    }
    if (action === "tab") {
      this._activeTab = button.dataset.tab;
      this._configurationDrawer = null;
      this._notice = null;
      this._render();
      this._refreshTabData(this._activeTab);
      return;
    }
    for (const handler of ACTION_HANDLERS) {
      if (await handler.call(this, action, button, event)) return;
    }
  }
  _handleInput(event) {
    if (event.target?.id === "ignored-reference-input") {
      this._ignoredReferenceDraft = String(event.target.value ?? "");
    }
    handleSettingsInput.call(this, event);
    this._markConfigurationControlDirty(event.target);
    this._handleRuleInput(event);
  }

  _handleChange(event) {
    handleSettingsInput.call(this, event);
    this._markConfigurationControlDirty(event.target);
    this._handleRuleInput(event);
    if (event.target?.id === "coherence-scan-esphome") {
      this._ensureSettingsDraft();
      this._settingsDraft.coherence_scan_esphome = Boolean(event.target.checked);
    }
    if (event.target?.id === "rule-update-message-when-active" && this._editingRule) {
      this._editingRule.update_message_when_active = Boolean(event.target.checked);
      this._ruleDirty = true;
    }
    void this._handleImportSelection(event);
  }

  _handleKeydown(event) {
    if (event.target?.id === "ignored-reference-input" && ["Enter", ","].includes(event.key)) {
      event.preventDefault();
      if (this._commitIgnoredReferenceInput()) {
        this._notice = null;
      }
      this._render();
      return;
    }
    if (event.target.closest?.(".rule-editor-resize") && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      this._setRuleEditorWidth(this._ruleEditorWidth + (event.key === "ArrowLeft" ? 16 : -16));
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    const timestamp = event.target.closest?.('[data-action="toggle-alert-timestamp"]'); if (timestamp) { event.preventDefault(); void this._handleClick({ target: timestamp }); return; }
    const summary = event.target.closest?.('.summary [data-action="filter-summary-status"]');
    if (summary) {
      event.preventDefault();
      void this._handleClick({ target: summary });
    }
  }
  async _handleSubmit(event) {
    event.preventDefault();
    if (this._busy) return;
    // The save call rerenders the panel. Keep the form reference before the
    // first await because the browser may clear Event.target afterwards.
    const form = event.target;
    const formId = form?.id;
    if (formId === "automatic-form") {
      if (this._reportFormValidity(form)) await this._saveAutomatic();
      return;
    }
    if (formId === "settings-form") {
      if (this._reportFormValidity(form)) await this._saveSettings();
      return;
    }
    if (formId === "rule-form") {
      if (this._ruleEditorMode === "yaml") await this._saveRuleYaml();
      else if (this._reportFormValidity(form)) await this._saveRule(form);
    }
  }
  _reportFormValidity(form) {
    let valid = form.reportValidity?.() ?? true;
    form.querySelectorAll?.("ha-input").forEach((field) => {
      if (typeof field.reportValidity === "function") {
        valid = field.reportValidity() && valid;
      } else if (field.required && String(field.value ?? "") === "") {
        valid = false;
      }
    });
    if (!validateDurationFields(form, this)) {
      this._notice = { kind: "error", text: this._t("errors.duration_field_range") };
      this._refreshUiState();
      valid = false;
    }
    return valid;
  }
  _styles() {
    return panelStyles();
  }
}
if (!customElements.get("alert-manager-panel")) {
  customElements.define("alert-manager-panel", AlertManagerPanel);
}
export { AlertManagerPanel, makeTableState, lines, newRuleDefaults };
