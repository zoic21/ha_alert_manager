import { ALERT_MANAGER_ENTITY_IDS, MDI_DOWNLOAD, MDI_PLUS, MDI_UPLOAD } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { downloadTextPayload } from "../components/config-backups.js";
import {
  renderConfigurationDrawer,
  replaceConfigurationDrawer,
} from "../components/configuration-drawer.js";

export function renderSettings(context) {
    const {
      config, settingsDraft, historyConfig, historyEvents, entityDelayDraft,
      ignoredReferenceDraft, configurationDrawer, busy,
      recoveryActive = false, configBackupsMarkup = "",
      renderNumberField, t,
    } = context;
    const ignoredReferences = settingsDraft.coherence_ignored_entity_references;
    return `<form id="settings-form" class="stack settings-form">
      <ha-card outlined class="panel settings-card"><h2>${esc(t("settings.alert_display"))}</h2><div class="settings-grid">
        ${renderNumberField("global-delay", t("settings.global_delay"), config.global_delay, t("units.seconds"), 0, 31536000, { help: t("settings.global_delay_help") })}
        ${renderNumberField("pending-display-delay", t("settings.pending_display_delay"), config.pending_display_delay, t("units.seconds"), 0, 31536000, { help: t("settings.pending_display_delay_help") })}
      </div></ha-card>
      <ha-card outlined class="panel settings-card"><h2>${esc(t("settings.coherence_settings"))}</h2><div class="settings-grid">
        <div class="field"><span class="field-label">${esc(t("settings.coherence_schedule"))}</span><ha-select id="coherence-schedule"></ha-select><small>${esc(t("settings.coherence_schedule_help"))}</small></div>
        <div class="field"><div class="switch-field-row"><span class="field-label">${esc(t("settings.coherence_scan_esphome"))}</span><ha-switch id="coherence-scan-esphome" aria-label="${esc(t("settings.coherence_scan_esphome"))}" ${settingsDraft.coherence_scan_esphome ? "checked" : ""}></ha-switch></div><small>${esc(t("settings.coherence_scan_esphome_help"))}</small></div>
        <div class="field settings-wide ignored-references-field"><span class="field-label">${esc(t("settings.coherence_ignored_entity_references"))}</span>
          ${ignoredReferences.length ? `<ha-chip-set class="ignored-reference-chips">${ignoredReferences.map((reference) => `<ha-input-chip selected label="${esc(reference)}" data-ignored-reference="${esc(reference)}">${esc(reference)}</ha-input-chip>`).join("")}</ha-chip-set>` : ""}
          <div class="ignored-reference-add"><ha-input id="ignored-reference-input" type="text" value="${esc(ignoredReferenceDraft)}" placeholder="${esc(t("settings.coherence_ignored_entity_reference_placeholder"))}" aria-label="${esc(t("settings.coherence_ignored_entity_reference_placeholder"))}"></ha-input><ha-button type="button" appearance="plain" data-action="add-ignored-reference"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button></div>
          <small>${esc(t("settings.coherence_ignored_entity_references_help"))}</small>
        </div>
      </div></ha-card>
      <ha-card outlined class="panel settings-card"><h2>${esc(t("settings.exclusions"))}</h2><div class="settings-grid">
        <div class="field settings-wide"><span class="field-label">${esc(t("settings.label_exclusions"))}</span><ha-selector id="excluded-labels"></ha-selector><small>${esc(t("settings.labels_help"))}</small></div>
        ${renderSettingsConfigurationEntry("excluded_entities", t("settings.entity_exclusions"), (settingsDraft.excluded_entities ?? []).length, t)}
        ${renderSettingsConfigurationEntry("excluded_devices", t("settings.device_exclusions"), (settingsDraft.excluded_devices ?? []).length, t)}
      </div></ha-card>
      <ha-card outlined class="panel settings-card"><h2>${esc(t("settings.history_settings"))}</h2>
        <div class="history-settings">
          <div class="history-settings-row">
            <span class="field-label history-limit-label">${esc(t("settings.history_limit"))}</span>
            <ha-input id="history-limit" type="number" min="0" max="1000" step="1" value="${esc(historyConfig.retention_limit)}" required aria-label="${esc(t("settings.history_limit"))}"><span slot="end">${esc(t("units.events"))}</span></ha-input>
            <div class="actions history-actions"><ha-button appearance="plain" variant="danger" data-action="clear-history" ${busy || !historyEvents.length ? "disabled" : ""}>${esc(t("settings.history_clear"))}</ha-button></div>
          </div>
          <small class="history-limit-help">${esc(t("settings.history_limit_help"))}</small>
        </div>
      </ha-card>
      <ha-card outlined class="panel settings-card"><div><h2>${esc(t("settings.entity_delay"))}</h2><small>${esc(t("settings.delay_help"))}</small></div>
        ${renderSettingsConfigurationEntry("entity_delays", t("settings.entity_delay"), entityDelayDraft.length, t)}
      </ha-card>
      <ha-card outlined class="panel configuration-transfer"><div><h2>${esc(t("settings.transfer_title"))}</h2><small>${esc(t("settings.transfer_help"))}</small></div>
        <div class="actions transfer-actions"><ha-button appearance="plain" data-action="export-config" ${busy || recoveryActive ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_DOWNLOAD}"></ha-svg-icon>${esc(t("settings.export"))}</ha-button><ha-button appearance="accent" variant="brand" data-action="choose-config-import" ${busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_UPLOAD}"></ha-svg-icon>${esc(t("settings.import"))}</ha-button></div>
        <input id="config-import-file" data-import-file type="file" accept=".yaml,.yml,text/yaml,application/x-yaml" hidden>
        ${configBackupsMarkup}
      </ha-card>
      <div class="actions settings-save-actions"><ha-button appearance="accent" variant="brand" data-action="save-settings" ${busy || recoveryActive ? "disabled" : ""}>${esc(t("settings.save"))}</ha-button></div>
      ${renderSettingsConfigurationDrawer({
        settingsDraft, entityDelayDraft, configurationDrawer, busy, t,
      })}
    </form>`;
}

