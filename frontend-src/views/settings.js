import { collectAutomaticChanges } from "./automatic.js";
import {
  ALERT_MANAGER_ENTITY_IDS,
  MAX_DURATION_SECONDS,
  MDI_DOWNLOAD,
  MDI_PLUS,
  MDI_UPLOAD,
} from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { downloadTextPayload } from "../components/config-backups.js";
import {
  renderConfigurationDrawer,
  replaceConfigurationDrawer,
} from "../components/configuration-drawer.js";
import {
  cloneNotificationProfile,
  hydrateNotificationProfileControls,
  renderNotificationProfileDrawer,
  renderNotificationProfiles,
  updateNotificationProfileUsage,
} from "../components/notification-profiles.js";

const SETTINGS_SECTIONS = [
  ["automatic", "tabs.automatic", "mdi:radar"],
  ["alert-display", "settings.alert_display", "mdi:alert-outline"],
  ["coherence", "settings.coherence_settings", "mdi:check-decagram-outline"],
  ["exclusions", "settings.exclusions", "mdi:shield-off-outline"],
  ["notifications", "notifications.title", "mdi:bell-outline"],
  ["history", "settings.history_settings", "mdi:history"],
  ["entity-delay", "settings.entity_delay", "mdi:timer-cog-outline"],
  ["transfer", "settings.transfer_title", "mdi:file-swap-outline"],
];

