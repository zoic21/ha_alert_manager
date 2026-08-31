import { esc } from "../utils/escaping.js";

export function refreshOverviewData() {
    const tablePage = this.shadowRoot?.querySelector('[data-alert-table-page="overview"]');
    if (!tablePage) {
      this._render();
      return;
    }
    const counts = {
      active: this._alerts.active_count,
      pending: this._alerts.pending_count,
      acknowledged: this._alerts.acknowledge_count ?? this._alerts.acknowledge?.length ?? 0,
      tracked: this._alerts.tracked_count ?? 0,
    };
    for (const [key, count] of Object.entries(counts)) {
      const value = tablePage.querySelector?.(`[data-summary="${key}"] strong`);
      if (value) value.textContent = String(count);
    }
    this._refreshAlertTableData("overview", tablePage);
    this._updateCountdowns();
}

export function renderOverview() {
    const selectedStatuses = this._filterValues(this._tableState.overview.filters.status);
    const selected = (status) => selectedStatuses.length === 1 && selectedStatuses[0] === status;
    const summary = `${this._renderPageMessages()}
      <section class="summary">
        <ha-card outlined data-summary="active" data-action="filter-summary-status" data-status="active" tabindex="0" role="button" aria-pressed="${selected("active")}"><span>${esc(this._t("overview.summary_active"))}</span><strong class="danger">${this._alerts.active_count}</strong></ha-card>
        <ha-card outlined data-summary="pending" data-action="filter-summary-status" data-status="pending" tabindex="0" role="button" aria-pressed="${selected("pending")}"><span>${esc(this._t("overview.summary_pending"))}</span><strong class="pending">${this._alerts.pending_count}</strong></ha-card>
        <ha-card outlined data-summary="acknowledged" data-action="filter-summary-status" data-status="acknowledged" tabindex="0" role="button" aria-pressed="${selected("acknowledged")}"><span>${esc(this._t("overview.summary_acknowledged"))}</span><strong class="acknowledged">${this._alerts.acknowledge_count ?? this._alerts.acknowledge?.length ?? 0}</strong></ha-card>
        <ha-card outlined data-summary="tracked"><span>${esc(this._t("overview.summary_tracked"))}</span><strong>${this._alerts.tracked_count ?? 0}</strong></ha-card>
      </section>`;
    return this._renderAlertTable("overview", this._tableRows("overview"), summary);
}

export async function bulkAlertAction(service) {
    if (this._busy) return;
    const compatibleStatus = service === "acknowledge" ? "active" : "acknowledged";
    const rows = this._tableRows("overview").filter((row) => (
      this._selectedAlertIds.has(row.id) && row.status === compatibleStatus
    ));
    if (!rows.length) return;
    this._busy = true;
    this._notice = null;
    this._refreshUiState();
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
    this._refreshOverviewData();
    this._updateSelectionToolbar();
    this._refreshUiState();
}

export function applyOptimisticAcknowledgement(alertId, acknowledged) {
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

export async function handleOverviewAction(action, button) {
  if (action === "bulk-acknowledge" || action === "bulk-unacknowledge") {
    await this._bulkAlertAction(action === "bulk-acknowledge" ? "acknowledge" : "unacknowledge");
    return true;
  }
  if (action === "filter-summary-status") {
    const status = button.dataset.status;
    if (!["active", "pending", "acknowledged"].includes(status)) return true;
    const selectedStatuses = this._filterValues(this._tableState.overview.filters.status);
    this._tableState.overview.filters.status = selectedStatuses.length === 1
      && selectedStatuses[0] === status
      ? []
      : [status];
    this._render();
    return true;
  }
  if (action === "enable-monitoring") {
    if (this._busy) return true;
    this._busy = true;
    this._refreshUiState();
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
      this._refreshUiState();
    }
    return true;
  }
  return false;
}