export function renderSettingsConfigurationEntry(id, label, count, t) {
  return `<div class="configuration-entry settings-configuration-entry"><ha-button id="settings-${id}-configuration" appearance="plain" data-action="open-settings-configuration" data-configuration-id="${esc(id)}" data-configuration-label="${esc(label)}" aria-label="${esc(t("settings.configure_aria", { name: label }))}">${esc(t("buttons.configuration_named", { name: label, count }))}</ha-button></div>`;
}

export function renderSettingsConfigurationDrawer(context) {
  const { settingsDraft, entityDelayDraft, configurationDrawer, busy, t } = context;
  if (configurationDrawer?.kind !== "settings") return "";
  const id = configurationDrawer.id;
  let title;
  let content;
  if (id === "entity_delays") {
    title = t("settings.entity_delay");
    content = `<div class="configuration-section-heading">
        <small>${esc(t("settings.delay_help"))}</small>
        <ha-button appearance="plain" data-action="add-entity-delay"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button>
      </div>
      <div class="delay-list">${entityDelayDraft.length ? entityDelayDraft.map((row, index) => `<div class="delay-row">
        <ha-selector id="delay-entity-${index}"></ha-selector>
        <ha-input data-delay-index="${index}" type="number" min="0" max="31536000" step="1" value="${esc(row.delay)}" required aria-label="${esc(t("settings.aria_delay"))}"><span slot="end">${esc(t("units.seconds"))}</span></ha-input>
        <ha-button appearance="plain" variant="danger" data-action="remove-entity-delay" data-index="${index}" aria-label="${esc(t("settings.aria_remove_delay"))}">${esc(t("buttons.delete"))}</ha-button>
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
  });
}