export function renderSettings(context) {
    const {
      config, settingsDraft, historyConfig, entityDelayDraft,
      ignoredReferenceDraft, configurationDrawer, notificationProfileDraft,
      notificationProfileValidationError,
      notificationUsage = {},
      busy, useBottomSheet,
      recoveryActive = false, configBackupsMarkup = "",
      automaticMarkup = "",
      configurationDirty = false,
      renderNumberField, t,
    } = context;
    const ignoredReferences = settingsDraft.coherence_ignored_entity_references;
    return `<div class="stack settings-page">
      ${renderSettingsNavigation(t)}
      ${automaticMarkup}
      <form id="settings-form" class="stack settings-form">
      <ha-card id="settings-section-alert-display" outlined class="panel settings-card settings-scroll-section"><h2>${esc(t("settings.alert_display"))}</h2><div class="settings-grid">
        ${renderNumberField("global-delay", t("settings.global_delay"), settingsDraft.global_delay ?? config.global_delay, t("units.seconds"), 0, MAX_DURATION_SECONDS, { help: t("settings.global_delay_help") })}
        ${renderNumberField("pending-display-delay", t("settings.pending_display_delay"), settingsDraft.pending_display_delay ?? config.pending_display_delay, t("units.seconds"), 0, MAX_DURATION_SECONDS, { help: t("settings.pending_display_delay_help") })}
      </div></ha-card>
      <ha-card id="settings-section-coherence" outlined class="panel settings-card settings-scroll-section"><h2>${esc(t("settings.coherence_settings"))}</h2><div class="settings-grid">
        <div class="field"><span class="field-label">${esc(t("settings.coherence_schedule"))}</span><ha-select id="coherence-schedule"></ha-select><small>${esc(t("settings.coherence_schedule_help"))}</small></div>
        <div class="field"><div class="switch-field-row"><span class="field-label">${esc(t("settings.coherence_scan_esphome"))}</span><ha-switch id="coherence-scan-esphome" aria-label="${esc(t("settings.coherence_scan_esphome"))}" ${settingsDraft.coherence_scan_esphome ? "checked" : ""}></ha-switch></div><small>${esc(t("settings.coherence_scan_esphome_help"))}</small></div>
        <div class="field settings-wide ignored-references-field"><span class="field-label">${esc(t("settings.coherence_ignored_entity_references"))}</span>
          ${ignoredReferences.length ? `<ha-chip-set class="ignored-reference-chips">${ignoredReferences.map((reference) => `<ha-input-chip selected label="${esc(reference)}" data-ignored-reference="${esc(reference)}">${esc(reference)}</ha-input-chip>`).join("")}</ha-chip-set>` : ""}
          <div class="ignored-reference-add"><ha-input id="ignored-reference-input" type="text" value="${esc(ignoredReferenceDraft)}" placeholder="${esc(t("settings.coherence_ignored_entity_reference_placeholder"))}" aria-label="${esc(t("settings.coherence_ignored_entity_reference_placeholder"))}"></ha-input><ha-button type="button" appearance="plain" data-action="add-ignored-reference"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button></div>
          <small>${esc(t("settings.coherence_ignored_entity_references_help"))}</small>
        </div>
      </div></ha-card>
      <ha-card id="settings-section-exclusions" outlined class="panel settings-card settings-scroll-section"><h2>${esc(t("settings.exclusions"))}</h2><div class="settings-grid">
        <div class="field settings-wide"><span class="field-label">${esc(t("settings.label_exclusions"))}</span><ha-selector id="excluded-labels"></ha-selector><small>${esc(t("settings.labels_help"))}</small></div>
        <div class="settings-wide settings-configuration-actions">
          ${renderSettingsConfigurationEntry("excluded_entities", t("settings.entity_exclusions"), (settingsDraft.excluded_entities ?? []).length, t)}
          ${renderSettingsConfigurationEntry("excluded_devices", t("settings.device_exclusions"), (settingsDraft.excluded_devices ?? []).length, t)}
        </div>
      </div></ha-card>
      ${renderNotificationProfiles({
        profiles: settingsDraft.notification_profiles ?? [],
        batchDelayField: renderNumberField("notification-batch-delay", t("notifications.batch_delay"), settingsDraft.notification_batch_delay ?? config.notification_batch_delay ?? 30, t("units.seconds"), 10, 300, { help: t("notifications.batch_delay_help") }),
        usage: notificationUsage,
        busy,
        t,
      })}
      <ha-card id="settings-section-history" outlined class="panel settings-card settings-scroll-section"><h2>${esc(t("settings.history_settings"))}</h2>
        <div class="history-settings">
          <div class="history-settings-row">
            <span class="field-label history-limit-label">${esc(t("settings.history_limit"))}</span>
            <ha-input id="history-limit" type="number" min="0" max="1000" step="1" value="${esc(settingsDraft.history_limit ?? historyConfig.retention_limit)}" required aria-label="${esc(t("settings.history_limit"))}"><span slot="end">${esc(t("units.events"))}</span></ha-input>
          </div>
          <small class="history-limit-help">${esc(t("settings.history_limit_help"))}</small>
        </div>
      </ha-card>
      <ha-card id="settings-section-entity-delay" outlined class="panel settings-card settings-scroll-section"><div><h2>${esc(t("settings.entity_delay"))}</h2><small>${esc(t("settings.delay_help"))}</small></div>
        ${renderSettingsConfigurationEntry("entity_delays", t("settings.entity_delay"), entityDelayDraft.length, t)}
      </ha-card>
      <ha-card id="settings-section-transfer" outlined class="panel configuration-transfer settings-scroll-section"><div><h2>${esc(t("settings.transfer_title"))}</h2><small>${esc(t("settings.transfer_help"))}</small></div>
        <div class="actions transfer-actions"><ha-button type="button" appearance="plain" data-action="export-config" ${busy || recoveryActive ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_DOWNLOAD}"></ha-svg-icon>${esc(t("settings.export"))}</ha-button><ha-button type="button" appearance="accent" variant="brand" data-action="choose-config-import" ${busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_UPLOAD}"></ha-svg-icon>${esc(t("settings.import"))}</ha-button></div>
        <input id="config-import-file" data-import-file type="file" accept=".yaml,.yml,text/yaml,application/x-yaml" hidden>
        ${configBackupsMarkup}
      </ha-card>
      ${renderSettingsConfigurationDrawer({
        settingsDraft, entityDelayDraft, configurationDrawer,
        notificationProfileDraft, notificationProfileValidationError,
        busy, useBottomSheet, t,
      })}
      </form>
      <div class="settings-fab-positioner"><ha-button type="button" slot="fab" size="l" class="${configurationDirty ? "dirty" : ""}" appearance="accent" variant="brand" data-action="save-configuration" ${busy || recoveryActive ? "disabled" : ""}>${esc(t("settings.save"))}</ha-button></div>
    </div>`;
}

