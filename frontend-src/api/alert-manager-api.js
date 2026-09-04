export class AlertManagerApi {
  constructor(getHass) {
    this._getHass = getHass;
  }

  call(message) {
    return this._getHass().callWS(message);
  }

  testRule(rule, ruleId = "") {
    return this.call({
      type: "alert_manager/rules/test",
      rule,
      ...(ruleId ? { rule_id: ruleId } : {}),
    });
  }
}

const PANEL_STATE_CACHE = new WeakMap();

function panelStateCacheKey(hass) {
  const key = hass?.connection ?? hass;
  return key && (typeof key === "object" || typeof key === "function") ? key : null;
}

export function rememberPanelState() {
    const key = panelStateCacheKey(this._hass);
    if (!key || !this._config) return;
    PANEL_STATE_CACHE.set(key, {
      language: this._language,
      translations: this._translations,
      englishTranslations: this._englishTranslations,
      config: this._config,
      alerts: this._alerts,
      packs: this._packs,
      historyConfig: this._historyConfig,
      configRecovery: this._configRecovery,
      notificationStats: this._notificationStats,
      labels: this._labels,
      monitoringEnabled: this._monitoringEnabled,
    });
}

export function restorePanelState() {
    const key = panelStateCacheKey(this._hass);
    const cached = key ? PANEL_STATE_CACHE.get(key) : null;
    if (!cached || cached.language !== this._language) return false;
    this._translations = cached.translations;
    this._englishTranslations = cached.englishTranslations;
    this._config = cached.config;
    this._alerts = cached.alerts;
    this._packs = cached.packs;
    this._historyConfig = cached.historyConfig;
    this._configRecovery = cached.configRecovery;
    this._notificationStats = cached.notificationStats ?? { last_24h: {} };
    this._labels = cached.labels;
    this._monitoringEnabled = cached.monitoringEnabled;
    this._loading = false;
    this._cachedStateNeedsRefresh = true;
    return true;
}

export function setHass(value) {
    const language = value?.locale?.language || "en";
    const languageChanged = language !== this._language;
    const scannedAt = value?.states?.["sensor.alert_manager_coherence_issue"]
      ?.attributes?.scanned_at ?? null;
    const coherenceChanged = Boolean(
      scannedAt && scannedAt !== this._coherenceScannedAt,
    );
    this._coherenceScannedAt = scannedAt;
    this._hass = value;
    this._language = language;
    if (!this._config) this._restorePanelState();
    const alertsChanged = this._syncSensor();
    if (this.isConnected && this._config && this._coherenceLoaded && coherenceChanged) {
      void this._refreshCoherence();
    }
    if (
      this.isConnected
      && (!this._config || this._cachedStateNeedsRefresh)
      && !this._loadPromise
    ) {
      this._load();
    } else if (this.isConnected && languageChanged && !this._translationPromise) {
      this._reloadTranslations();
    } else if (this.isConnected && this._activeTab === "overview" && alertsChanged) {
      this._refreshOverviewData();
      void this._refreshAlerts();
    } else if (this.isConnected && this._activeTab === "history" && alertsChanged) {
      this._refreshHistory();
    } else if (this.isConnected) {
      this._hydrateSelectors();
    }
}

export function refreshTabData(tab) {
    if (!this._hass || !this._config) return;
    if (tab === "history") {
      void this._refreshHistory();
    } else if (tab === "coherence") {
      void this._refreshCoherence();
    } else if (tab === "settings" && !this._loadPromise) {
      void this._refreshNotificationStats();
    } else if (tab === "overview" && !this._loadPromise) {
      void this._refreshAlerts();
    }
}