export function renderSettingsPanel() {
    this._ensureSettingsDraft();
    return renderSettings({
      config: this._config,
      settingsDraft: this._settingsDraft,
      historyConfig: this._historyConfig,
      historyEvents: this._history?.events ?? [],
      entityDelayDraft: this._entityDelayDraft,
      ignoredReferenceDraft: this._ignoredReferenceDraft,
      configurationDrawer: this._configurationDrawer,
      busy: this._busy,
      recoveryActive: this._configRecovery?.active === true,
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

export async function saveSettings() {
    this._ensureSettingsDraft();
    if (!this._commitIgnoredReferenceInput()) {
      this._refreshUiState();
      return;
    }
    this._captureEntityDelayValues();
    const historyLimit = Number(this.shadowRoot.querySelector("#history-limit").value);
    if (!Number.isInteger(historyLimit) || historyLimit < 0 || historyLimit > 1000) {
      this._notice = { kind: "error", text: this._t("settings.history_limit_validation") };
      this._refreshUiState();
      return;
    }
    const entityDelays = {};
    for (const row of this._entityDelayDraft) {
      if (!row.entity_id || !Number.isInteger(row.delay) || row.delay < 0) {
        this._notice = { kind: "error", text: this._t("settings.delay_validation") };
        this._refreshUiState();
        return;
      }
      if (row.entity_id in entityDelays) {
        this._notice = {
          kind: "error",
          text: this._t("settings.duplicate_delay_save", { entity_id: row.entity_id }),
        };
        this._refreshUiState();
        return;
      }
      entityDelays[row.entity_id] = row.delay;
    }
    const changes = {
      global_delay: Number(this.shadowRoot.querySelector("#global-delay").value),
      pending_display_delay: Number(this.shadowRoot.querySelector("#pending-display-delay").value),
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
    try {
      const config = await this._api.call({
        type: "alert_manager/config/update",
        config: changes,
      });
      this._config = config;
      if (historyChanged) {
        this._historyConfig = await this._api.call({
          type: "alert_manager/history/config/update",
          retention_limit: historyLimit,
        });
        this._config = { ...this._config, history_limit: historyLimit };
        await this._refreshHistory();
      }
      this._resetSettingsDraft();
      this._configurationDrawer = null;
      replaceConfigurationDrawer(
        this.shadowRoot?.querySelector?.("#settings-form"),
        "",
      );
      this._notice = { kind: "success", text: this._t("success.settings_saved") };
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._busy = false;
      this._refreshUiState();
    }
}

export function resetSettingsDraft() {
    this._settingsDraft = null;
    this._entityDelayDraft = null;
    this._ignoredReferenceDraft = "";
}

export function ensureSettingsDraft() {
    if (this._settingsDraft && this._entityDelayDraft) return;
    this._settingsDraft = {
      coherence_scan_esphome: this._config.coherence_scan_esphome !== false,
      coherence_ignored_entity_references: [
        ...(this._config.coherence_ignored_entity_references ?? []),
      ],
      excluded_labels: [...(this._config.excluded_labels ?? [])],
      excluded_entities: [...(this._config.excluded_entities ?? [])],
      excluded_devices: [...(this._config.excluded_devices ?? [])],
    };
    this._entityDelayDraft = Object.entries(this._config.entity_delays ?? {}).map(
      ([entity_id, delay]) => ({ entity_id, delay }),
    );
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
    this._config.coherence_schedule ?? "none",
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
    busy: this._busy,
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
  if (action === "save-settings") {
    const form = this.shadowRoot.querySelector("#settings-form");
    if (form && this._reportFormValidity(form) && !this._busy) await this._saveSettings();
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
    refreshSettingsConfigurationDrawer.call(this);
    updateSettingsConfigurationCount.call(this, "entity_delays");
    return true;
  }
  if (action === "remove-entity-delay") {
    this._captureEntityDelayValues();
    this._entityDelayDraft.splice(Number(button.dataset.index), 1);
    refreshSettingsConfigurationDrawer.call(this);
    updateSettingsConfigurationCount.call(this, "entity_delays");
    return true;
  }
  return false;
}