export function renderSettingsNavigation(t) {
  return `<ha-card outlined class="panel settings-navigation"><h2>${esc(t("settings.quick_access"))}</h2><div class="settings-navigation-actions">${SETTINGS_SECTIONS.map(([id, key, icon]) => `<ha-button type="button" appearance="outlined" data-action="scroll-settings-section" data-section-id="${id}"><ha-icon slot="start" icon="${icon}"></ha-icon>${esc(t(key))}</ha-button>`).join("")}</div></ha-card>`;
}

export function renderSettingsConfigurationEntry(id, label, count, t) {
  return `<div class="configuration-entry settings-configuration-entry"><ha-button type="button" id="settings-${id}-configuration" appearance="plain" data-action="open-settings-configuration" data-configuration-id="${esc(id)}" data-configuration-label="${esc(label)}" aria-label="${esc(t("settings.configure_aria", { name: label }))}">${esc(t("buttons.configuration_named", { name: label, count }))}</ha-button></div>`;
}

export function renderSettingsConfigurationDrawer(context) {
  const {
    settingsDraft, entityDelayDraft, configurationDrawer,
    notificationProfileDraft, busy, useBottomSheet, t,
  } = context;
  if (configurationDrawer?.kind === "notification") {
    return renderNotificationProfileDrawer({
      draft: notificationProfileDraft,
      busy,
      useBottomSheet,
      validationError: context.notificationProfileValidationError,
      t,
    });
  }
  if (configurationDrawer?.kind !== "settings") return "";
  const id = configurationDrawer.id;
  let title;
  let content;
  if (id === "entity_delays") {
    title = t("settings.entity_delay");
    content = `<div class="configuration-section-heading">
        <small>${esc(t("settings.delay_help"))}</small>
        <ha-button type="button" appearance="plain" data-action="add-entity-delay"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button>
      </div>
      <div class="delay-list">${entityDelayDraft.length ? entityDelayDraft.map((row, index) => `<div class="delay-row">
        <ha-selector id="delay-entity-${index}"></ha-selector>
        <ha-input data-delay-index="${index}" type="number" min="0" max="${MAX_DURATION_SECONDS}" step="1" value="${esc(row.delay)}" required aria-label="${esc(t("settings.aria_delay"))}"><span slot="end">${esc(t("units.seconds"))}</span></ha-input>
        <ha-button type="button" appearance="plain" variant="danger" data-action="remove-entity-delay" data-index="${index}" aria-label="${esc(t("settings.aria_remove_delay"))}">${esc(t("buttons.delete"))}</ha-button>
      </div>`).join("") : `<div class="empty compact">${esc(t("settings.no_delay"))}</div>`}</div>`;
  } else if (id === "excluded_entities") {
    title = t("settings.entity_exclusions");
    content = `<div class="field"><span class="field-label">${esc(title)}</span><ha-selector id="excluded-entities"></ha-selector></div>`;
  } else if (id === "excluded_devices") {
    title = t("settings.device_exclusions");
    content = `<div class="field"><span class="field-label">${esc(title)}</span><ha-selector id="excluded-devices"></ha-selector></div>`;
  } else {
    return "";
  }
  return renderConfigurationDrawer({
    title,
    ariaLabel: t("settings.close_configuration_aria", { name: title }),
    content,
    saveAction: "save-settings",
    saveLabel: t("buttons.save"),
    busy,
    useBottomSheet,
  });
}

