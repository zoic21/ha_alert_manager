export class AlertManagerApi {
  constructor(getHass) {
    this._getHass = getHass;
  }

  call(message) {
    return this._getHass().callWS(message);
  }
}

export async function load() {
    this._loadPromise = Promise.all([
      this._api.call({ type: "alert_manager/config/get" }),
      this._api.call({ type: "alert_manager/alerts/list" }),
      this._api.call({ type: "alert_manager/packs/list" }),
      this._api.call({ type: "alert_manager/history/list" }),
      this._api.call({ type: "alert_manager/history/config/get" }),
      this._api.call({ type: "alert_manager/coherence/get" }),
      this._api.call({ type: "alert_manager/config/recovery/get" }),
      this._api.call({ type: "config/label_registry/list" }).catch(() => []),
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
        this._coherence,
        this._configRecovery,
        this._labels,
      ] = await this._loadPromise;
      this._monitoringEnabled = this._config.monitoring_enabled !== false;
      this._coherenceScannedAt = this._coherence?.scanned_at ?? this._coherenceScannedAt;
      this._resetSettingsDraft();
      this._resetAutomaticDraft();
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

export async function refreshHistory() {
    if (!this._hass || this._historyLoadPromise) return this._historyLoadPromise;
    this._historyLoadPromise = this._api.call({ type: "alert_manager/history/list" });
    try {
      this._history = await this._historyLoadPromise;
    } catch (error) {
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
      this._coherenceScannedAt = this._coherence?.scanned_at ?? this._coherenceScannedAt;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._coherenceLoadPromise = null;
      if (this.isConnected && this._activeTab === "coherence") this._refreshCoherenceData();
    }
    return this._coherence;
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
