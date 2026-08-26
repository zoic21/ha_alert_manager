const TABS = [
  {
    id: "overview",
    path: "/alert-manager/overview",
    translationKey: "tabs.overview",
    iconPath: "M19,5V7H15V5H19M9,5V11H5V5H9M19,13V19H15V13H19M9,17V19H5V17H9M21,3H13V9H21V3M11,3H3V13H11V3M21,11H13V21H21V11M11,15H3V21H11V15Z",
  },
  {
    id: "history",
    path: "/alert-manager/history",
    translationKey: "tabs.history",
    iconPath: "M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3C8.03,3 4,7.03 4,12H1L4.89,15.89L5,16L9,12H6C6,8.13 9.13,5 13,5C16.87,5 20,8.13 20,12C20,15.87 16.87,19 13,19C11.07,19 9.32,18.22 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21C17.97,21 22,16.97 22,12C22,7.03 17.97,3 13,3Z",
  },
  {
    id: "automatic",
    path: "/alert-manager/automatic",
    translationKey: "tabs.automatic",
    iconPath: "M19.07,4.93L17.66,6.34C19.1,7.79 20,9.79 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12C4,7.92 7.05,4.56 11,4.07V6.09C8.16,6.57 6,9.03 6,12A6,6 0 0,0 12,18A6,6 0 0,0 18,12C18,10.34 17.33,8.84 16.24,7.76L14.83,9.17C15.55,9.9 16,10.9 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12C8,10.14 9.28,8.59 11,8.14V10.28C10.4,10.63 10,11.26 10,12A2,2 0 0,0 12,14A2,2 0 0,0 14,12C14,11.26 13.6,10.62 13,10.28V2H12A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12C22,9.24 20.88,6.74 19.07,4.93Z",
  },
  {
    id: "rules",
    path: "/alert-manager/rules",
    translationKey: "tabs.rules",
    iconPath: "M3,5H9V11H3V5M5,7V9H7V7H5M11,7H21V9H11V7M11,15H21V17H11V15M5,20L1.5,16.5L2.91,15.09L5,17.17L9.59,12.59L11,14L5,20Z",
  },
  {
    id: "settings",
    path: "/alert-manager/settings",
    translationKey: "tabs.settings",
    iconPath: "M8 13C6.14 13 4.59 14.28 4.14 16H2V18H4.14C4.59 19.72 6.14 21 8 21S11.41 19.72 11.86 18H22V16H11.86C11.41 14.28 9.86 13 8 13M8 19C6.9 19 6 18.1 6 17C6 15.9 6.9 15 8 15S10 15.9 10 17C10 18.1 9.1 19 8 19M19.86 6C19.41 4.28 17.86 3 16 3S12.59 4.28 12.14 6H2V8H12.14C12.59 9.72 14.14 11 16 11S19.41 9.72 19.86 8H22V6H19.86M16 9C14.9 9 14 8.1 14 7C14 5.9 14.9 5 16 5S18 5.9 18 7C18 8.1 17.1 9 16 9Z",
  },
];

const MDI_CLOSE = "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z";
const MDI_PLUS = "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z";
const MDI_ALERT_CIRCLE_OUTLINE = "M13,14H11V10H13M13,18H11V16H13M12,2C6.48,2 2,6.48 2,12C2,17.52 6.48,22 12,22C17.52,22 22,17.52 22,12C22,6.48 17.52,2 12,2M12,20C7.58,20 4,16.42 4,12C4,7.58 7.58,4 12,4C16.42,4 20,7.58 20,12C20,16.42 16.42,20 12,20Z";
const MDI_CLOCK_OUTLINE = "M12,20C7.58,20 4,16.42 4,12C4,7.58 7.58,4 12,4C16.42,4 20,7.58 20,12C20,16.42 16.42,20 12,20M12,2C6.48,2 2,6.48 2,12C2,17.52 6.48,22 12,22C17.52,22 22,17.52 22,12C22,6.48 17.52,2 12,2M12.5,7H11V13L16.25,16.15L17,14.92L12.5,12.25V7Z";
const MDI_CHECK_CIRCLE_OUTLINE = "M12,2C6.48,2 2,6.48 2,12C2,17.52 6.48,22 12,22C17.52,22 22,17.52 22,12C22,6.48 17.52,2 12,2M10,17L5,12L6.41,10.59L10,14.17L17.59,6.58L19,8L10,17Z";
const MDI_DOTS_VERTICAL = "M12,8C13.1,8 14,7.1 14,6C14,4.9 13.1,4 12,4C10.9,4 10,4.9 10,6C10,7.1 10.9,8 12,8M12,10C10.9,10 10,10.9 10,12C10,13.1 10.9,14 12,14C13.1,14 14,13.1 14,12C14,10.9 13.1,10 12,10M12,16C10.9,16 10,16.9 10,18C10,19.1 10.9,20 12,20C13.1,20 14,19.1 14,18C14,16.9 13.1,16 12,16Z";
const MDI_DOWNLOAD = "M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z";
const MDI_UPLOAD = "M5,17H19V19H5M12,3L5,10H9V14H15V10H19L12,3Z";
const MDI_FILTER_VARIANT = "M14,12V19.88C14.04,20.18 13.94,20.5 13.71,20.71C13.32,21.1 12.69,21.1 12.3,20.71L10.29,18.7C10.06,18.47 9.96,18.16 10,17.87V12H9.97L4.21,4.62C3.87,4.19 3.95,3.56 4.38,3.22C4.56,3.08 4.78,3 5,3V3H19V3C19.22,3 19.44,3.08 19.62,3.22C20.05,3.56 20.13,4.19 19.79,4.62L14.03,12H14Z";
const MDI_GROUP = "M12,5A3,3 0 1,0 12,11A3,3 0 0,0 12,5M6,7A2,2 0 1,0 6,11A2,2 0 0,0 6,7M18,7A2,2 0 1,0 18,11A2,2 0 0,0 18,7M12,13C9.33,13 4,14.33 4,17V19H20V17C20,14.33 14.67,13 12,13M6,13C3.33,13 0,14.33 0,17V19H2V17C2,15.83 3.04,14.86 4.37,14.17C4.88,13.73 5.47,13.34 6.1,13.04L6,13M18,13L17.9,13.04C18.53,13.34 19.12,13.73 19.63,14.17C20.96,14.86 22,15.83 22,17V19H24V17C24,14.33 20.67,13 18,13Z";
const MDI_SORT = "M3,18H9V16H3V18M3,13H15V11H3V13M3,6V8H21V6H3Z";
const MDI_TABLE_COLUMN = "M4,3H20A2,2 0 0,1 22,5V19A2,2 0 0,1 20,21H4A2,2 0 0,1 2,19V5A2,2 0 0,1 4,3M4,5V19H8V5H4M10,5V19H14V5H10M16,5V19H20V5H16Z";
const MDI_CHECKBOX_MULTIPLE = "M17,3H5A2,2 0 0,0 3,5V17H5V5H17V3M19,7H9A2,2 0 0,0 7,9V19A2,2 0 0,0 9,21H19A2,2 0 0,0 21,19V9A2,2 0 0,0 19,7M17,17H11V11H17V17Z";
const MDI_ARROW_UP = "M4,12L5.41,13.41L11,7.83V20H13V7.83L18.59,13.42L20,12L12,4L4,12Z";
const MDI_ARROW_DOWN = "M20,12L18.59,10.59L13,16.17V4H11V16.17L5.41,10.58L4,12L12,20L20,12Z";
const TEXT_RULE_OPERATORS = new Set(["equals", "not_equals", "contains", "not_contains"]);
const ALERT_MANAGER_ENTITY_IDS = [
  "sensor.alert_manager_main_active",
  "sensor.alert_manager_main_pending",
  "sensor.alert_manager_main_acknowledge",
  "switch.alert_manager_main_monitoring",
];

const esc = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const lines = (value) =>
  String(value ?? "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const newRuleDefaults = () => ({
  name: "",
  entity_ids: [],
  enabled: true,
  source: "state",
  attribute: "",
  operator: "equals",
  value: [""],
  duration: 900,
  message: "",
});

const yamlValue = (value) => {
  if (value === null || value === undefined || value === "") return "null";
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  return JSON.stringify(String(value));
};

const ruleToYaml = (rule) => {
  const lines = [
    `name: ${yamlValue(rule.name)}`,
    `enabled: ${yamlValue(rule.enabled ?? true)}`,
    "entity_ids:",
    ...(rule.entity_ids ?? []).map((entityId) => `  - ${yamlValue(entityId)}`),
    `source: ${yamlValue(rule.source ?? "state")}`,
  ];
  if ((rule.source ?? "state") === "attribute") lines.push(`attribute: ${yamlValue(rule.attribute)}`);
  lines.push(
    `operator: ${yamlValue(rule.operator)}`,
    Array.isArray(rule.value)
      ? "value:\n" + rule.value.map((value) => `  - ${yamlValue(value)}`).join("\n")
      : `value: ${yamlValue(rule.value)}`,
    `duration: ${yamlValue(rule.duration)}`,
    `message: ${yamlValue(rule.message)}`,
  );
  return `${lines.join("\n")}\n`;
};

const TABLE_PREFERENCES_KEY = "alert-manager-table-preferences-v1";
const REQUIRED_COLUMNS = new Set(["status", "entity"]);
const DEFAULT_TABLE_STATE = Object.freeze({
  overview: Object.freeze({
    columns: Object.freeze(["status", "device", "entity", "value", "condition", "detected", "timeline"]),
    groupBy: "none",
    sortBy: "detected",
    sortDirection: "desc",
  }),
  history: Object.freeze({
    columns: Object.freeze(["status", "device", "entity", "value", "condition", "detected", "resolved"]),
    groupBy: "none",
    sortBy: "detected",
    sortDirection: "desc",
  }),
});

const makeTableState = (kind, preferences = {}) => {
  const defaults = DEFAULT_TABLE_STATE[kind];
  const sortOptions = kind === "history"
    ? ["status", "device", "entityName", "rule", "value", "detected", "resolved"]
    : ["status", "device", "entityName", "rule", "value", "detected", "activated", "remaining"];
  const savedColumns = Array.isArray(preferences.columns)
    ? preferences.columns.filter((column, index, columns) => (
      typeof column === "string" && columns.indexOf(column) === index
    ))
    : [];
  const columns = savedColumns.length ? [...savedColumns] : [...defaults.columns];
  for (const required of REQUIRED_COLUMNS) {
    if (!columns.includes(required)) columns.push(required);
  }
  return {
    search: "",
    filters: {
      status: "",
      device: "",
      area: "",
      rule: "",
      entity: "",
      acknowledged: "",
      detectedFrom: "",
      detectedTo: "",
      resolvedFrom: "",
      resolvedTo: "",
    },
    columns,
    groupBy: ["none", "device", "area", "rule", "status"].includes(preferences.groupBy)
      ? preferences.groupBy
      : defaults.groupBy,
    sortBy: sortOptions.includes(preferences.sortBy) ? preferences.sortBy : defaults.sortBy,
    sortDirection: preferences.sortDirection === "asc" ? "asc" : "desc",
  };
};

class AlertManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
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
      tracked_count: 0,
      alerts: [],
      pending: [],
      acknowledge: [],
    };
    this._history = { events: [], count: 0, retention_limit: 100, enabled: true };
    this._historyConfig = { retention_limit: 100, enabled: true };
    this._historyLoadPromise = null;
    this._activeTab = "overview";
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleMenuOpen = false;
    this._ruleDirty = false;
    this._loading = true;
    this._busy = false;
    this._notice = null;
    this._monitoringEnabled = true;
    this._timer = null;
    this._entityStates = {};
    this._tableState = this._loadTablePreferences();
    this._collapsedTableGroups = new Set();
    this._nativeGroupLabels = { overview: new Map(), history: new Map() };
    this._selectionMode = false;
    this._selectedAlertIds = new Set();
    this._settingsDraft = null;
    this._entityDelayDraft = null;
    this._ruleEditorWidth = 560;
    this._ruleEditorResize = null;
    this._configuredControls = new WeakSet();
    this.shadowRoot.addEventListener("click", (event) => this._handleClick(event));
    this.shadowRoot.addEventListener("keydown", (event) => this._handleKeydown(event));
    this.shadowRoot.addEventListener("pointerdown", (event) => this._startRuleEditorResize(event));
    this.shadowRoot.addEventListener("dblclick", (event) => this._resetRuleEditorWidth(event));
    this.shadowRoot.addEventListener("submit", (event) => this._handleSubmit(event));
    this.shadowRoot.addEventListener("input", (event) => this._handleInput(event));
    this.shadowRoot.addEventListener("change", (event) => this._handleChange(event));
    this._ruleEditorResizeMove = (event) => this._resizeRuleEditor(event);
    this._ruleEditorResizeEnd = () => this._stopRuleEditorResize();
  }

  _loadTablePreferences() {
    let saved = {};
    try {
      saved = JSON.parse(window.localStorage?.getItem(TABLE_PREFERENCES_KEY) ?? "{}");
    } catch (_error) {
      saved = {};
    }
    return {
      overview: makeTableState("overview", saved?.overview),
      history: makeTableState("history", saved?.history),
    };
  }

  _saveTablePreferences() {
    const preferences = Object.fromEntries(["overview", "history"].map((kind) => {
      const state = this._tableState[kind];
      return [kind, {
        columns: [...state.columns],
        groupBy: state.groupBy,
        sortBy: state.sortBy,
        sortDirection: state.sortDirection,
      }];
    }));
    try {
      window.localStorage?.setItem(TABLE_PREFERENCES_KEY, JSON.stringify(preferences));
    } catch (_error) {
      // Private browsing or a full storage quota must not make the panel unusable.
    }
  }

  set hass(value) {
    const language = value?.locale?.language || "en";
    const languageChanged = language !== this._language;
    this._hass = value;
    this._language = language;
    const alertsChanged = this._syncSensor();
    if (this.isConnected && !this._config && !this._loadPromise) {
      this._load();
    } else if (this.isConnected && languageChanged && !this._translationPromise) {
      this._reloadTranslations();
    } else if (this.isConnected && this._activeTab === "overview" && alertsChanged) {
      this._render();
    } else if (this.isConnected && this._activeTab === "history" && alertsChanged) {
      this._refreshHistory();
    } else if (this.isConnected) {
      this._hydrateSelectors();
    }
  }

  get hass() {
    return this._hass;
  }

  set panel(value) {
    this._panel = value;
  }

  set route(value) {
    this._route = value;
    const activeTab = this._tabFromRoute(value);
    if (activeTab !== this._activeTab) {
      this._activeTab = activeTab;
      this._editingRule = null;
      this._notice = null;
      if (activeTab === "history") this._refreshHistory();
      if (this.isConnected) this._render();
    } else if (this.isConnected) {
      this._hydrateSelectors();
    }
  }

  set narrow(value) {
    this._narrow = value;
  }

  connectedCallback() {
    this._render();
    if (this._hass && !this._config && !this._loadPromise) this._load();
    if (!this._timer) {
      this._timer = window.setInterval(() => this._updateCountdowns(), 1000);
    }
  }

  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
    this._stopRuleEditorResize();
  }

  async _load() {
    this._loadPromise = Promise.all([
      this._hass.callWS({ type: "alert_manager/config/get" }),
      this._hass.callWS({ type: "alert_manager/alerts/list" }),
      this._hass.callWS({ type: "alert_manager/packs/list" }),
      this._hass.callWS({ type: "alert_manager/history/list" }),
      this._hass.callWS({ type: "alert_manager/history/config/get" }),
      this._fetchTranslations(this._language),
    ]);
    this._loading = true;
    this._render();
    try {
      [
        this._config,
        this._alerts,
        this._packs,
        this._history,
        this._historyConfig,
      ] = await this._loadPromise;
      this._monitoringEnabled = this._config.monitoring_enabled !== false;
      this._resetSettingsDraft();
      this._syncSensor();
      this._notice = null;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._loading = false;
      this._loadPromise = null;
      this._render();
    }
  }

  async _refreshHistory() {
    if (!this._hass || this._historyLoadPromise) return this._historyLoadPromise;
    this._historyLoadPromise = this._hass.callWS({ type: "alert_manager/history/list" });
    try {
      this._history = await this._historyLoadPromise;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._historyLoadPromise = null;
      if (this.isConnected) this._render();
    }
    return this._history;
  }

  async _fetchTranslations(language) {
    const request = (requestedLanguage) => this._hass.callWS({
      type: "frontend/get_translations",
      language: requestedLanguage,
      category: "config_panel",
      integration: "alert_manager",
    });
    const [localized, english] = await Promise.all([
      request(language),
      language === "en" ? Promise.resolve(null) : request("en"),
    ]);
    if (language !== this._language) return;
    this._translations = localized?.resources ?? {};
    this._englishTranslations = english?.resources ?? this._translations;
  }

  async _reloadTranslations() {
    this._loading = true;
    this._render();
    const language = this._language;
    this._translationPromise = this._fetchTranslations(language);
    try {
      await this._translationPromise;
      this._notice = null;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._translationPromise = null;
      this._loading = false;
      this._render();
    }
  }

  _t(key, params = {}) {
    const resourceKey = `component.alert_manager.config_panel.${key}`;
    const template = this._translations[resourceKey]
      ?? this._englishTranslations[resourceKey]
      ?? resourceKey;
    return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => (
      Object.hasOwn(params, name) ? String(params[name] ?? "") : match
    ));
  }

  _tabs() {
    return TABS.map(({ path, translationKey, iconPath }) => ({
      path,
      name: this._t(translationKey),
      iconPath,
    }));
  }

  _syncSensor() {
    const states = this._hass?.states ?? {};
    const entityIds = [
      "sensor.alert_manager_main_active",
      "sensor.alert_manager_main_pending",
      "sensor.alert_manager_main_acknowledge",
      "switch.alert_manager_main_monitoring",
    ];
    if (entityIds.every((entityId) => states[entityId] === this._entityStates[entityId])) {
      return false;
    }
    this._entityStates = Object.fromEntries(
      entityIds.map((entityId) => [entityId, states[entityId]]),
    );
    const monitoringState = states["switch.alert_manager_main_monitoring"]?.state;
    if (monitoringState === "on" || monitoringState === "off") {
      this._monitoringEnabled = monitoringState === "on";
    }
    // The three public sensors intentionally expose zero while monitoring is
    // disabled. Keep the panel's last/WebSocket snapshot so pending rows can
    // show their suspended delay instead of disappearing from the interface.
    if (this._monitoringEnabled) {
      const partitions = [
        ["sensor.alert_manager_main_active", "active_count", "alerts"],
        ["sensor.alert_manager_main_pending", "pending_count", "pending"],
        ["sensor.alert_manager_main_acknowledge", "acknowledge_count", "acknowledge"],
      ];
      for (const [entityId, countKey, alertsKey] of partitions) {
        const state = states[entityId];
        const alerts = state?.attributes?.alerts;
        if (!state || !Array.isArray(alerts)) continue;
        this._alerts[countKey] = Number(state.state ?? alerts.length ?? 0);
        this._alerts[alertsKey] = alerts;
      }
    }
    return true;
  }

  async _call(message, successText) {
    this._busy = true;
    this._notice = null;
    this._render();
    try {
      const result = await this._hass.callWS(message);
      this._notice = successText ? { kind: "success", text: successText } : null;
      return result;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
      return null;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _errorText(error) {
    const code = error?.code ?? error?.body?.code;
    const message = error?.message ?? error?.body?.message;
    if (code === "invalid_format" && typeof message === "string" && message) return message;
    return this._t(`errors.${["invalid_format", "not_loaded"].includes(code) ? code : "unknown"}`);
  }

  _render() {
    if (!this.shadowRoot) return;
    const content = this._loading
      ? `<div class="loading">${esc(this._t("loading"))}</div>`
      : this._renderTab();
    const page = `<main>
      ${!this._monitoringEnabled ? `<div class="monitoring-warning" role="alert"><span>${esc(this._t("monitoring.disabled"))}</span><ha-button appearance="accent" variant="brand" data-action="enable-monitoring" ${this._busy ? "disabled" : ""}>${esc(this._t("monitoring.enable"))}</ha-button></div>` : ""}
      ${this._notice ? `<div class="notice ${this._notice.kind}">${esc(this._notice.text)}</div>` : ""}
      ${content}
    </main>`;
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      ${this._hass ? `<hass-tabs-subpage id="panel-shell" back-path="/config/integrations">${page}</hass-tabs-subpage>` : page}`;
    this._hydrateSelectors();
    this._hydrateDataTables();
    this._hydrateYamlEditor();
    this._updateCountdowns();
  }

  _hydrateDataTables() {
    for (const kind of ["overview", "history"]) {
      const table = this.shadowRoot.querySelector(`[data-native-alert-table="${kind}"]`);
      if (!table) continue;
      const sourceRows = kind === "overview"
        ? this._tableRows("overview")
        : this._tableRows("history", this._history?.events ?? []);
      const visibleRows = this._filteredTableRows(kind, sourceRows);
      const allowedColumns = Object.keys(this._tableColumns(kind));
      const hiddenColumns = allowedColumns.filter((column) => !this._tableState[kind].columns.includes(column));
      const orderedColumns = [...this._tableState[kind].columns, ...hiddenColumns];
      const data = this._nativeTableData(kind, visibleRows);
      table.id = "id";
      table.columns = this._nativeTableColumns(kind);
      table.columnOrder = orderedColumns;
      table.hiddenColumns = hiddenColumns;
      table.data = data;
      table.filter = "";
      table.groupColumn = this._tableState[kind].groupBy === "none" ? undefined : "_group";
      table.sortColumn = this._nativeSortColumn(this._tableState[kind].sortBy);
      table.sortDirection = this._tableState[kind].sortDirection;
      table.initialCollapsedGroups = [...this._nativeGroupLabels[kind]].filter(([, base]) => (
        this._collapsedTableGroups.has(`${kind}:${base}`)
      )).map(([group]) => group);
      table.selectable = kind === "overview" && this._selectionMode;
      table.clickable = false;
      table.noDataText = sourceRows.length
        ? this._t("table.empty_filtered")
        : this._t(kind === "history" ? "history.empty" : "table.empty_current");
      table.addEventListener("collapsed-changed", (event) => {
        for (const key of [...this._collapsedTableGroups]) {
          if (key.startsWith(`${kind}:`)) this._collapsedTableGroups.delete(key);
        }
        for (const group of event.detail?.value ?? []) {
          const base = this._nativeGroupLabels[kind].get(String(group));
          if (base) this._collapsedTableGroups.add(`${kind}:${base}`);
        }
      });
      table.addEventListener("sorting-changed", (event) => {
        const column = this._tableSortStateColumn(event.detail?.column);
        if (!column || !event.detail?.direction) return;
        this._tableState[kind].sortBy = column;
        this._tableState[kind].sortDirection = event.detail.direction;
        this._saveTablePreferences();
      });
      if (kind === "overview") {
        table.addEventListener("selection-changed", (event) => {
          const selected = new Set((event.detail?.value ?? []).map(String));
          if (selected.size === this._selectedAlertIds.size
            && [...selected].every((id) => this._selectedAlertIds.has(id))) return;
          this._selectedAlertIds = selected;
          this._updateSelectionToolbar();
        });
        if (this._selectionMode && this._selectedAlertIds.size) {
          const restore = () => table.isConnected && table.select?.([...this._selectedAlertIds], true);
          Promise.resolve(table.updateComplete).then(() => globalThis.setTimeout(restore, 130));
        }
      }
      const search = this.shadowRoot.querySelector(`#${kind}-table-search`);
      if (search) {
        search.value = this._tableState[kind].search;
        search.placeholder = this._t("table.search");
      }
    }
  }

  _updateSelectionToolbar() {
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
  }

  _configureSelector(id, selector, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element) return;
    element.hass = this._hass;
    if (this._configuredControls.has(element)) return;
    element.selector = selector;
    element.value = value;
    element.addEventListener("value-changed", (event) => onChange(event.detail?.value));
    this._configuredControls.add(element);
  }

  _configureSelect(id, options, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element || this._configuredControls.has(element)) return;
    element.options = options;
    element.value = value;
    element.addEventListener("selected", (event) => {
      element.value = event.detail?.value;
      onChange?.(event.detail?.value);
    });
    this._configuredControls.add(element);
  }

  _hydrateSelectors() {
    const shell = this.shadowRoot.querySelector("#panel-shell");
    if (shell && this._hass) {
      const activePage = TABS.find((tab) => tab.id === this._activeTab) ?? TABS[0];
      shell.hass = this._hass;
      shell.tabs = this._tabs();
      shell.route = { prefix: "", path: activePage.path };
      shell.backPath = "/config/integrations";
      shell.backCallback = window.history?.state?.from !== undefined
        ? () => window.history.back()
        : undefined;
    }
    if (!this._hass || !this._config) return;
    if (this._editingRule !== null) {
      const closeButton = this.shadowRoot.querySelector("#rule-editor-close");
      if (closeButton) {
        closeButton.label = this._t("rules.aria_close");
        closeButton.path = MDI_CLOSE;
      }
      const menuButton = this.shadowRoot.querySelector('[data-action="toggle-rule-menu"]');
      if (menuButton) menuButton.path = MDI_DOTS_VERTICAL;
      if (this._ruleEditorMode !== "visual") return;
      this._configureSelect(
        "rule-source",
        [
          { value: "state", label: this._t("rules.source_state") },
          { value: "attribute", label: this._t("rules.source_attribute") },
        ],
        this._editingRule.source ?? "state",
        (value) => {
          this._editingRule.source = value;
          this._ruleDirty = true;
          const attributeField = this.shadowRoot.querySelector(".rule-attribute-field");
          if (attributeField) attributeField.hidden = value !== "attribute";
        },
      );
      this._configureSelect(
        "rule-operator",
        [
          { value: "equals", label: this._t("operators.equals") },
          { value: "not_equals", label: this._t("operators.not_equals") },
          { value: "contains", label: this._t("operators.contains") },
          { value: "not_contains", label: this._t("operators.not_contains") },
          { value: "above", label: this._t("operators.above") },
          { value: "below", label: this._t("operators.below") },
        ],
        this._editingRule.operator ?? "equals",
        (value) => {
          this._captureRuleDraft();
          this._editingRule.operator = value;
          this._ruleDirty = true;
          if (TEXT_RULE_OPERATORS.has(value)) {
            this._editingRule.value = this._ruleValueList(this._editingRule.value);
          } else {
            this._editingRule.value = this._ruleValueList(this._editingRule.value)[0] ?? "";
          }
          this._render();
        },
      );
      this._configureSelector(
        "rule-entity-ids",
        { entity: { multiple: true, exclude_entities: ALERT_MANAGER_ENTITY_IDS } },
        this._editingRule.entity_ids ?? [],
        (value) => {
          this._editingRule.entity_ids = Array.isArray(value) ? value : [];
          this._ruleDirty = true;
        },
      );
    }
    if (this._activeTab !== "settings") return;
    this._ensureSettingsDraft();
    this._configureSelector(
      "excluded-labels",
      { label: { multiple: true } },
      this._settingsDraft.excluded_labels,
      (value) => { this._settingsDraft.excluded_labels = Array.isArray(value) ? value : []; },
    );
      this._configureSelector(
        "excluded-entities",
        { entity: { multiple: true, exclude_entities: ALERT_MANAGER_ENTITY_IDS } },
      this._settingsDraft.excluded_entities,
      (value) => { this._settingsDraft.excluded_entities = Array.isArray(value) ? value : []; },
    );
    this._configureSelector(
      "excluded-devices",
      { device: { multiple: true } },
      this._settingsDraft.excluded_devices,
      (value) => { this._settingsDraft.excluded_devices = Array.isArray(value) ? value : []; },
    );
    this._entityDelayDraft.forEach((row, index) => {
      this._configureSelector(
        `delay-entity-${index}`,
        { entity: { exclude_entities: ALERT_MANAGER_ENTITY_IDS } },
        row.entity_id || "",
        (value) => this._setEntityDelayEntity(index, value),
      );
    });
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
    if (this._activeTab === "automatic") return this._renderAutomatic();
    if (this._activeTab === "history") return this._renderHistory();
    if (this._activeTab === "rules") return this._renderRules();
    if (this._activeTab === "settings") return this._renderSettings();
    return this._renderOverview();
  }

  _tabFromRoute(route) {
    const path = `${route?.prefix ?? ""}${route?.path ?? ""}`.replace(/\/$/, "");
    return TABS.find((tab) => path.endsWith(`/${tab.id}`))?.id ?? "overview";
  }

  _renderOverview() {
    return `
      <section class="summary">
        <article><span>${esc(this._t("overview.summary_active"))}</span><strong class="danger">${this._alerts.active_count}</strong></article>
        <article><span>${esc(this._t("overview.summary_pending"))}</span><strong class="pending">${this._alerts.pending_count}</strong></article>
        <article><span>${esc(this._t("overview.summary_acknowledged"))}</span><strong class="acknowledged">${this._alerts.acknowledge_count ?? this._alerts.acknowledge?.length ?? 0}</strong></article>
        <article><span>${esc(this._t("overview.summary_tracked"))}</span><strong>${this._alerts.tracked_count ?? 0}</strong></article>
      </section>
      ${this._renderAlertTable("overview", this._tableRows("overview"))}`;
  }

  _renderHistory() {
    const limit = Number(this._historyConfig?.retention_limit ?? this._history?.retention_limit ?? 100);
    if (limit === 0) {
      return `<ha-card outlined class="history-empty"><div class="empty"><h2>${esc(this._t("history.disabled_title"))}</h2><p>${esc(this._t("history.disabled_help"))}</p><ha-button appearance="plain" data-action="open-history-settings">${esc(this._t("history.open_settings"))}</ha-button></div></ha-card>`;
    }
    const events = Array.isArray(this._history?.events) ? this._history.events : [];
    return this._renderAlertTable("history", this._tableRows("history", events));
  }

  _historyRuleName(event) {
    if (event.rule_name && event.rule_name !== event.type) return event.rule_name;
    const pack = this._packs.find((item) => item.id === event.type);
    return pack ? this._t(`packs.${pack.translation_key}.name`) : (event.rule_name || event.type);
  }

  _historyConditionText(event) {
    if (event.condition_key) return this._conditionText(event);
    if (!event.source || !event.operator) return event.condition ?? "";
    const source = this._t(
      event.source === "attribute" ? "conditions.sources.attribute" : "conditions.sources.state",
      { attribute: event.attribute ?? "" },
    );
    const expected = Array.isArray(event.comparison_value)
      ? event.comparison_value.join(" / ")
      : event.comparison_value;
    return `${source} ${this._t(`operators.${event.operator}`)} ${expected ?? ""}${event.unit ? ` ${event.unit}` : ""}`;
  }


  _tableColumns(kind) {
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
      message: { label: this._t("table.columns.message") },
      timeline: { label: this._t("table.columns.timeline") },
      resolved: { label: this._t("table.columns.resolved") },
      duration: { label: this._t("table.columns.duration") },
    };
    const allowed = kind === "overview"
      ? ["status", "device", "entity", "entity_id", "value", "condition", "detected", "timeline", "area", "rule", "message"]
      : ["status", "device", "entity", "entity_id", "value", "condition", "detected", "resolved", "duration", "area", "rule", "message"];
    return Object.fromEntries(allowed.map((column) => [column, all[column]]));
  }

  _alertRuleName(alert) {
    if (alert.rule_name && alert.rule_name !== alert.type) return alert.rule_name;
    const pack = this._packs.find((item) => item.id === alert.type);
    return pack ? this._t(`packs.${pack.translation_key}.name`) : (alert.rule_name || alert.type || "—");
  }

  _displayValue(value, unit) {
    if (value === undefined || value === null || value === "") return "—";
    const rendered = typeof value === "object" ? JSON.stringify(value) : String(value);
    return unit ? `${rendered} ${unit}` : rendered;
  }

  _tableRows(kind, historyEvents = []) {
    const create = (source, status, history = false) => {
      const entityName = history ? (source.entity_name || source.entity_id) : (source.name || source.entity_id);
      const value = history ? source.trigger_value : source.value;
      const condition = history ? this._historyConditionText(source) : this._conditionText(source);
      const rule = history ? this._historyRuleName(source) : this._alertRuleName(source);
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
        device: source.device_name || "",
        area: source.area || "",
        rule,
        message: source.message || "",
        value: this._displayValue(value, source.unit),
        rawValue: value,
        condition,
        detected: source.detected_at || "",
        activated: history ? source.active_at : source.active_since,
        resolved: history ? source.resolved_at : "",
        due: history ? "" : source.due_at,
        duration: history ? Number(source.total_duration_seconds ?? 0) : 0,
        acknowledged: history ? source.acknowledged === true : status === "acknowledged",
      };
      row.search = [
        row.rule, row.entityName, row.entityId, row.device, row.area, row.message,
        row.condition, row.value, row.statusLabel,
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

  _filterCount(kind) {
    return Object.values(this._tableState[kind].filters).filter(Boolean).length;
  }

  _filteredTableRows(kind, rows) {
    const state = this._tableState[kind];
    const query = state.search.trim().toLocaleLowerCase(this._language);
    const filters = state.filters;
    const filtered = rows.filter((row) => {
      if (query && !row.search.includes(query)) return false;
      if (filters.status && row.status !== filters.status) return false;
      if (filters.device && row.device !== filters.device) return false;
      if (filters.area && row.area !== filters.area) return false;
      if (filters.rule && row.rule !== filters.rule) return false;
      if (filters.entity && row.entityId !== filters.entity) return false;
      if (filters.acknowledged && String(row.acknowledged) !== filters.acknowledged) return false;
      if (!this._dateMatches(row.detected, filters.detectedFrom, filters.detectedTo)) return false;
      if (kind === "history" && !this._dateMatches(row.resolved, filters.resolvedFrom, filters.resolvedTo)) return false;
      return true;
    });
    const direction = state.sortDirection === "asc" ? 1 : -1;
    return filtered.sort((left, right) => direction * this._compareTableRows(left, right, state.sortBy));
  }

  _dateMatches(value, from, to) {
    if (!from && !to) return true;
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return false;
    if (from && timestamp < Date.parse(`${from}T00:00:00`)) return false;
    if (to && timestamp > Date.parse(`${to}T23:59:59.999`)) return false;
    return true;
  }

  _compareTableRows(left, right, key) {
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

  _renderAlertTable(kind, sourceRows) {
    const state = this._tableState[kind];
    const columns = this._tableColumns(kind);
    state.columns = state.columns.filter((column) => columns[column]);
    for (const required of REQUIRED_COLUMNS) {
      if (!state.columns.includes(required)) state.columns.push(required);
    }
    const visibleRows = this._filteredTableRows(kind, sourceRows);
    const selection = kind === "overview" && this._selectionMode;
    return `<ha-card outlined class="data-table-card ${selection ? "selection-active" : ""}">
      <ha-data-table class="native-alert-table" data-native-alert-table="${kind}">
        <div slot="header">${this._renderTableToolbar(kind, sourceRows, visibleRows)}</div>
      </ha-data-table>
      <div class="table-footer">${esc(this._t("table.visible_count", { visible: visibleRows.length, total: sourceRows.length }))}</div>
    </ha-card>`;
  }

  _renderTableToolbar(kind, sourceRows, visibleRows) {
    if (kind === "overview" && this._selectionMode) {
      const selectedRows = sourceRows.filter((row) => this._selectedAlertIds.has(row.id));
      const acknowledgeCount = selectedRows.filter((row) => row.status === "active").length;
      const unacknowledgeCount = selectedRows.filter((row) => row.status === "acknowledged").length;
      return `<div class="table-toolbar selection-toolbar" role="toolbar" aria-label="${esc(this._t("table.selection.toolbar"))}">
        <button type="button" class="toolbar-icon-button" data-action="close-selection" title="${esc(this._t("table.selection.close"))}" aria-label="${esc(this._t("table.selection.close"))}"><ha-svg-icon path="${MDI_CLOSE}"></ha-svg-icon></button>
        <button type="button" class="toolbar-button" data-action="select-visible">${esc(this._t("table.selection.select"))}</button>
        <strong class="selection-count" data-selection-count>${esc(this._t("table.selection.count", { count: selectedRows.length }))}</strong>
        <span class="toolbar-spacer"></span>
        <button type="button" class="toolbar-button primary" data-action="bulk-acknowledge" data-selection-action="acknowledge" ${acknowledgeCount ? "" : "hidden"} ${this._busy ? "disabled" : ""}>${esc(this._t("table.selection.acknowledge", { count: acknowledgeCount }))}</button>
        <button type="button" class="toolbar-button danger" data-action="bulk-unacknowledge" data-selection-action="unacknowledge" ${unacknowledgeCount ? "" : "hidden"} ${this._busy ? "disabled" : ""}>${esc(this._t("table.selection.unacknowledge", { count: unacknowledgeCount }))}</button>
      </div>`;
    }
    const filterCount = this._filterCount(kind);
    const menu = this._openTableMenu?.startsWith(`${kind}:`) ? this._openTableMenu.split(":")[1] : "";
    return `<div class="table-toolbar-wrap">
      <div class="table-toolbar" role="toolbar" aria-label="${esc(this._t("table.toolbar"))}">
        ${this._toolbarMenuButton(kind, "filters", MDI_FILTER_VARIANT, this._t("table.filters.title"), filterCount)}
        <ha-input-search id="${kind}-table-search" class="table-search" data-table-search="${kind}" appearance="outlined"></ha-input-search>
        <span class="toolbar-spacer"></span>
        ${this._toolbarMenuButton(kind, "group", MDI_GROUP, this._t("table.group.title"))}
        ${this._toolbarMenuButton(kind, "sort", MDI_SORT, this._t("table.sort.title"))}
        ${this._toolbarMenuButton(kind, "columns", MDI_TABLE_COLUMN, this._t("table.columns.title"))}
        ${kind === "overview" ? `<button type="button" class="toolbar-icon-button" data-action="open-selection" title="${esc(this._t("table.selection.open"))}" aria-label="${esc(this._t("table.selection.open"))}"><ha-svg-icon path="${MDI_CHECKBOX_MULTIPLE}"></ha-svg-icon></button>` : ""}
      </div>
      ${menu ? `<div class="table-menu table-menu-${menu}">${this._renderTableMenu(kind, menu, sourceRows, visibleRows)}</div>` : ""}
    </div>`;
  }

  _toolbarMenuButton(kind, menu, icon, label, count = 0) {
    const active = this._openTableMenu === `${kind}:${menu}`;
    return `<button type="button" class="toolbar-button ${active ? "is-active" : ""}" data-action="toggle-table-menu" data-table-kind="${kind}" data-menu="${menu}" aria-expanded="${active}"><ha-svg-icon path="${icon}"></ha-svg-icon><span>${esc(label)}</span>${count ? `<span class="filter-count">${count}</span>` : ""}</button>`;
  }

  _renderTableMenu(kind, menu, rows) {
    const state = this._tableState[kind];
    if (menu === "filters") return this._renderFilterMenu(kind, rows);
    if (menu === "group") {
      return `<fieldset><legend>${esc(this._t("table.group.title"))}</legend>${["none", "device", "area", "rule", "status"].map((value) => `<label><input type="radio" name="${kind}-group" data-table-setting="groupBy" data-table-kind="${kind}" value="${value}" ${state.groupBy === value ? "checked" : ""}>${esc(this._t(`table.group.${value}`))}</label>`).join("")}</fieldset>`;
    }
    if (menu === "sort") {
      const options = kind === "history"
        ? ["status", "device", "entityName", "rule", "value", "detected", "resolved"]
        : ["status", "device", "entityName", "rule", "value", "detected", "activated", "remaining"];
      return `<div class="menu-fields"><label>${esc(this._t("table.sort.title"))}<select data-table-setting="sortBy" data-table-kind="${kind}">${options.map((value) => `<option value="${value}" ${state.sortBy === value ? "selected" : ""}>${esc(this._t(`table.sort.${value === "entityName" ? "entity_name" : value}`))}</option>`).join("")}</select></label><label>${esc(this._t("table.sort.direction"))}<select data-table-setting="sortDirection" data-table-kind="${kind}"><option value="asc" ${state.sortDirection === "asc" ? "selected" : ""}>${esc(this._t("table.sort.asc"))}</option><option value="desc" ${state.sortDirection === "desc" ? "selected" : ""}>${esc(this._t("table.sort.desc"))}</option></select></label></div>`;
    }
    return this._renderColumnMenu(kind);
  }

  _facetOptions(rows, key) {
    return [...new Set(rows.map((row) => row[key]).filter(Boolean))]
      .sort((left, right) => String(left).localeCompare(String(right), this._language, { numeric: true }));
  }

  _filterSelect(kind, key, label, options) {
    const value = this._tableState[kind].filters[key];
    return `<label>${esc(label)}<select data-table-filter="${key}" data-table-kind="${kind}"><option value="">${esc(this._t("table.filters.all"))}</option>${options.map((option) => `<option value="${esc(option.value ?? option)}" ${value === String(option.value ?? option) ? "selected" : ""}>${esc(option.label ?? option)}</option>`).join("")}</select></label>`;
  }

  _renderFilterMenu(kind, rows) {
    const statuses = kind === "history"
      ? [{ value: "resolved", label: this._t("history.resolved") }]
      : ["active", "pending", "acknowledged"].map((value) => ({ value, label: this._t(`overview.status_${value}`) }));
    const filters = this._tableState[kind].filters;
    return `<div class="filter-grid">
      ${this._filterSelect(kind, "status", this._t("table.columns.status"), statuses)}
      ${this._filterSelect(kind, "device", this._t("table.columns.device"), this._facetOptions(rows, "device"))}
      ${this._filterSelect(kind, "area", this._t("table.columns.area"), this._facetOptions(rows, "area"))}
      ${this._filterSelect(kind, "rule", this._t("table.columns.rule"), this._facetOptions(rows, "rule"))}
      ${this._filterSelect(kind, "entity", this._t("table.columns.entity"), this._facetOptions(rows, "entityId").map((entityId) => ({ value: entityId, label: rows.find((row) => row.entityId === entityId)?.entityName || entityId })))}
      ${this._filterSelect(kind, "acknowledged", this._t("table.filters.acknowledged"), [{ value: "true", label: this._t("table.filters.yes") }, { value: "false", label: this._t("table.filters.no") }])}
      <label>${esc(this._t("table.filters.detected_from"))}<input type="date" data-table-filter="detectedFrom" data-table-kind="${kind}" value="${esc(filters.detectedFrom)}"></label>
      <label>${esc(this._t("table.filters.detected_to"))}<input type="date" data-table-filter="detectedTo" data-table-kind="${kind}" value="${esc(filters.detectedTo)}"></label>
      ${kind === "history" ? `<label>${esc(this._t("table.filters.resolved_from"))}<input type="date" data-table-filter="resolvedFrom" data-table-kind="history" value="${esc(filters.resolvedFrom)}"></label><label>${esc(this._t("table.filters.resolved_to"))}<input type="date" data-table-filter="resolvedTo" data-table-kind="history" value="${esc(filters.resolvedTo)}"></label>` : ""}
      <div class="filter-actions"><button type="button" class="toolbar-button" data-action="reset-filters" data-table-kind="${kind}" ${this._filterCount(kind) ? "" : "disabled"}>${esc(this._t("table.filters.reset"))}</button></div>
    </div>`;
  }

  _renderColumnMenu(kind) {
    const columns = this._tableColumns(kind);
    const visible = this._tableState[kind].columns;
    return `<div class="column-list">${Object.entries(columns).map(([column, definition]) => {
      const index = visible.indexOf(column);
      const required = REQUIRED_COLUMNS.has(column);
      return `<div class="column-option"><label><input type="checkbox" data-table-column="${column}" data-table-kind="${kind}" ${index >= 0 ? "checked" : ""} ${required ? "disabled" : ""}>${esc(definition.label)}</label><span>${index >= 0 ? `<button type="button" class="column-move" data-action="move-column" data-table-kind="${kind}" data-column="${column}" data-direction="up" ${index === 0 ? "disabled" : ""} aria-label="${esc(this._t("table.columns.move_up", { column: definition.label }))}"><ha-svg-icon path="${MDI_ARROW_UP}"></ha-svg-icon></button><button type="button" class="column-move" data-action="move-column" data-table-kind="${kind}" data-column="${column}" data-direction="down" ${index === visible.length - 1 ? "disabled" : ""} aria-label="${esc(this._t("table.columns.move_down", { column: definition.label }))}"><ha-svg-icon path="${MDI_ARROW_DOWN}"></ha-svg-icon></button>` : ""}</span></div>`;
    }).join("")}<button type="button" class="toolbar-button" data-action="reset-columns" data-table-kind="${kind}">${esc(this._t("table.columns.reset"))}</button></div>`;
  }

  _nativeTableColumns(kind) {
    const widths = {
      status: ["56px", "56px", 1],
      device: ["150px", "230px", 1],
      entity: ["180px", "280px", 1.4],
      entity_id: ["190px", "280px", 1],
      value: ["110px", "220px", 1],
      condition: ["260px", "420px", 2],
      detected: ["170px", "210px", 1],
      timeline: ["210px", "260px", 1.2],
      resolved: ["170px", "210px", 1],
      duration: ["120px", "170px", 1],
      area: ["130px", "220px", 1],
      rule: ["160px", "260px", 1],
      message: ["220px", "420px", 1.5],
    };
    const sortable = new Set(["status", "device", "entity", "value", "detected", "resolved", "rule"]);
    const valueColumns = {
      status: "statusSort",
      entity: "entityName",
      value: "valueSort",
      detected: "detectedSort",
      resolved: "resolvedSort",
    };
    const columns = Object.fromEntries(Object.entries(this._tableColumns(kind)).map(([column, definition]) => {
      const [minWidth, maxWidth, flex] = widths[column] ?? ["120px", "260px", 1];
      return [column, {
        title: definition.label,
        label: definition.label,
        main: column === "entity",
        type: column === "status" ? "icon" : undefined,
        minWidth,
        maxWidth,
        flex,
        sortable: sortable.has(column),
        valueColumn: valueColumns[column],
        template: (row) => this._nativeTableCell(kind, row, column),
      }];
    }));
    columns.activated = { title: this._t("table.sort.activated"), hidden: true, sortable: true, valueColumn: "activatedSort" };
    columns.remaining = { title: this._t("table.sort.remaining"), hidden: true, sortable: true, valueColumn: "remainingSort" };
    return columns;
  }

  _nativeTableData(kind, visibleRows) {
    const state = this._tableState[kind];
    const statusRank = { active: 0, pending: 1, acknowledged: 2, resolved: 3 };
    const rows = visibleRows.map(({ source: _source, ...row }) => ({
      ...row,
      statusSort: statusRank[row.status] ?? 99,
      valueSort: String(row.rawValue ?? ""),
      detectedSort: Date.parse(row.detected) || 0,
      activatedSort: Date.parse(row.activated) || 0,
      resolvedSort: Date.parse(row.resolved) || 0,
      remainingSort: Date.parse(row.due) || 0,
    }));
    this._nativeGroupLabels[kind] = new Map();
    if (state.groupBy === "none") return rows;
    const bases = visibleRows.map((row) => this._nativeGroupBase(kind, row));
    const counts = new Map();
    for (const base of bases) counts.set(base, (counts.get(base) ?? 0) + 1);
    return rows.map((row) => {
      const base = this._nativeGroupBase(kind, row);
      const group = `${base} (${counts.get(base) ?? 0})`;
      this._nativeGroupLabels[kind].set(group, base);
      return { ...row, _group: group };
    });
  }

  _nativeGroupBase(kind, row) {
    const groupBy = this._tableState[kind].groupBy;
    const value = groupBy === "status" ? row.statusLabel : row[groupBy];
    return value || this._t(`table.groups.without_${groupBy}`);
  }

  _nativeSortColumn(column) {
    return column === "entityName" ? "entity" : column;
  }

  _tableSortStateColumn(column) {
    return column === "entity" ? "entityName" : column;
  }

  _nativeTableCell(kind, row, column) {
    if (column === "status") return this._nativeStatusCell(row, kind);
    if (column === "entity") return this._nativeEntityCell(row);
    if (column === "entity_id") return row.entityId || "—";
    if (column === "device") return row.device || "—";
    if (column === "area") return row.area || "—";
    if (column === "rule") return row.rule || "—";
    if (column === "message") return row.message || "—";
    if (column === "value") return row.value;
    if (column === "condition") return row.condition || "—";
    if (column === "detected") return this._date(row.detected);
    if (column === "resolved") return this._date(row.resolved);
    if (column === "duration") return this._historyDurationText(row.duration);
    if (column === "timeline") return this._nativeTimelineCell(row);
    return "—";
  }

  _nativeStatusCell(row, kind) {
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
    status.style.cssText = `display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;color:${color};background:${background}`;
    const icon = document.createElement("ha-svg-icon");
    icon.path = path;
    icon.style.cssText = "width:21px;height:21px";
    status.append(icon);
    return status;
  }

  _nativeEntityCell(row) {
    if (!globalThis.document?.createElement) return row.entityName;
    if (!this._hass?.states?.[row.entityId]) {
      const label = document.createElement("span");
      label.textContent = row.entityName;
      return label;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.entityName;
    button.setAttribute("aria-label", row.entityName);
    button.style.cssText = "border:0;background:transparent;padding:0;color:var(--primary-text-color,#212121);font:inherit;font-weight:var(--ha-font-weight-medium,500);text-align:left;cursor:pointer";
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      this._openMoreInfo(row.entityId);
    });
    return button;
  }

  _nativeTimelineCell(row) {
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

  _openMoreInfo(entityId) {
    if (!this._hass?.states?.[entityId]) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    }));
  }

  _renderAutomatic() {
    const availablePacks = this._packs.filter((pack) => pack.available);
    return `<form id="automatic-form" class="automatic-grid">
      ${availablePacks.map((pack) => {
        const config = this._config.automatic[pack.id];
        const packKey = pack.translation_key || pack.id;
        const packName = this._t(`packs.${packKey}.name`);
        return `<section class="panel category-card">
          <div class="category-header">
            <h2>${esc(packName)}</h2>
            <ha-switch id="auto-${pack.id}-enabled" aria-label="${esc(this._t("automatic.aria_enable", { name: packName }))}" ${config.enabled ? "checked" : ""}></ha-switch>
          </div>
          <p>${esc(this._t(`packs.${packKey}.description`))}</p>
          <div class="fields">
            ${this._numberField(`auto-${pack.id}-delay`, this._t("automatic.pack_delay"), config.delay, this._t("units.seconds"), 0, 31536000, { required: false })}
            ${pack.id === "battery" ? this._numberField("battery-threshold", this._t("automatic.threshold"), config.threshold, "%", -1000000000, 1000000000, { step: "any" }) : ""}
          </div>
          <small>${esc(this._t("automatic.empty_delay_help"))}</small>
        </section>`;
      }).join("")}
      <div class="actions automatic-actions"><ha-button appearance="accent" variant="brand" data-action="save-automatic" ${this._busy ? "disabled" : ""}>${esc(this._t("automatic.save"))}</ha-button></div>
    </form>`;
  }

  _renderRules() {
    const rules = this._config.rules ?? [];
    const editorOpen = this._editingRule !== null;
    const editor = editorOpen ? this._renderRuleEditor() : "";
    return `<div class="rules-layout ${editorOpen ? "has-editor" : ""}" style="--rule-editor-width:${this._ruleEditorWidth}px"><section class="panel rules-list-panel">
      <div><h2>${esc(this._t("rules.title"))}</h2><p>${esc(this._t("rules.description"))}</p></div>
      ${rules.length ? `<div class="table-wrap"><table><thead><tr><th>${esc(this._t("rules.name"))}</th><th>${esc(this._t("rules.entities"))}</th><th>${esc(this._t("rules.condition"))}</th><th>${esc(this._t("rules.duration"))}</th><th class="rule-toggle-cell">${esc(this._t("overview.status_active"))}</th></tr></thead><tbody>
        ${rules.map((rule) => `<tr class="rule-row ${this._editingRule?.id === rule.id ? "is-selected" : ""}" data-action="edit-rule" data-id="${esc(rule.id)}" tabindex="0" aria-label="${esc(this._t("rules.aria_edit", { name: rule.name }))}">
          <td>${esc(rule.name)}</td><td>${rule.entity_ids.map((entityId) => `<code>${esc(entityId)}</code>`).join("")}</td>
          <td>${esc(this._ruleSummary(rule))}</td><td>${esc(this._durationText(rule.duration))}</td>
          <td class="rule-toggle-cell"><ha-switch haptic data-action="toggle-rule" data-id="${esc(rule.id)}" aria-label="${esc(this._t(rule.enabled ? "rules.aria_disable" : "rules.aria_enable", { name: rule.name }))}" ${rule.enabled ? "checked" : ""} ${this._busy ? "disabled" : ""}></ha-switch></td>
        </tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">${esc(this._t("rules.empty"))}</div>`}
      <div class="actions new-rule-action"><ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(this._t("rules.new"))}</ha-button></div>
    </section>${editor}</div>`;
  }

  _renderRuleEditor() {
    const rule = { ...newRuleDefaults(), ...(this._editingRule ?? {}) };
    rule.value = TEXT_RULE_OPERATORS.has(rule.operator)
      ? this._ruleValueList(rule.value)
      : this._ruleValueList(rule.value)[0] ?? "";
    this._editingRule = rule;
    const yamlMode = this._ruleEditorMode === "yaml";
    const editorContent = yamlMode ? this._renderRuleYamlEditor(rule) : this._renderRuleVisualEditor(rule);
    return `<div class="rule-editor-backdrop" data-action="cancel-rule" aria-hidden="true"></div>
    <ha-card outlined class="rule-editor-drawer" role="dialog" aria-modal="false" aria-label="${esc(this._t(rule.id ? "rules.aria_edit_dialog" : "rules.aria_create_dialog"))}">
      <div class="rule-editor-resize" role="separator" aria-orientation="vertical" aria-label="${esc(this._t("rules.aria_resize"))}" tabindex="0"><div class="resize-indicator"></div></div>
      <ha-dialog-header show-border>
        <ha-icon-button id="rule-editor-close" slot="navigationIcon" data-action="cancel-rule"></ha-icon-button>
        <span slot="title">${esc(this._t(rule.id ? "rules.modify" : "rules.create"))}</span>
        ${rule.id ? "" : `<span slot="subtitle">${esc(this._t("rules.new_subtitle"))}</span>`}
        <div slot="actionItems" class="rule-menu-wrap"><ha-icon-button data-action="toggle-rule-menu" aria-label="${esc(this._t("rules.aria_menu"))}" title="${esc(this._t("rules.aria_menu"))}"></ha-icon-button>${this._ruleMenuOpen ? `<div class="rule-editor-menu" role="menu"><ha-button appearance="plain" data-action="switch-rule-editor">${esc(this._t(yamlMode ? "rules.edit_visually" : "rules.edit_yaml"))}</ha-button></div>` : ""}</div>
      </ha-dialog-header>
      <form id="rule-form" class="rule-editor-form">
        ${editorContent}
        <div class="actions rule-editor-actions">${rule.id ? `<ha-button appearance="plain" variant="danger" data-action="delete-rule" data-id="${esc(rule.id)}">${esc(this._t("buttons.delete"))}</ha-button>` : ""}<span class="action-spacer"></span><ha-button appearance="plain" data-action="cancel-rule">${esc(this._t("buttons.cancel"))}</ha-button><ha-button appearance="accent" variant="brand" data-action="save-rule" ${this._busy ? "disabled" : ""}>${esc(this._t("buttons.save"))}</ha-button></div>
      </form>
    </ha-card>`;
  }

  _renderRuleVisualEditor(rule) {
    return `
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>${esc(this._t("rules.editor_information"))}</h3><small>${esc(this._t("rules.editor_information_help"))}</small></div></div>
          <div class="fields">
            ${this._textField("name", this._t("rules.name"), rule.name, true, "name", "full rule-name-field")}
            <div class="field full"><span class="field-label">${esc(this._t("rules.entities"))}</span><ha-selector id="rule-entity-ids"></ha-selector><small>${esc(this._t("rules.entities_help"))}</small></div>
          </div>
        </section>
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>${esc(this._t("rules.condition"))}</h3><small>${esc(this._t("rules.editor_condition_help"))}</small></div></div>
          <div class="fields">
            <div class="field"><span class="field-label">${esc(this._t("rules.source"))}</span><ha-select id="rule-source" data-field="source"></ha-select></div>
            <div class="field rule-attribute-field" ${rule.source === "attribute" ? "" : "hidden"}><span class="field-label">${esc(this._t("rules.attribute_name"))}</span><ha-input name="attribute" data-field="attribute" type="text" value="${esc(rule.attribute || "")}" aria-label="${esc(this._t("rules.attribute_name"))}"></ha-input></div>
            <div class="field full"><span class="field-label">${esc(this._t("rules.operator"))}</span><ha-select id="rule-operator" data-field="operator"></ha-select></div>
            ${this._renderRuleValues(rule)}
          </div>
        </section>
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>${esc(this._t("rules.editor_trigger"))}</h3><small>${esc(this._t("rules.editor_trigger_help"))}</small></div></div>
          <div class="fields">
            ${this._numberField("duration", this._t("rules.duration"), rule.duration, this._t("units.seconds"), 0, 31536000, { nameMode: "name" })}
            ${this._textField("message", this._t("rules.message_optional"), rule.message || "", false, "name", "full rule-message-field")}
          </div>
        </section>`;
  }

  _renderRuleYamlEditor(rule) {
    if (!this._ruleYaml) this._ruleYaml = ruleToYaml(rule);
    return `<section class="rule-editor-section yaml-rule-section">
      <div class="rule-section-heading"><div><h3>${esc(this._t("rules.yaml_title"))}</h3><small>${esc(this._t("rules.yaml_help"))}</small></div></div>
      <ha-code-editor id="rule-yaml-editor" mode="yaml" aria-label="${esc(this._t("rules.yaml_title"))}"></ha-code-editor>
      ${this._ruleYamlError ? `<div class="yaml-error" role="alert">${esc(this._ruleYamlError)}</div>` : ""}
    </section>`;
  }

  _renderRuleValues(rule) {
    if (!TEXT_RULE_OPERATORS.has(rule.operator)) {
      return `<div class="field full"><span class="field-label">${esc(this._t("rules.value"))}</span><ha-input data-field="value" name="value" type="number" step="any" value="${esc(rule.value)}" required aria-label="${esc(this._t("rules.value"))}"></ha-input></div>`;
    }
    const values = this._ruleValueList(rule.value);
    const multipleHint = rule.operator === "equals" || rule.operator === "contains"
      ? this._t("rules.multiple_any")
      : this._t("rules.multiple_none");
    return `<div class="field full rule-values-field"><span class="field-label">${esc(this._t("rules.values"))}</span><div class="rule-value-list">
      ${values.map((value, index) => `<div class="rule-value-row"><ha-input data-rule-value-index="${index}" type="text" value="${esc(value)}" required aria-label="${esc(this._t("rules.aria_value", { index: index + 1 }))}"></ha-input>${values.length > 1 ? `<ha-button appearance="plain" variant="danger" data-action="remove-rule-value" data-index="${index}" aria-label="${esc(this._t("rules.aria_remove_value", { index: index + 1 }))}">${esc(this._t("buttons.remove"))}</ha-button>` : ""}</div>`).join("")}
    </div><div class="rule-value-footer"><small>${esc(multipleHint)}</small><ha-button appearance="plain" data-action="add-rule-value"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(this._t("buttons.add"))}</ha-button></div></div>`;
  }

  _ruleValueList(value) {
    return (Array.isArray(value) ? value : [value ?? ""]).map((item) => String(item));
  }

  _renderSettings() {
    this._ensureSettingsDraft();
    return `<form id="settings-form" class="stack">
      <section class="panel"><h2>${esc(this._t("settings.general"))}</h2><div class="fields">
        ${this._numberField("global-delay", this._t("settings.global_delay"), this._config.global_delay, this._t("units.seconds"), 0, 31536000, { help: this._t("settings.global_delay_help") })}
        <div class="field"><span class="field-label">${esc(this._t("settings.label_exclusions"))}</span><ha-selector id="excluded-labels"></ha-selector><small>${esc(this._t("settings.labels_help"))}</small></div>
        <div class="history-settings full">
          <div class="history-settings-row">
            <span class="field-label history-limit-label">${esc(this._t("settings.history_limit"))}</span>
            <ha-input id="history-limit" type="number" min="0" max="1000" step="1" value="${esc(this._historyConfig.retention_limit)}" required aria-label="${esc(this._t("settings.history_limit"))}"><span slot="end">${esc(this._t("units.events"))}</span></ha-input>
            <div class="actions history-actions"><ha-button appearance="plain" variant="danger" data-action="clear-history" ${this._busy || !(this._history?.events?.length) ? "disabled" : ""}>${esc(this._t("settings.history_clear"))}</ha-button></div>
          </div>
          <small class="history-limit-help">${esc(this._t("settings.history_limit_help"))}</small>
        </div>
      </div></section>
      <section class="panel"><h2>${esc(this._t("settings.explicit_exclusions"))}</h2><div class="fields">
        <div class="field"><span class="field-label">${esc(this._t("settings.entity_exclusions"))}</span><ha-selector id="excluded-entities"></ha-selector></div>
        <div class="field"><span class="field-label">${esc(this._t("settings.device_exclusions"))}</span><ha-selector id="excluded-devices"></ha-selector></div>
      </div></section>
      <section class="panel"><div><h2>${esc(this._t("settings.entity_delay"))}</h2><small>${esc(this._t("settings.delay_help"))}</small></div>
        <div class="delay-list">${this._entityDelayDraft.length ? this._entityDelayDraft.map((row, index) => `<div class="delay-row">
          <ha-selector id="delay-entity-${index}"></ha-selector>
          <ha-input data-delay-index="${index}" type="number" min="0" max="31536000" step="1" value="${esc(row.delay)}" required aria-label="${esc(this._t("settings.aria_delay"))}"><span slot="end">${esc(this._t("units.seconds"))}</span></ha-input>
          <ha-button appearance="plain" variant="danger" data-action="remove-entity-delay" data-index="${index}" aria-label="${esc(this._t("settings.aria_remove_delay"))}">${esc(this._t("buttons.delete"))}</ha-button>
        </div>`).join("") : `<div class="empty compact">${esc(this._t("settings.no_delay"))}</div>`}</div>
        <div class="actions delay-add-action"><ha-button appearance="accent" variant="brand" data-action="add-entity-delay"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(this._t("buttons.add"))}</ha-button></div>
      </section>
      <section class="panel configuration-transfer"><div><h2>${esc(this._t("settings.transfer_title"))}</h2><small>${esc(this._t("settings.transfer_help"))}</small></div>
        <div class="actions transfer-actions"><ha-button appearance="plain" data-action="export-config" ${this._busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_DOWNLOAD}"></ha-svg-icon>${esc(this._t("settings.export"))}</ha-button><ha-button appearance="accent" variant="brand" data-action="choose-config-import" ${this._busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_UPLOAD}"></ha-svg-icon>${esc(this._t("settings.import"))}</ha-button></div>
        <input id="config-import-file" data-import-file type="file" accept=".yaml,.yml,text/yaml,application/x-yaml" hidden>
      </section>
      <div class="actions settings-save-actions"><ha-button appearance="accent" variant="brand" data-action="save-settings" ${this._busy ? "disabled" : ""}>${esc(this._t("settings.save"))}</ha-button></div>
    </form>`;
  }

  _numberField(id, label, value, suffix, min, max, options = {}) {
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

  _ruleSummary(rule) {
    const source = rule.source === "attribute"
      ? this._t("conditions.sources.attribute", { attribute: rule.attribute })
      : this._t("conditions.sources.state");
    const expected = this._ruleValueList(rule.value).join(" / ");
    return `${source} ${this._t(`operators.${rule.operator}`)} ${expected}`;
  }

  async _handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "toggle-table-menu") {
      const key = `${button.dataset.tableKind}:${button.dataset.menu}`;
      this._openTableMenu = this._openTableMenu === key ? "" : key;
      this._render();
      return;
    }
    if (action === "open-selection") {
      this._selectionMode = true;
      this._selectedAlertIds.clear();
      this._openTableMenu = "";
      this._render();
      return;
    }
    if (action === "close-selection") {
      this._selectionMode = false;
      this._selectedAlertIds.clear();
      this._render();
      return;
    }
    if (action === "select-visible") {
      const table = this.shadowRoot.querySelector('[data-native-alert-table="overview"]');
      const visible = this._filteredTableRows("overview", this._tableRows("overview"));
      const select = !visible.length || !visible.every((row) => this._selectedAlertIds.has(row.id));
      if (table?.selectAll && table?.clearSelection) {
        if (select) table.selectAll();
        else table.clearSelection();
        return;
      }
      for (const row of visible) {
        if (select) this._selectedAlertIds.add(row.id);
        else this._selectedAlertIds.delete(row.id);
      }
      this._updateSelectionToolbar();
      return;
    }
    if (action === "bulk-acknowledge" || action === "bulk-unacknowledge") {
      await this._bulkAlertAction(action === "bulk-acknowledge" ? "acknowledge" : "unacknowledge");
      return;
    }
    if (action === "reset-filters") {
      const kind = button.dataset.tableKind;
      Object.keys(this._tableState[kind].filters).forEach((key) => {
        this._tableState[kind].filters[key] = "";
      });
      this._render();
      return;
    }
    if (action === "reset-columns") {
      const kind = button.dataset.tableKind;
      this._tableState[kind].columns = [...DEFAULT_TABLE_STATE[kind].columns];
      this._saveTablePreferences();
      this._render();
      return;
    }
    if (action === "move-column") {
      const { tableKind: kind, column, direction } = button.dataset;
      const columns = this._tableState[kind].columns;
      const index = columns.indexOf(column);
      const target = direction === "up" ? index - 1 : index + 1;
      if (index >= 0 && target >= 0 && target < columns.length) {
        [columns[index], columns[target]] = [columns[target], columns[index]];
        this._saveTablePreferences();
        this._render();
      }
      return;
    }
    if (action === "enable-monitoring") {
      if (this._busy) return;
      this._busy = true;
      this._render();
      try {
        await this._hass.callService("switch", "turn_on", {
          entity_id: "switch.alert_manager_main_monitoring",
        });
        this._monitoringEnabled = true;
        if (this._config) this._config.monitoring_enabled = true;
      } catch (error) {
        this._notice = { kind: "error", text: this._errorText(error) };
      } finally {
        this._busy = false;
        this._render();
      }
      return;
    }
    if (action === "more-info") {
      this._openMoreInfo(button.dataset.entityId);
      return;
    }
    if (action === "tab") {
      this._activeTab = button.dataset.tab;
      this._editingRule = null;
      this._notice = null;
      this._render();
      return;
    }
    if (action === "save-automatic") {
      const form = this.shadowRoot.querySelector("#automatic-form");
      if (form && this._reportFormValidity(form) && !this._busy) {
        await this._saveAutomatic();
      }
      return;
    }
    if (action === "save-settings") {
      const form = this.shadowRoot.querySelector("#settings-form");
      if (form && this._reportFormValidity(form) && !this._busy) {
        await this._saveSettings();
      }
      return;
    }
    if (action === "clear-history") {
      if (!window.confirm(this._t("settings.history_clear_confirm"))) return;
      const result = await this._call(
        { type: "alert_manager/history/clear", confirmed: true },
        this._t("success.history_cleared"),
      );
      if (result) this._history = result;
      return;
    }
    if (action === "open-history-settings") {
      this._activeTab = "settings";
      this._notice = null;
      window.history?.pushState?.(null, "", "/alert-manager/settings");
      this._render();
      return;
    }
    if (action === "export-config") {
      await this._exportConfiguration();
      return;
    }
    if (action === "choose-config-import") {
      this.shadowRoot.querySelector("#config-import-file")?.click();
      return;
    }
    if (action === "new-rule") {
      this._editingRule = {};
      this._ruleEditorMode = "visual";
      this._ruleYaml = "";
      this._ruleYamlError = null;
      this._ruleMenuOpen = false;
      this._ruleDirty = false;
      this._render();
      return;
    }
    if (action === "cancel-rule") {
      this._cancelRuleEditor();
      return;
    }
    if (action === "toggle-rule-menu") {
      this._ruleMenuOpen = !this._ruleMenuOpen;
      this._render();
      return;
    }
    if (action === "switch-rule-editor") {
      await this._switchRuleEditor();
      return;
    }
    if (action === "add-rule-value") {
      this._captureRuleDraft();
      this._editingRule.value = [...this._ruleValueList(this._editingRule.value), ""];
      this._ruleDirty = true;
      this._render();
      return;
    }
    if (action === "remove-rule-value") {
      this._captureRuleDraft();
      const values = this._ruleValueList(this._editingRule.value);
      values.splice(Number(button.dataset.index), 1);
      this._editingRule.value = values.length ? values : [""];
      this._ruleDirty = true;
      this._render();
      return;
    }
    if (action === "add-entity-delay") {
      this._ensureSettingsDraft();
      this._captureEntityDelayValues();
      this._entityDelayDraft.push({ entity_id: "", delay: 900 });
      this._render();
      return;
    }
    if (action === "remove-entity-delay") {
      this._captureEntityDelayValues();
      this._entityDelayDraft.splice(Number(button.dataset.index), 1);
      this._render();
      return;
    }
    if (action === "save-rule") {
      const form = this.shadowRoot.querySelector("#rule-form");
      if (form && !this._busy) {
        if (this._ruleEditorMode === "yaml") await this._saveRuleYaml();
        else if (this._reportFormValidity(form)) await this._saveRule(form);
      }
      return;
    }
    const rule = (this._config.rules || []).find((item) => item.id === button.dataset.id);
    if (!rule) return;
    if (action === "edit-rule") {
      this._editingRule = { ...rule };
      this._ruleEditorMode = "visual";
      this._ruleYaml = "";
      this._ruleYamlError = null;
      this._ruleMenuOpen = false;
      this._ruleDirty = false;
      this._render();
    } else if (action === "toggle-rule") {
      const updated = await this._call(
        { type: "alert_manager/rules/update", rule_id: rule.id, rule: { enabled: !rule.enabled } },
        this._t(rule.enabled ? "success.rule_disabled" : "success.rule_enabled"),
      );
      if (updated) this._replaceRule(updated);
    } else if (action === "delete-rule") {
      if (!window.confirm(this._t("rules.delete_confirm", { name: rule.name }))) return;
      const result = await this._call(
        { type: "alert_manager/rules/delete", rule_id: rule.id },
        this._t("success.rule_deleted"),
      );
      if (result !== null) {
        this._config.rules = this._config.rules.filter((item) => item.id !== rule.id);
        if (this._editingRule?.id === rule.id) this._editingRule = null;
        this._render();
      }
    }
  }

  async _bulkAlertAction(service) {
    if (this._busy) return;
    const compatibleStatus = service === "acknowledge" ? "active" : "acknowledged";
    const rows = this._tableRows("overview").filter((row) => (
      this._selectedAlertIds.has(row.id) && row.status === compatibleStatus
    ));
    if (!rows.length) return;
    this._busy = true;
    this._notice = null;
    this._render();
    const results = await Promise.allSettled(rows.map((row) => this._hass.callService(
      "alert_manager",
      service,
      { alert_id: row.id },
    )));
    const succeeded = rows.filter((_row, index) => results[index].status === "fulfilled");
    for (const row of succeeded) {
      this._applyOptimisticAcknowledgement(row.id, service === "acknowledge");
      this._selectedAlertIds.delete(row.id);
    }
    const failed = rows.length - succeeded.length;
    this._notice = failed
      ? {
        kind: "error",
        text: this._t("table.selection.partial", { count: succeeded.length, failed }),
      }
      : {
        kind: "success",
        text: this._t(
          service === "acknowledge" ? "table.selection.acknowledged_result" : "table.selection.unacknowledged_result",
          { count: succeeded.length },
        ),
      };
    this._busy = false;
    this._render();
  }

  _applyOptimisticAcknowledgement(alertId, acknowledged) {
    const fromKey = acknowledged ? "alerts" : "acknowledge";
    const toKey = acknowledged ? "acknowledge" : "alerts";
    const index = (this._alerts[fromKey] ?? []).findIndex((alert) => alert.id === alertId);
    if (index < 0) return;
    const [alert] = this._alerts[fromKey].splice(index, 1);
    const updated = acknowledged
      ? {
        ...alert,
        acknowledged: true,
        acknowledged_at: new Date().toISOString(),
        acknowledged_by: this._hass?.user?.name || null,
      }
      : {
        ...alert,
        acknowledged: false,
        acknowledged_at: null,
        acknowledged_by: null,
      };
    this._alerts[toKey] = [...(this._alerts[toKey] ?? []), updated];
    this._alerts.active_count = this._alerts.alerts.length;
    this._alerts.acknowledge_count = this._alerts.acknowledge.length;
  }

  _handleInput(event) {
    const target = event.target;
    const kind = target?.dataset?.tableSearch;
    if (kind && this._tableState[kind]) {
      const cursor = target.selectionStart;
      this._tableState[kind].search = String(event.detail?.value ?? target.value ?? "");
      this._render();
      const search = this.shadowRoot.querySelector(`#${kind}-table-search`);
      search?.focus?.();
      search?.setSelectionRange?.(cursor, cursor);
      return;
    }
    this._handleRuleInput(event);
  }

  _handleChange(event) {
    const target = event.target;
    const kind = target?.dataset?.tableKind;
    if (kind && target.dataset.tableFilter) {
      this._tableState[kind].filters[target.dataset.tableFilter] = String(target.value ?? "");
      this._render();
      return;
    }
    if (kind && target.dataset.tableSetting) {
      this._tableState[kind][target.dataset.tableSetting] = String(target.value ?? "");
      this._saveTablePreferences();
      this._render();
      return;
    }
    if (kind && target.dataset.tableColumn) {
      const column = target.dataset.tableColumn;
      const columns = this._tableState[kind].columns;
      if (target.checked && !columns.includes(column)) columns.push(column);
      if (!target.checked && !REQUIRED_COLUMNS.has(column)) {
        this._tableState[kind].columns = columns.filter((item) => item !== column);
      }
      this._saveTablePreferences();
      this._render();
      return;
    }
    void this._handleImportSelection(event);
  }

  _handleRuleInput(event) {
    if (this._editingRule === null) return;
    const target = event.target;
    if (target?.closest?.("#rule-form")) this._ruleDirty = true;
    if (target?.id === "rule-yaml-editor") {
      this._ruleYaml = String(target.value ?? this._ruleYaml);
      this._ruleYamlError = null;
    }
  }

  _cancelRuleEditor() {
    if (this._ruleDirty && !window.confirm(this._t("rules.discard_confirm"))) return;
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleMenuOpen = false;
    this._ruleDirty = false;
    this._render();
  }

  async _switchRuleEditor() {
    this._ruleMenuOpen = false;
    if (this._ruleEditorMode === "visual") {
      this._captureRuleDraft();
      this._ruleYaml = ruleToYaml(this._editingRule ?? newRuleDefaults());
      this._ruleYamlError = null;
      this._ruleEditorMode = "yaml";
      this._render();
      return;
    }
    const ruleId = this._editingRule?.id;
    const validated = await this._call(
      {
        type: "alert_manager/rules/yaml/validate",
        yaml: this._ruleYaml,
        ...(ruleId ? { rule_id: ruleId } : {}),
      },
      "",
    );
    if (!validated) {
      this._ruleYamlError = this._notice?.text ?? this._t("rules.yaml_invalid");
      this._render();
      return;
    }
    this._editingRule = { ...validated, ...(ruleId ? { id: ruleId } : {}) };
    this._ruleYamlError = null;
    this._ruleEditorMode = "visual";
    this._render();
  }

  async _saveRuleYaml() {
    const id = String(this._editingRule?.id ?? "");
    const message = id
      ? { type: "alert_manager/rules/yaml/update", rule_id: id, yaml: this._ruleYaml }
      : { type: "alert_manager/rules/yaml/create", yaml: this._ruleYaml };
    const updated = await this._call(
      message,
      this._t(id ? "success.rule_updated" : "success.rule_created"),
    );
    if (!updated) {
      this._ruleYamlError = this._notice?.text ?? this._t("rules.yaml_invalid");
      this._render();
      return;
    }
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleDirty = false;
    this._replaceRule(updated);
  }

  async _exportConfiguration() {
    const result = await this._call(
      { type: "alert_manager/config/export" },
      this._t("success.config_exported"),
    );
    if (!result?.yaml) return;
    const blob = new Blob([result.yaml], { type: "application/yaml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "alert-manager-config.yaml";
    link.click();
    URL.revokeObjectURL(url);
  }

  async _handleImportSelection(event) {
    const input = event.target;
    if (!input?.matches?.("[data-import-file]") || this._busy) return;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    let rawYaml;
    try {
      rawYaml = await file.text();
    } catch (_error) {
      this._notice = { kind: "error", text: this._t("settings.import_read_error") };
      this._render();
      return;
    }
    const summary = await this._call(
      { type: "alert_manager/config/import/validate", yaml: rawYaml },
      "",
    );
    if (!summary) return;
    const prompt = this._t("settings.import_confirm", {
      rules: summary.rules,
      packs: summary.enabled_packs,
      delays: summary.entity_delays,
    });
    if (!window.confirm(prompt)) return;
    const result = await this._call(
      { type: "alert_manager/config/import", yaml: rawYaml, confirmed: true },
      this._t("success.config_imported"),
    );
    if (!result?.config) return;
    this._config = result.config;
    this._monitoringEnabled = this._config.monitoring_enabled !== false;
    this._resetSettingsDraft();
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleDirty = false;
    try {
      this._alerts = await this._hass.callWS({ type: "alert_manager/alerts/list" });
      this._syncSensor();
    } catch (_error) {
      // The integration has already completed the import.  The sensor update
      // will refresh the overview shortly even if this immediate read failed.
    }
    this._render();
  }

  _startRuleEditorResize(event) {
    const handle = event.target.closest?.(".rule-editor-resize");
    if (!handle || window.innerWidth <= 700) return;
    event.preventDefault();
    const drawer = this.shadowRoot.querySelector(".rule-editor-drawer");
    this._ruleEditorResize = {
      startX: event.clientX,
      startWidth: drawer?.getBoundingClientRect?.().width ?? this._ruleEditorWidth,
    };
    handle.classList?.add("is-resizing");
    document.addEventListener("pointermove", this._ruleEditorResizeMove);
    document.addEventListener("pointerup", this._ruleEditorResizeEnd);
    document.addEventListener("pointercancel", this._ruleEditorResizeEnd);
    document.body?.style.setProperty("cursor", "ew-resize");
    document.body?.style.setProperty("user-select", "none");
  }

  _resizeRuleEditor(event) {
    if (!this._ruleEditorResize) return;
    const delta = this._ruleEditorResize.startX - event.clientX;
    this._setRuleEditorWidth(this._ruleEditorResize.startWidth + delta);
  }

  _setRuleEditorWidth(width) {
    const viewportWidth = Number(window.innerWidth) || 1400;
    const maximum = Math.max(360, Math.min(800, viewportWidth - 64));
    this._ruleEditorWidth = Math.round(Math.min(maximum, Math.max(360, width)));
    this.shadowRoot.querySelector(".rules-layout")?.style.setProperty(
      "--rule-editor-width",
      `${this._ruleEditorWidth}px`,
    );
  }

  _stopRuleEditorResize() {
    document.removeEventListener("pointermove", this._ruleEditorResizeMove);
    document.removeEventListener("pointerup", this._ruleEditorResizeEnd);
    document.removeEventListener("pointercancel", this._ruleEditorResizeEnd);
    document.body?.style.removeProperty("cursor");
    document.body?.style.removeProperty("user-select");
    this.shadowRoot?.querySelector(".rule-editor-resize")?.classList.remove("is-resizing");
    this._ruleEditorResize = null;
  }

  _resetRuleEditorWidth(event) {
    if (!event.target.closest?.(".rule-editor-resize")) return;
    event.preventDefault();
    this._setRuleEditorWidth(560);
  }

  _handleKeydown(event) {
    if (event.target.closest?.(".rule-editor-resize") && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      this._setRuleEditorWidth(this._ruleEditorWidth + (event.key === "ArrowLeft" ? 16 : -16));
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest?.(".rule-row[data-action=\"edit-rule\"]");
    if (!row || event.target.closest?.("ha-switch")) return;
    event.preventDefault();
    void this._handleClick({ target: row });
  }

  async _handleSubmit(event) {
    event.preventDefault();
    if (this._busy) return;
    // The save call rerenders the panel. Keep the form reference before the
    // first await because the browser may clear Event.target afterwards.
    const form = event.target;
    const formId = form?.id;
    if (formId === "automatic-form") {
      await this._saveAutomatic();
      return;
    }
    if (formId === "settings-form") {
      await this._saveSettings();
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
    return valid;
  }

  async _saveAutomatic() {
    const automatic = {};
    for (const pack of this._packs.filter((item) => item.available)) {
      const delayValue = this.shadowRoot.querySelector(`#auto-${pack.id}-delay`).value;
      automatic[pack.id] = {
        enabled: this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`).checked,
        delay: delayValue === "" ? null : Number(delayValue),
      };
      if (pack.id === "battery") {
        automatic[pack.id].threshold = Number(
          this.shadowRoot.querySelector("#battery-threshold").value,
        );
      }
    }
    const config = await this._call(
      { type: "alert_manager/config/update", config: { automatic } },
      this._t("success.automatic_saved"),
    );
    if (config) {
      this._config = config;
      this._render();
    }
  }

  async _saveSettings() {
    this._ensureSettingsDraft();
    this._captureEntityDelayValues();
    const historyLimit = Number(this.shadowRoot.querySelector("#history-limit").value);
    if (!Number.isInteger(historyLimit) || historyLimit < 0 || historyLimit > 1000) {
      this._notice = { kind: "error", text: this._t("settings.history_limit_validation") };
      this._render();
      return;
    }
    const entityDelays = {};
    for (const row of this._entityDelayDraft) {
      if (!row.entity_id || !Number.isInteger(row.delay) || row.delay < 0) {
        this._notice = { kind: "error", text: this._t("settings.delay_validation") };
        this._render();
        return;
      }
      if (row.entity_id in entityDelays) {
        this._notice = {
          kind: "error",
          text: this._t("settings.duplicate_delay_save", { entity_id: row.entity_id }),
        };
        this._render();
        return;
      }
      entityDelays[row.entity_id] = row.delay;
    }
    const changes = {
      global_delay: Number(this.shadowRoot.querySelector("#global-delay").value),
      excluded_labels: [...this._settingsDraft.excluded_labels],
      excluded_entities: [...this._settingsDraft.excluded_entities],
      excluded_devices: [...this._settingsDraft.excluded_devices],
      entity_delays: entityDelays,
    };
    const historyChanged = historyLimit !== Number(this._historyConfig.retention_limit);
    this._busy = true;
    this._notice = null;
    this._render();
    try {
      const config = await this._hass.callWS({
        type: "alert_manager/config/update",
        config: changes,
      });
      this._config = config;
      if (historyChanged) {
        this._historyConfig = await this._hass.callWS({
          type: "alert_manager/history/config/update",
          retention_limit: historyLimit,
        });
        this._config = { ...this._config, history_limit: historyLimit };
        await this._refreshHistory();
      }
      this._resetSettingsDraft();
      this._notice = { kind: "success", text: this._t("success.settings_saved") };
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _saveRule(form) {
    const field = (name) =>
      form.querySelector?.(`[data-field="${name}"]`) ??
      form.elements?.namedItem(name) ??
      form.querySelector?.(`[name="${name}"]`);
    const value = (name) => field(name)?.value ?? "";
    const source = value("source");
    const operator = value("operator");
    const valueInputs = Array.from(form.querySelectorAll?.("[data-rule-value-index]") ?? []);
    const comparisonValue = TEXT_RULE_OPERATORS.has(operator)
      ? (valueInputs.length
        ? valueInputs.map((input) => String(input.value).trim())
        : this._ruleValueList(value("value")).map((item) => item.trim()))
      : String(value("value"));
    const rule = {
      name: String(value("name")).trim(),
      entity_ids: [...(this._editingRule?.entity_ids ?? [])],
      enabled: Boolean(this._editingRule?.enabled ?? true),
      source,
      attribute: source === "attribute" ? String(value("attribute")).trim() : null,
      operator,
      value: comparisonValue,
      duration: Number(value("duration")),
      message: String(value("message")).trim() || null,
    };
    const id = String(this._editingRule?.id ?? "");
    // _call renders a busy state. Keep the submitted values as the editor draft so
    // that render cannot clear the form, especially when the backend rejects it.
    this._editingRule = { ...rule, ...(id ? { id } : {}) };
    const message = id
      ? { type: "alert_manager/rules/update", rule_id: id, rule }
      : { type: "alert_manager/rules/create", rule };
    const updated = await this._call(
      message,
      this._t(id ? "success.rule_updated" : "success.rule_created"),
    );
    if (updated) {
      this._editingRule = null;
      this._ruleEditorMode = "visual";
      this._ruleDirty = false;
      this._replaceRule(updated);
    }
  }

  _captureRuleDraft() {
    const form = this.shadowRoot.querySelector?.("#rule-form");
    if (!form || this._editingRule === null) return;
    const field = (name) => form.querySelector?.(`[data-field="${name}"]`);
    const value = (name) => field(name)?.value;
    const valueInputs = Array.from(form.querySelectorAll?.("[data-rule-value-index]") ?? []);
    this._editingRule = {
      ...this._editingRule,
      name: String(value("name") ?? this._editingRule.name ?? ""),
      enabled: Boolean(this._editingRule.enabled ?? true),
      source: value("source") ?? this._editingRule.source ?? "state",
      attribute: String(value("attribute") ?? this._editingRule.attribute ?? ""),
      operator: value("operator") ?? this._editingRule.operator ?? "equals",
      value: valueInputs.length
        ? valueInputs.map((input) => String(input.value))
        : String(value("value") ?? this._editingRule.value ?? ""),
      duration: Number(value("duration") ?? this._editingRule.duration ?? 900),
      message: String(value("message") ?? this._editingRule.message ?? ""),
    };
  }

  _replaceRule(rule) {
    const index = this._config.rules.findIndex((item) => item.id === rule.id);
    if (index === -1) this._config.rules.push(rule);
    else this._config.rules[index] = rule;
    if (this._editingRule?.id === rule.id) {
      this._editingRule = { ...this._editingRule, enabled: rule.enabled };
    }
    this._render();
  }

  _resetSettingsDraft() {
    this._settingsDraft = null;
    this._entityDelayDraft = null;
  }

  _ensureSettingsDraft() {
    if (this._settingsDraft && this._entityDelayDraft) return;
    this._settingsDraft = {
      excluded_labels: [...(this._config.excluded_labels ?? [])],
      excluded_entities: [...(this._config.excluded_entities ?? [])],
      excluded_devices: [...(this._config.excluded_devices ?? [])],
    };
    this._entityDelayDraft = Object.entries(this._config.entity_delays ?? {}).map(
      ([entity_id, delay]) => ({ entity_id, delay }),
    );
  }

  _captureEntityDelayValues() {
    if (!this._entityDelayDraft) return;
    this.shadowRoot.querySelectorAll("[data-delay-index]").forEach((input) => {
      const row = this._entityDelayDraft[Number(input.dataset.delayIndex)];
      if (row) row.delay = Number(input.value);
    });
  }

  _setEntityDelayEntity(index, value) {
    if (!this._entityDelayDraft) return;
    const entityId = typeof value === "string" ? value : "";
    if (
      entityId
      && this._entityDelayDraft.some(
        (row, rowIndex) => rowIndex !== index && row.entity_id === entityId,
      )
    ) {
      this._notice = {
        kind: "error",
        text: this._t("settings.duplicate_delay", { entity_id: entityId }),
      };
      this._render();
      return;
    }
    this._entityDelayDraft[index].entity_id = entityId;
  }

  _date(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(this._language, {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(date);
  }

  _remaining(value) {
    const due = new Date(value).getTime();
    if (!Number.isFinite(due)) return "—";
    const seconds = Math.max(0, Math.ceil((due - Date.now()) / 1000));
    return seconds === 0 ? this._t("duration.activation") : this._durationText(seconds);
  }

  _durationText(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    if (value < 60) return this._t("duration.seconds", { count: value });
    if (value % 3600 === 0) {
      return this._t("duration.hours", { count: value / 3600 });
    }
    if (value % 60 === 0) {
      return this._t("duration.minutes", { count: value / 60 });
    }
    return this._t("duration.minutes_seconds", {
      minutes: Math.floor(value / 60),
      seconds: value % 60,
    });
  }

  _historyDurationText(seconds) {
    return this._durationText(Math.max(0, Math.round(Number(seconds) || 0)));
  }

  _conditionText(alert) {
    if (!alert?.condition_key) return alert?.condition ?? "";
    const params = { ...(alert.condition_params ?? {}) };
    if (alert.condition_key === "rule.generated") {
      const sourceKey = params.source === "attribute"
        ? "conditions.sources.attribute"
        : "conditions.sources.state";
      params.source = this._t(sourceKey, { attribute: params.attribute ?? "" });
      params.operator = this._t(`operators.${params.operator}`);
      params.unit = params.unit ? ` ${params.unit}` : "";
      params.duration = Number(params.duration)
        ? ` ${this._t("conditions.fragments.duration", {
          duration: this._durationText(params.duration),
        })}`
        : "";
    }
    return this._t(`conditions.${alert.condition_key}`, params);
  }

  _updateCountdowns() {
    if (!this._monitoringEnabled) return;
    const roots = [this.shadowRoot];
    this.shadowRoot?.querySelectorAll("ha-data-table").forEach((table) => {
      if (table.shadowRoot) roots.push(table.shadowRoot);
    });
    for (const root of roots) {
      root?.querySelectorAll("[data-due]").forEach((node) => {
        node.textContent = this._remaining(node.dataset.due);
      });
    }
  }

  _styles() {
    return `
      :host{display:block;height:100%;background:var(--primary-background-color,#fafafa);color:var(--primary-text-color,#212121);font-family:var(--ha-font-family-body,var(--paper-font-body1_-_font-family,Roboto,Noto,sans-serif));font-size:var(--ha-font-size-m,14px);line-height:var(--ha-line-height-normal,1.6)}
      *{box-sizing:border-box}main{max-width:1400px;margin:0 auto;padding:24px}h2{font-size:var(--ha-font-size-xl,20px);font-weight:var(--ha-font-weight-normal,400);line-height:var(--ha-line-height-condensed,1.4);margin:0 0 6px}p{margin:0;color:var(--secondary-text-color,#727272)}
      .summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:20px}.summary article,.panel{background:var(--card-background-color,#fff);border-radius:14px;box-shadow:var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.08));padding:20px}.summary article{display:flex;align-items:center;justify-content:space-between}.summary strong{font-size:30px}.danger{color:var(--error-color,#db4437)}.acknowledged{color:var(--blue-color,var(--primary-color,#03a9f4))}.pending{color:var(--warning-color,#f5a623)}
      .data-table-card{display:block;overflow:visible;background:var(--card-background-color,#fff)}
      .table-toolbar-wrap{position:relative}.table-toolbar{display:flex;align-items:center;gap:6px;min-height:56px;padding:8px 12px;border-bottom:1px solid var(--divider-color,#ddd)}.toolbar-spacer{flex:1}
      .toolbar-button,.toolbar-icon-button,.column-move{appearance:none;border:0;background:transparent;color:var(--primary-text-color,#212121);font:inherit;cursor:pointer}.toolbar-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:40px;padding:0 12px;border-radius:var(--ha-border-radius-m,8px);white-space:nowrap}.toolbar-icon-button{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;padding:0;border-radius:50%}.toolbar-button:hover,.toolbar-button.is-active,.toolbar-icon-button:hover,.column-move:hover{background:var(--ha-color-fill-neutral-quiet-hover,var(--secondary-background-color,#f5f5f5))}.toolbar-button:focus-visible,.toolbar-icon-button:focus-visible,.column-move:focus-visible{outline:var(--wa-focus-ring,2px solid var(--primary-color,#03a9f4));outline-offset:2px}.toolbar-button:disabled,.toolbar-icon-button:disabled,.column-move:disabled{cursor:default;opacity:.45}.toolbar-button ha-svg-icon,.toolbar-icon-button ha-svg-icon{width:21px;height:21px}.toolbar-button.primary{color:var(--primary-color,#03a9f4);font-weight:var(--ha-font-weight-medium,500)}.toolbar-button.danger{color:var(--error-color,#db4437);font-weight:var(--ha-font-weight-medium,500)}
      .filter-count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff);font-size:11px}
      .table-search{display:block;min-width:220px;max-width:420px;flex:1}
      .table-menu{position:absolute;z-index:4;top:57px;left:12px;right:12px;max-height:min(520px,70vh);overflow:auto;padding:16px;border:1px solid var(--divider-color,#ddd);border-radius:var(--ha-border-radius-l,12px);background:var(--card-background-color,#fff);box-shadow:var(--ha-card-box-shadow,0 4px 16px rgba(0,0,0,.22))}.table-menu fieldset{display:grid;gap:8px;margin:0;padding:0;border:0}.table-menu legend{margin-bottom:8px;font-weight:var(--ha-font-weight-medium,500)}.table-menu label{display:flex;flex-direction:column;gap:5px}.table-menu fieldset label{align-items:center;flex-direction:row}.table-menu select,.table-menu input[type="date"]{min-height:38px;padding:6px 9px;border:1px solid var(--divider-color,#ddd);border-radius:var(--ha-border-radius-m,8px);background:var(--card-background-color,#fff);color:var(--primary-text-color,#212121);font:inherit}
      .filter-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.filter-actions{display:flex;align-items:end}.menu-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
      .column-list{display:grid;gap:4px}.column-option{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:42px;padding:4px 6px;border-bottom:1px solid var(--divider-color,#ddd)}.column-option label{align-items:center;flex-direction:row;gap:9px}.column-option>span{display:flex}.column-move{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:50%}.column-move ha-svg-icon{width:19px;height:19px}
      .selection-toolbar{background:var(--ha-color-fill-primary-quiet-resting,color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff)))}.selection-count{margin-inline-start:6px}
      .native-alert-table{display:block;height:clamp(320px,62vh,780px);min-width:0;--data-table-row-height:52px}.table-footer{padding:8px 14px;color:var(--secondary-text-color,#727272);font-size:var(--ha-font-size-s,12px);text-align:right}
      .panel{margin-bottom:20px}.history-empty .empty h2{margin-bottom:8px}.history-empty .empty ha-button{margin-top:16px}.history-settings{display:grid;gap:8px;margin-top:4px}.history-settings-row{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"label ." "input action";align-items:center;gap:6px 16px}.history-limit-label{grid-area:label}#history-limit{grid-area:input}.history-actions{grid-area:action;align-self:start;min-height:56px;align-items:center;justify-content:flex-end;flex-wrap:nowrap}.history-limit-help{margin-top:0}.settings-save-actions{justify-content:flex-end;margin-top:4px}
      code{font-family:var(--ha-font-family-code,ui-monospace,SFMono-Regular,monospace);font-size:12px;word-break:break-all}
      .stack{display:grid;gap:16px}.automatic-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.automatic-grid .category-card{margin-bottom:0}.automatic-actions{grid-column:1/-1}.category-header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:16px}.category-header h2{margin:0}.category-header ha-switch{align-self:start}.category-card p{font-size:13px;margin-top:4px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:18px}.full{grid-column:1/-1;margin-top:16px}.field{display:flex;min-width:0;flex-direction:column;gap:6px}.field-label{font-size:var(--ha-font-size-m,14px);font-weight:var(--ha-font-weight-normal,400)}ha-input,ha-select,ha-selector{display:block;width:100%;font-weight:var(--ha-font-weight-normal,400)}ha-input{--ha-input-padding-bottom:0}ha-input>[slot="end"]{padding-inline-start:var(--ha-space-2,8px);color:var(--secondary-text-color,#727272);white-space:nowrap}.switch-field{display:flex;align-items:center;justify-content:space-between;min-height:56px;gap:16px}small{display:block;margin-top:8px;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400)}
      .actions{display:flex;justify-content:flex-end;gap:10px}.table-wrap{overflow:auto;margin-top:16px}table{border-collapse:collapse;width:100%;min-width:720px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--divider-color,#ddd);vertical-align:middle}th{font-size:12px;color:var(--secondary-text-color,#727272)}td code{display:block}.rule-row{cursor:pointer}.rule-row:hover{background:var(--ha-color-fill-neutral-quiet-hover,var(--secondary-background-color,#f5f5f5))}.rule-row:focus-visible{outline:var(--wa-focus-ring,2px solid var(--primary-color,#03a9f4));outline-offset:-2px}.rule-row.is-selected{background:var(--ha-color-fill-primary-quiet-resting,color-mix(in srgb,var(--primary-color,#03a9f4) 12%,transparent))}.rule-toggle-cell{text-align:right;width:72px}.rule-toggle-cell ha-switch{display:inline-block;vertical-align:middle}.new-rule-action{justify-content:flex-start;margin-top:16px}.rules-layout{--rule-editor-width:560px}.rules-layout.has-editor .rules-list-panel{margin-inline-end:calc(var(--rule-editor-width) + 8px)}ha-card.rule-editor-drawer{position:fixed;z-index:6;inset-block-start:calc(var(--header-height,56px) + 16px);inset-block-end:16px;inset-inline-end:max(24px,calc((85vw - 1400px)/2 + 24px));width:var(--rule-editor-width);max-width:calc(100vw - 64px);display:flex;flex-direction:column;overflow:visible;border-color:var(--primary-color,#03a9f4);border-width:2px;--ha-card-border-radius:var(--ha-dialog-border-radius,var(--ha-border-radius-2xl,14px))}.rule-editor-drawer ha-dialog-header{flex:none;background:var(--ha-dialog-surface-background,var(--card-background-color,#fff));border-radius:var(--ha-card-border-radius);border-end-start-radius:0;border-end-end-radius:0}.rule-menu-wrap{position:relative}.rule-editor-menu{position:absolute;z-index:10;inset-inline-end:0;inset-block-start:40px;min-width:190px;padding:4px;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#ddd);border-radius:var(--ha-border-radius-m,8px);box-shadow:var(--ha-card-box-shadow,0 3px 10px rgba(0,0,0,.2))}.rule-editor-menu ha-button{width:100%;justify-content:flex-start}.rule-editor-form{flex:1;min-height:0;overflow:auto;margin:0;padding:0;background:var(--primary-background-color,#fafafa)}.rule-editor-section{padding:20px;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#ddd)}.rule-section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.rule-section-heading h3{font-size:var(--ha-font-size-l,16px);font-weight:var(--ha-font-weight-medium,500);line-height:1.4;margin:0}.rule-section-heading small{display:block;margin-top:2px}.rule-editor-form .full{margin-top:0}.rule-name-field{margin-top:0}.rule-attribute-field[hidden]{display:none}.rule-values-field{gap:10px}.rule-value-list{display:grid;gap:10px}.rule-value-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:start}.rule-value-row ha-button{margin-top:8px}.rule-value-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}.rule-value-footer small{margin:0}.yaml-rule-section{min-height:0;display:flex;flex:1;flex-direction:column}.yaml-rule-section ha-code-editor{display:block;flex:1;min-height:360px;border:1px solid var(--divider-color,#ddd);border-radius:var(--ha-border-radius-m,8px);overflow:hidden}.yaml-error{margin-top:12px;padding:10px 12px;border-radius:var(--ha-border-radius-m,8px);background:color-mix(in srgb,var(--error-color,#db4437) 14%,transparent);color:var(--error-color,#db4437);overflow-wrap:anywhere}.rule-editor-actions{position:sticky;bottom:0;z-index:1;align-items:center;justify-content:flex-start;padding:12px 20px max(12px,var(--safe-area-inset-bottom,0px));background:var(--card-background-color,#fff);border-top:1px solid var(--divider-color,#ddd);box-shadow:0 -2px 8px rgba(0,0,0,.08)}.action-spacer{flex:1}.rule-editor-resize{position:absolute;inset-block:var(--ha-card-border-radius) var(--ha-card-border-radius);inset-inline-start:-12px;width:24px;z-index:7;cursor:ew-resize;display:flex;align-items:center;justify-content:center;touch-action:none}.resize-indicator{height:100%;width:4px;border-radius:var(--ha-border-radius-pill,999px);background:var(--primary-color,#03a9f4);opacity:0;transform:scaleX(0);transition:opacity 180ms ease-in-out,transform 180ms ease-in-out}.rule-editor-resize:hover .resize-indicator,.rule-editor-resize:focus-visible .resize-indicator,.rule-editor-resize.is-resizing .resize-indicator{opacity:1;transform:scaleX(1)}.rule-editor-resize:focus-visible{outline:none}.rule-editor-backdrop{display:none}.delay-list{display:grid;gap:10px;margin-top:16px}.delay-add-action{justify-content:flex-start;margin-top:16px}.delay-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,260px) auto;gap:10px;align-items:start}.delay-row ha-input{min-width:0}.delay-row>ha-button{margin-top:8px}.configuration-transfer{display:grid;gap:16px}.transfer-actions{justify-content:flex-start}
      .empty,.loading{padding:40px;text-align:center;color:var(--secondary-text-color,#727272)}.empty.compact{padding:20px}.monitoring-warning{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 16px;border-radius:8px;margin-bottom:16px;background:color-mix(in srgb,var(--warning-color,#f5a623) 16%,transparent);color:var(--primary-text-color,#212121)}.monitoring-warning ha-button{flex:none}.notice{padding:12px 16px;border-radius:8px;margin-bottom:16px}.notice.success{background:color-mix(in srgb,var(--success-color,#43a047) 15%,transparent);color:var(--success-color,#2e7d32)}.notice.error{background:color-mix(in srgb,var(--error-color,#db4437) 15%,transparent);color:var(--error-color,#db4437)}
      @media(max-width:1000px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.rules-layout.has-editor .rules-list-panel{margin-inline-end:0}.rule-editor-backdrop{display:block;position:fixed;z-index:5;inset:var(--header-height,56px) 0 0;background:rgba(0,0,0,.32)}}
      @media(max-width:850px){.table-toolbar{flex-wrap:wrap}.table-search{order:10;max-width:none;min-width:100%;flex-basis:100%}.filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.table-menu{top:105px}.selection-toolbar .toolbar-spacer{display:none}.selection-toolbar{align-items:stretch}.selection-toolbar .toolbar-button{flex:1}.native-alert-table{height:calc(100vh - 250px);min-height:360px}}
      @media(max-width:700px){main{padding:12px}.summary,.automatic-grid{grid-template-columns:1fr}.summary article{padding:14px}.monitoring-warning{align-items:stretch;flex-direction:column}.monitoring-warning ha-button{width:100%}.fields{grid-template-columns:1fr}.panel{padding:15px}.actions ha-button{width:100%}.history-settings-row{grid-template-columns:1fr;grid-template-areas:"label" "input" "action"}.history-actions{align-self:auto;align-items:center;justify-content:flex-start}.delay-row{grid-template-columns:1fr}.delay-row ha-button{width:100%}ha-card.rule-editor-drawer{inset-block-start:var(--header-height,56px);inset-block-end:calc(var(--header-height,56px) + var(--safe-area-inset-bottom,0px));inset-inline-end:0;width:100%;max-width:none;border-width:0;overflow:hidden;--ha-card-border-radius:var(--ha-border-radius-square,0)}.rule-editor-resize{display:none}.rule-section-heading,.rule-value-footer{align-items:stretch;flex-direction:column}.rule-value-row{grid-template-columns:1fr}.rule-value-row ha-button{margin-top:0}.rule-editor-actions{flex-wrap:wrap}.rule-editor-actions .action-spacer{display:none}}
      @media(max-width:700px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.summary article{padding:12px}.summary strong{font-size:24px}}
      @media(max-width:560px){.toolbar-button span:not(.filter-count){display:none}.table-toolbar>.toolbar-button{width:40px;padding:0}.filter-grid,.menu-fields{grid-template-columns:1fr}.table-menu{left:6px;right:6px}.selection-toolbar .toolbar-button span{display:initial}.selection-count{width:100%;order:8;margin:0}.selection-toolbar .toolbar-spacer{display:none}}
    `;
  }
}

if (!customElements.get("alert-manager-panel")) {
  customElements.define("alert-manager-panel", AlertManagerPanel);
}

export { AlertManagerPanel, makeTableState, lines, newRuleDefaults };