export function renderSettingsPanel() {
    this._ensureSettingsDraft();
    return renderSettings({
      config: this._config,
      settingsDraft: this._settingsDraft,
      historyConfig: this._historyConfig,
      entityDelayDraft: this._entityDelayDraft,
      ignoredReferenceDraft: this._ignoredReferenceDraft,
      configurationDrawer: this._configurationDrawer,
      notificationProfileDraft: this._notificationProfileDraft,
      notificationProfileValidationError: this._notificationProfileValidationError,
      notificationUsage: this._notificationStats.last_24h,
      busy: this._busy,
      useBottomSheet: this._useNativeBottomSheet(),
      recoveryActive: this._configRecovery?.active === true,
      configurationDirty: this._automaticDirty || this._settingsDirty,
      automaticMarkup: this._renderAutomatic(),
      configBackupsMarkup: this._renderConfigBackups({
        backups: this._configRecovery?.backups ?? [],
        busy: this._busy,
        date: (value) => this._date(value),
        t: (key, replacements) => this._t(key, replacements),
      }),
      renderNumberField: (...args) => this._numberField(...args),
      t: (key, replacements) => this._t(key, replacements),
    });
}

export function refreshNotificationProfileUsage() {
  updateNotificationProfileUsage(
    this.shadowRoot,
    this._notificationStats.last_24h,
    (key, replacements) => this._t(key, replacements),
  );
}

export function updateConfigurationSaveButton() {
    const button = this.shadowRoot?.querySelector?.('[data-action="save-configuration"]');
    if (!button) return;
    button.classList.toggle("dirty", Boolean(this._automaticDirty || this._settingsDirty));
    button.disabled = Boolean(this._busy || this._configRecovery?.active);
}

export function markConfigurationDirty(kind) {
    if (kind === "automatic") this._automaticDirty = true;
    if (kind === "settings") this._settingsDirty = true;
    this._updateConfigurationSaveButton();
}

export function markConfigurationControlDirty(control) {
    if (!control?.closest || this._configurationDrawer?.kind === "notification") return;
    if (control.closest("#automatic-form")) {
      this._markConfigurationDirty("automatic");
    } else if (control.closest("#settings-form")) {
      this._markConfigurationDirty("settings");
    }
}

export async function saveConfiguration() {
    if (this._busy) return false;
    const saveAutomaticChanges = Boolean(this._automaticDirty);
    const saveSettingsChanges = Boolean(this._settingsDirty);
    if (!saveAutomaticChanges && !saveSettingsChanges) return false;

    const automaticForm = this.shadowRoot.querySelector("#automatic-form");
    const settingsForm = this.shadowRoot.querySelector("#settings-form");
    if (
      saveAutomaticChanges
      && (!automaticForm || !this._reportFormValidity(automaticForm))
    ) return false;
    if (
      saveSettingsChanges
      && (!settingsForm || !this._reportFormValidity(settingsForm))
    ) return false;

    if (!saveSettingsChanges) return this._saveAutomatic();
    const automaticChanges = saveAutomaticChanges
      ? collectAutomaticChanges.call(this) : {};
    if (!automaticChanges) return false;
    return this._saveSettings(automaticChanges);
}

export function commitIgnoredReferenceInput() {
    const input = this.shadowRoot.querySelector("#ignored-reference-input");
    const rawReference = String(input?.value ?? this._ignoredReferenceDraft);
    this._ignoredReferenceDraft = rawReference;
    const reference = rawReference.trim().toLowerCase();
    if (!reference) return true;
    if (!/^[a-z_][a-z0-9_]*\.[a-z0-9_]+$/.test(reference)) {
      this._notice = {
        kind: "error",
        text: this._t("settings.coherence_ignored_entity_reference_validation"),
      };
      return false;
    }
    this._ensureSettingsDraft();
    if (!this._settingsDraft.coherence_ignored_entity_references.includes(reference)) {
      this._settingsDraft.coherence_ignored_entity_references.push(reference);
    }
    this._ignoredReferenceDraft = "";
    if (input) input.value = "";
    return true;
}

export function removeIgnoredReference(reference) {
    this._ensureSettingsDraft();
    this._settingsDraft.coherence_ignored_entity_references =
      this._settingsDraft.coherence_ignored_entity_references.filter(
        (item) => item !== reference,
      );
    this._notice = null;
    this._markConfigurationDirty("settings");
    this._render();
}

