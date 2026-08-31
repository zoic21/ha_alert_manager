import { MDI_DOWNLOAD } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";

export function renderConfigBackups(context) {
  const { backups, busy, date, t } = context;
  return `<section class="config-backups" data-config-backups>
    <div><h3>${esc(t("recovery.backups_title"))}</h3><small>${esc(t("recovery.backups_help"))}</small></div>
    <div class="config-backup-list">${backups.length ? backups.map((backup) => `
      <div class="config-backup-row" data-backup-id="${esc(backup.id)}">
        <div class="config-backup-details"><strong>${esc(date(backup.created_at))}</strong><span>${esc(t("recovery.rule_count", { count: backup.rules }))}</span></div>
        <div class="actions config-backup-actions">
          <ha-button type="button" appearance="plain" data-action="download-config-backup" data-backup-id="${esc(backup.id)}" ${busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_DOWNLOAD}"></ha-svg-icon>${esc(t("recovery.download"))}</ha-button>
          <ha-button type="button" appearance="plain" variant="danger" data-action="restore-config-backup" data-backup-id="${esc(backup.id)}" ${busy ? "disabled" : ""}>${esc(t("recovery.restore"))}</ha-button>
        </div>
      </div>`).join("") : `<div class="empty compact">${esc(t("recovery.no_backups"))}</div>`}</div>
  </section>`;
}

export function renderRecoveryBanner(context) {
  const {
    active, failedConfigAvailable, backupsMarkup, busy, t,
  } = context;
  if (!active) return "";
  return `<section class="recovery-panel" data-config-recovery>
    <ha-alert class="page-alert recovery-alert" alert-type="error">
      <strong>${esc(t("recovery.banner_title"))}</strong>
      <span>${esc(t("recovery.banner_message"))}</span>
    </ha-alert>
    ${failedConfigAvailable ? `<div class="actions recovery-diagnostic-action"><ha-button type="button" appearance="plain" data-action="download-failed-config" ${busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_DOWNLOAD}"></ha-svg-icon>${esc(t("recovery.download_failed"))}</ha-button></div>` : ""}
    <ha-card outlined class="panel recovery-backups-card">${backupsMarkup}</ha-card>
  </section>`;
}

export function renderBackupRestoreDialog(context) {
  const { backup, busy, date, t } = context;
  if (!backup) return "";
  return `<ha-dialog id="config-backup-restore-dialog">
    <ha-dialog-header>${esc(t("recovery.confirm_title"))}</ha-dialog-header>
    <div class="config-backup-confirmation">${esc(t("recovery.confirm_message", {
      date: date(backup.created_at),
      rules: backup.rules,
    }))}</div>
    <ha-button type="button" slot="secondaryAction" appearance="plain" data-action="cancel-config-backup-restore" ${busy ? "disabled" : ""}>${esc(t("buttons.cancel"))}</ha-button>
    <ha-button type="button" slot="primaryAction" appearance="accent" variant="danger" data-action="confirm-config-backup-restore" data-backup-id="${esc(backup.id)}" ${busy ? "disabled" : ""}>${esc(t("recovery.restore"))}</ha-button>
  </ha-dialog>`;
}

export function renderBackupRestoreDialogPanel() {
  return renderBackupRestoreDialog({
    backup: this._backupRestoreCandidate,
    busy: this._busy,
    date: (value) => this._date(value),
    t: (key, replacements) => this._t(key, replacements),
  });
}

export function downloadTextPayload(payload) {
  if (!payload?.content || !payload?.filename) return false;
  const blob = new Blob(
    [payload.content],
    { type: payload.content_type || "text/plain;charset=utf-8" },
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = payload.filename;
  link.click();
  URL.revokeObjectURL(url);
  return true;
}

export async function applyCompleteConfiguration(result) {
  if (!result?.config) return false;
  this._config = result.config;
  this._monitoringEnabled = this._config.monitoring_enabled !== false;
  this._resetSettingsDraft();
  this._resetAutomaticDraft();
  this._editingRule = null;
  this._ruleEditorMode = "visual";
  this._ruleDirty = false;
  const [alerts, history, recovery] = await Promise.all([
    this._api.call({ type: "alert_manager/alerts/list" }).catch(() => null),
    this._api.call({ type: "alert_manager/history/list" }).catch(() => null),
    this._api.call({ type: "alert_manager/config/recovery/get" }).catch(() => null),
  ]);
  if (alerts) this._alerts = alerts;
  if (history) this._history = history;
  if (recovery) this._configRecovery = recovery;
  this._syncSensor();
  this._render();
  return true;
}

export function hydrateConfigBackups() {
  const dialog = this.shadowRoot?.querySelector?.("#config-backup-restore-dialog");
  if (!dialog || dialog.dataset.configured) return;
  dialog.dataset.configured = "true";
  dialog.hass = this._hass;
  dialog.scrimClickAction = "close";
  dialog.escapeKeyAction = "close";
  dialog.addEventListener("closed", () => {
    if (!this._backupRestoreCandidate) return;
    this._backupRestoreCandidate = null;
    this._render();
  });
  dialog.open = true;
}

export async function handleConfigBackupAction(action, button) {
  if (action === "download-config-backup") {
    const payload = await this._call(
      {
        type: "alert_manager/config/backups/download",
        backup_id: button.dataset.backupId,
      },
      this._t("success.backup_downloaded"),
    );
    downloadTextPayload(payload);
    return true;
  }
  if (action === "download-failed-config") {
    const payload = await this._call(
      { type: "alert_manager/config/recovery/failed/download" },
      this._t("success.failed_config_downloaded"),
    );
    downloadTextPayload(payload);
    return true;
  }
  if (action === "restore-config-backup") {
    this._backupRestoreCandidate = (this._configRecovery?.backups ?? []).find(
      (backup) => backup.id === button.dataset.backupId,
    ) ?? null;
    this._render();
    return true;
  }
  if (action === "cancel-config-backup-restore") {
    this._backupRestoreCandidate = null;
    this._render();
    return true;
  }
  if (action === "confirm-config-backup-restore") {
    const backupId = button.dataset.backupId;
    const result = await this._call(
      {
        type: "alert_manager/config/backups/restore",
        backup_id: backupId,
        confirmed: true,
      },
      this._t("success.backup_restored"),
    );
    this._backupRestoreCandidate = null;
    if (result) await this._applyCompleteConfiguration(result);
    else this._render();
    return true;
  }
  return false;
}