export async function load() {
    const initialLoad = !this._config;
    this._cachedStateNeedsRefresh = false;
    this._loadPromise = Promise.all([
      this._api.call({ type: "alert_manager/config/get" }),
      this._api.call({ type: "alert_manager/alerts/list" }),
      this._api.call({ type: "alert_manager/packs/list" }),
      this._api.call({ type: "alert_manager/history/config/get" }),
      this._api.call({ type: "alert_manager/config/recovery/get" }),
      this._api.call({ type: "alert_manager/notifications/stats/get" }),
      this._api.call({ type: "config/label_registry/list" }).catch(() => []),
      this._fetchTranslations(this._language),
    ]);
    if (initialLoad) {
      this._loading = true;
      this._render();
    }
    try {
      [
        this._config,
        this._alerts,
        this._packs,
        this._historyConfig,
        this._configRecovery,
        this._notificationStats,
        this._labels,
      ] = await this._loadPromise;
      this._notificationStats ??= { last_24h: {} };
      this._monitoringEnabled = this._config.monitoring_enabled !== false;
      this._resetSettingsDraft();
      this._resetAutomaticDraft();
      this._syncSensor();
      this._notice = null;
      this._rememberPanelState();
      if (["history", "coherence"].includes(this._activeTab)) {
        this._refreshTabData(this._activeTab);
      }
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._loading = false;
      this._loadPromise = null;
      if (initialLoad) {
        this._render();
      } else if (this._activeTab === "overview") {
        this._refreshOverviewData();
      } else if (this._activeTab === "rules") {
        this._refreshRulesData();
      } else {
        this._refreshUiState();
        if (this._activeTab === "settings") this._refreshNotificationProfileUsage();
        this._hydrateSelectors();
      }
      this._openAlertDeepLink();
    }
}

export async function refreshHistory() {
    if (!this._hass || this._historyLoadPromise) return this._historyLoadPromise;
    this._historyLoadPromise = this._api.call({ type: "alert_manager/history/list" });
    try {
      this._history = await this._historyLoadPromise;
      this._historyLoaded = true;
    } catch (error) {
      this._historyLoaded = true;
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._historyLoadPromise = null;
      if (this.isConnected) this._refreshHistoryData();
    }
    return this._history;
}

export async function refreshCoherence() {
    if (!this._hass || this._coherenceLoadPromise) return this._coherenceLoadPromise;
    this._coherenceLoadPromise = this._api.call({
      type: "alert_manager/coherence/get",
    });
    try {
      this._coherence = await this._coherenceLoadPromise;
      this._coherenceLoaded = true;
      this._coherenceScannedAt = this._coherence?.scanned_at ?? this._coherenceScannedAt;
    } catch (error) {
      this._coherenceLoaded = true;
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._coherenceLoadPromise = null;
      if (this.isConnected && this._activeTab === "coherence") this._refreshCoherenceData();
    }
    return this._coherence;
}

export async function refreshNotificationStats() {
    if (!this._hass || this._notificationStatsLoadPromise) {
      return this._notificationStatsLoadPromise;
    }
    this._notificationStatsLoadPromise = this._api.call({
      type: "alert_manager/notifications/stats/get",
    });
    try {
      this._notificationStats = await this._notificationStatsLoadPromise
        ?? { last_24h: {} };
      this._rememberPanelState();
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._notificationStatsLoadPromise = null;
      if (this.isConnected && this._activeTab === "settings") {
        this._refreshNotificationProfileUsage();
      }
    }
    return this._notificationStats;
}

export async function refreshAlerts() {
    if (!this._hass || !this._config) return this._alerts;
    if (this._alertsRefreshPromise) {
      this._alertsRefreshRequested = true;
      return this._alertsRefreshPromise;
    }
    this._alertsRefreshPromise = this._api.call({
      type: "alert_manager/alerts/list",
    });
    try {
      this._alerts = await this._alertsRefreshPromise;
      this._rememberPanelState();
      this._openAlertDeepLink();
      if (this.isConnected && this._activeTab === "overview") {
        this._refreshOverviewData();
      }
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._alertsRefreshPromise = null;
      if (this._alertsRefreshRequested) {
        this._alertsRefreshRequested = false;
        void this._refreshAlerts();
      }
    }
    return this._alerts;
}

export async function call(message, successText) {
    this._busy = true;
    this._notice = null;
    this._refreshUiState();
    try {
      const result = await this._api.call(message);
      this._notice = successText ? { kind: "success", text: successText } : null;
      return result;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
      return null;
    } finally {
      this._busy = false;
      this._refreshUiState();
    }
}