export async function exportConfiguration() {
    const result = await this._call(
      { type: "alert_manager/config/export" },
      this._t("success.config_exported"),
    );
    if (!result?.yaml) return;
    downloadTextPayload({
      content: result.yaml,
      content_type: "application/yaml;charset=utf-8",
      filename: "alert-manager-config.yaml",
    });
}

export async function handleImportSelection(event) {
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
    if (result?.config) await this._applyCompleteConfiguration(result);
}

export async function saveSettings(additionalChanges = {}) {
    this._ensureSettingsDraft();
    if (!this._commitIgnoredReferenceInput()) {
      this._refreshUiState();
      return false;
    }
    this._captureEntityDelayValues();
    const historyLimit = Number(this.shadowRoot.querySelector("#history-limit").value);
    if (!Number.isInteger(historyLimit) || historyLimit < 0 || historyLimit > 1000) {
      this._notice = { kind: "error", text: this._t("settings.history_limit_validation") };
      this._refreshUiState();
      return false;
    }
    const entityDelays = {};
    for (const row of this._entityDelayDraft) {
      if (!row.entity_id || !Number.isInteger(row.delay) || row.delay < 0) {
        this._notice = { kind: "error", text: this._t("settings.delay_validation") };
        this._refreshUiState();
        return false;
      }
      if (row.entity_id in entityDelays) {
        this._notice = {
          kind: "error",
          text: this._t("settings.duplicate_delay_save", { entity_id: row.entity_id }),
        };
        this._refreshUiState();
        return false;
      }
      entityDelays[row.entity_id] = row.delay;
    }
    const changes = {
      ...additionalChanges,
      global_delay: Number(this.shadowRoot.querySelector("#global-delay").value),
      pending_display_delay: Number(this.shadowRoot.querySelector("#pending-display-delay").value),
      notification_batch_delay: Number(this._settingsDraft.notification_batch_delay ?? 30),
      coherence_schedule: this.shadowRoot.querySelector("#coherence-schedule").value,
      coherence_scan_esphome: Boolean(
        this.shadowRoot.querySelector("#coherence-scan-esphome").checked,
      ),
      coherence_ignored_entity_references: [
        ...this._settingsDraft.coherence_ignored_entity_references,
      ],
      excluded_labels: [...this._settingsDraft.excluded_labels],
      excluded_entities: [...this._settingsDraft.excluded_entities],
      excluded_devices: [...this._settingsDraft.excluded_devices],
      entity_delays: entityDelays,
    };
    const historyChanged = historyLimit !== Number(this._historyConfig.retention_limit);
    this._busy = true;
    this._notice = null;
    this._refreshUiState();
    let saved = false;
    try {
      const config = await this._api.call({
        type: "alert_manager/config/update",
        config: changes,
      });
      this._config = config;
      if (additionalChanges.automatic) this._resetAutomaticDraft();
      if (historyChanged) {
        this._historyConfig = await this._api.call({
          type: "alert_manager/history/config/update",
          retention_limit: historyLimit,
        });
        this._config = { ...this._config, history_limit: historyLimit };
        if (this._historyLoaded) await this._refreshHistory();
      }
      this._resetSettingsDraft({ preserveNotification: true });
      this._configurationDrawer = null;
      replaceConfigurationDrawer(
        this.shadowRoot?.querySelector?.("#settings-form"),
        "",
      );
      this._notice = { kind: "success", text: this._t("success.settings_saved") };
      saved = true;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._busy = false;
      this._refreshUiState();
    }
    return saved;
}

export function resetSettingsDraft({ preserveNotification = false } = {}) {
    this._settingsDirty = false;
    this._settingsDraft = null;
    this._entityDelayDraft = null;
    this._ignoredReferenceDraft = "";
    if (!preserveNotification) {
      this._notificationProfileDraft = null;
      this._notificationProfileId = null;
      this._notificationProfileOriginal = null;
      this._notificationProfileValidationError = null;
    }
}

export function ensureSettingsDraft() {
    if (this._settingsDraft && this._entityDelayDraft) return;
    this._settingsDraft = {
      global_delay: this._config.global_delay,
      pending_display_delay: this._config.pending_display_delay,
      notification_batch_delay: this._config.notification_batch_delay ?? 30,
      coherence_schedule: this._config.coherence_schedule ?? "none",
      coherence_scan_esphome: this._config.coherence_scan_esphome !== false,
      history_limit: this._historyConfig.retention_limit,
      coherence_ignored_entity_references: [
        ...(this._config.coherence_ignored_entity_references ?? []),
      ],
      excluded_labels: [...(this._config.excluded_labels ?? [])],
      excluded_entities: [...(this._config.excluded_entities ?? [])],
      excluded_devices: [...(this._config.excluded_devices ?? [])],
      notification_profiles: (this._config.notification_profiles ?? []).map(
        cloneNotificationProfile,
      ),
    };
    this._entityDelayDraft = Object.entries(this._config.entity_delays ?? {}).map(
      ([entity_id, delay]) => ({ entity_id, delay }),
    );
}

export function handleSettingsInput(event) {
    if (event.target?.closest?.("#automatic-form")) this._captureAutomaticConfigurationValues();
    if (event.target?.dataset?.delayIndex !== undefined) this._captureEntityDelayValues();
    if (this._configurationDrawer?.kind === "notification") this._captureNotificationProfileDraft();

    const fields = {
      "global-delay": "global_delay",
      "pending-display-delay": "pending_display_delay",
      "notification-batch-delay": "notification_batch_delay",
      "history-limit": "history_limit",
    };
    const field = fields[event.target?.id];
    if (!field) return;
    this._ensureSettingsDraft();
    this._settingsDraft[field] = String(event.target.value ?? "");
}

export function captureEntityDelayValues() {
    if (!this._entityDelayDraft) return;
    this.shadowRoot.querySelectorAll("[data-delay-index]").forEach((input) => {
      const row = this._entityDelayDraft[Number(input.dataset.delayIndex)];
      if (row) row.delay = Number(input.value);
    });
}

export function setEntityDelayEntity(index, value) {
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

export function hydrateSettingsControls() {
  this._ensureSettingsDraft();
  this._configureSelect(
    "coherence-schedule",
    ["none", "daily", "weekly", "monthly"].map((value) => ({
      value,
      label: this._t(`settings.coherence_schedules.${value}`),
    })),
    this._settingsDraft.coherence_schedule,
    (value) => {
      this._settingsDraft.coherence_schedule = value;
    },
  );
  this.shadowRoot.querySelectorAll("ha-input-chip[data-ignored-reference]").forEach((chip) => {
    if (this._configuredControls.has(chip)) return;
    chip.label = chip.dataset.ignoredReference;
    chip.selected = true;
    chip.addEventListener("remove", (event) => {
      event.stopPropagation();
      this._removeIgnoredReference(chip.dataset.ignoredReference);
    });
    this._configuredControls.add(chip);
  });
  this._configureSelector(
    "excluded-labels",
    { label: { multiple: true } },
    this._settingsDraft.excluded_labels,
    (value) => {
      this._settingsDraft.excluded_labels = this._multipleSelectorValue(
        value,
        this._settingsDraft.excluded_labels,
      );
    },
  );
  this._configureSelector(
    "excluded-entities",
    { entity: { multiple: true, exclude_entities: ALERT_MANAGER_ENTITY_IDS } },
    this._settingsDraft.excluded_entities,
    (value) => {
      this._settingsDraft.excluded_entities = this._multipleSelectorValue(
        value,
        this._settingsDraft.excluded_entities,
      );
      updateSettingsConfigurationCount.call(this, "excluded_entities");
    },
  );
  this._configureSelector(
    "excluded-devices",
    { device: { multiple: true } },
    this._settingsDraft.excluded_devices,
    (value) => {
      this._settingsDraft.excluded_devices = this._multipleSelectorValue(
        value,
        this._settingsDraft.excluded_devices,
      );
      updateSettingsConfigurationCount.call(this, "excluded_devices");
    },
  );
  this._entityDelayDraft.forEach((row, index) => {
    this._configureSelector(
      `delay-entity-${index}`,
      { entity: { exclude_entities: ALERT_MANAGER_ENTITY_IDS } },
      row.entity_id || "",
      (value) => this._setEntityDelayEntity(index, value),
    );
  });
  hydrateNotificationProfileControls(this);
}

export function refreshSettingsConfigurationDrawer() {
  const form = this.shadowRoot?.querySelector?.("#settings-form");
  if (!form) {
    this._render();
    return;
  }
  replaceConfigurationDrawer(form, renderSettingsConfigurationDrawer({
    settingsDraft: this._settingsDraft,
    entityDelayDraft: this._entityDelayDraft,
    configurationDrawer: this._configurationDrawer,
    notificationProfileDraft: this._notificationProfileDraft,
    notificationProfileValidationError: this._notificationProfileValidationError,
    busy: this._busy,
    useBottomSheet: this._useNativeBottomSheet(),
    t: (key, replacements) => this._t(key, replacements),
  }));
  this._hydrateSelectors();
  this._decorateActionIcons();
}

export function updateSettingsConfigurationCount(id) {
  const button = this.shadowRoot?.querySelector?.(`#settings-${id}-configuration`);
  if (!button) return;
  const count = id === "entity_delays"
    ? this._entityDelayDraft.length
    : this._settingsDraft[id].length;
  button.textContent = this._t("buttons.configuration_named", {
    name: button.dataset.configurationLabel,
    count,
  });
}

export async function handleSettingsAction(action, button) {
  if (action === "scroll-settings-section") {
    const sectionId = button.dataset.sectionId;
    if (SETTINGS_SECTIONS.some(([id]) => id === sectionId)) {
      this.shadowRoot.querySelector(`#settings-section-${sectionId}`)
        ?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
    return true;
  }
  if (action === "save-settings") {
    const form = this.shadowRoot.querySelector("#settings-form");
    if (form && this._reportFormValidity(form) && !this._busy) await this._saveSettings();
    return true;
  }
  if (action === "save-configuration") {
    await this._saveConfiguration();
    return true;
  }
  if (action === "open-settings-configuration") {
    this._ensureSettingsDraft();
    this._captureEntityDelayValues();
    this._configurationDrawer = {
      kind: "settings",
      id: button.dataset.configurationId,
    };
    refreshSettingsConfigurationDrawer.call(this);
    return true;
  }
  if (
    action === "close-configuration-drawer"
    && this._configurationDrawer?.kind === "settings"
  ) {
    const id = this._configurationDrawer.id;
    this._captureEntityDelayValues();
    this._configurationDrawer = null;
    refreshSettingsConfigurationDrawer.call(this);
    updateSettingsConfigurationCount.call(this, id);
    return true;
  }
  if (action === "add-ignored-reference") {
    if (this._commitIgnoredReferenceInput()) this._notice = null;
    this._render();
    return true;
  }
  if (action === "export-config") {
    await this._exportConfiguration();
    return true;
  }
  if (action === "choose-config-import") {
    this.shadowRoot.querySelector("#config-import-file")?.click();
    return true;
  }
  if (action === "add-entity-delay") {
    this._ensureSettingsDraft();
    this._captureEntityDelayValues();
    this._entityDelayDraft.push({ entity_id: "", delay: 900 });
    this._markConfigurationDirty("settings");
    refreshSettingsConfigurationDrawer.call(this);
    updateSettingsConfigurationCount.call(this, "entity_delays");
    return true;
  }
  if (action === "remove-entity-delay") {
    this._captureEntityDelayValues();
    this._entityDelayDraft.splice(Number(button.dataset.index), 1);
    this._markConfigurationDirty("settings");
    refreshSettingsConfigurationDrawer.call(this);
    updateSettingsConfigurationCount.call(this, "entity_delays");
    return true;
  }
  return false;
}
