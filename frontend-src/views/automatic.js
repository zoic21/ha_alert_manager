import { MAX_DURATION_SECONDS, MDI_PLUS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import {
  renderConfigurationDrawer,
  replaceConfigurationDrawer,
} from "../components/configuration-drawer.js";

const NUMBER_MAP_FIELD_TYPES = new Set(["device_number_map", "entity_number_map"]);
const MAP_FIELD_TYPES = new Set([
  ...NUMBER_MAP_FIELD_TYPES,
  "device_settings_map",
  "pack_settings_map",
]);

function isNumberMapField(field) {
  return NUMBER_MAP_FIELD_TYPES.has(field.type);
}

function drawerFields(pack) {
  return (pack.config_fields ?? []).filter((field) => MAP_FIELD_TYPES.has(field.type));
}

function fieldConfigurationCount(pack, field, config, draft) {
  const value = draft?.[pack.id]?.[field.id];
  return Array.isArray(value)
    ? value.filter((row) => row.target_id).length
    : Object.keys(value ?? config[field.id] ?? {}).length;
}

export function renderAutomatic(context) {
    const {
      availablePacks, config, draft, configurationDrawer, busy, useBottomSheet,
      renderNumberField, t,
    } = context;
    return `<ha-card id="settings-section-automatic" outlined class="panel settings-card automatic-section settings-scroll-section">
      <h2 class="automatic-section-title">${esc(t("tabs.automatic"))}</h2>
      <form id="automatic-form" class="automatic-grid">
      ${availablePacks.map((pack) => {
        const packConfig = draft[pack.id];
        const packKey = pack.translation_key || pack.id;
        const packName = t(`packs.${packKey}.name`);
        const configurableFields = drawerFields(pack);
        const configurationButtons = configurableFields.map((field) => {
          const fieldName = t(`automatic.fields.${field.translation_key}.label`);
          const count = fieldConfigurationCount(pack, field, packConfig, draft);
          const label = configurableFields.length === 1
            ? t("buttons.configuration", { count })
            : t("buttons.configuration_named", { name: fieldName, count });
          return `<ha-button id="auto-${pack.id}-${field.id}-configuration" appearance="plain" data-action="open-automatic-configuration" data-pack-id="${esc(pack.id)}" data-field-id="${esc(field.id)}" aria-label="${esc(t("automatic.configure_aria", { name: fieldName }))}">${esc(label)}</ha-button>`;
        }).join("");
        return `<section class="category-card">
          <div class="category-header">
            <h2>${esc(packName)}</h2>
            <ha-switch id="auto-${pack.id}-enabled" aria-label="${esc(t("automatic.aria_enable", { name: packName }))}" ${packConfig.enabled ? "checked" : ""}></ha-switch>
          </div>
          <p>${esc(t(`packs.${packKey}.description`))}</p>
          <div class="pack-configuration" data-pack-configuration="${esc(pack.id)}" ${packConfig.enabled ? "" : "hidden"}>
            <div class="fields">
              <div class="field full"><span class="field-label">${esc(t("automatic.labels"))}</span><ha-selector id="auto-${pack.id}-labels"></ha-selector><small>${esc(t("automatic.labels_help"))}</small></div>
              ${pack.uses_delay === false ? "" : renderNumberField(`auto-${pack.id}-delay`, t("automatic.pack_delay"), packConfig.delay, t("units.seconds"), 0, MAX_DURATION_SECONDS, { required: false, help: t("automatic.empty_delay_help") })}
              ${(pack.config_fields ?? []).filter((field) => field.type === "number").map((field) => renderPackField(
                pack,
                field,
                packConfig,
                { availablePacks, draft, renderNumberField, t },
              )).join("")}
            </div>
            ${configurationButtons ? `<div class="configuration-entry automatic-configuration-entry${configurableFields.length > 1 ? " has-multiple-configurations" : ""}">${configurationButtons}</div>` : ""}
          </div>
        </section>`;
      }).join("")}
      ${renderAutomaticConfigurationDrawer({
        availablePacks, config, draft, configurationDrawer, busy, useBottomSheet,
        renderNumberField, t,
      })}
      </form>
    </ha-card>`;
}

export function renderAutomaticPanel() {
    this._ensureAutomaticDraft();
    return renderAutomatic({
      availablePacks: this._packs.filter((pack) => pack.available),
      config: this._config,
      draft: this._automaticMapDraft,
      configurationDrawer: this._configurationDrawer,
      busy: this._busy,
      useBottomSheet: this._useNativeBottomSheet(),
      renderNumberField: (...args) => this._numberField(...args),
      t: (key, replacements) => this._t(key, replacements),
    });
}

export function renderAutomaticConfigurationDrawer(context) {
  const {
    availablePacks, config, draft, configurationDrawer, busy, useBottomSheet,
    renderNumberField, t,
  } = context;
  if (configurationDrawer?.kind !== "automatic") return "";
  const pack = availablePacks.find((item) => item.id === configurationDrawer.id);
  const fields = pack ? drawerFields(pack) : [];
  const field = fields.find((item) => item.id === configurationDrawer.fieldId)
    ?? (fields.length === 1 ? fields[0] : null);
  if (!field) return "";
  const packConfig = draft[pack.id];
  const fieldName = t(`automatic.fields.${field.translation_key}.label`);
  const content = `<div class="fields configuration-drawer-fields">${renderPackField(
    pack,
    field,
    packConfig,
    { availablePacks, draft, renderNumberField, t },
  )}</div>`;
  return renderConfigurationDrawer({
    title: fieldName,
    ariaLabel: t("automatic.close_configuration_aria", { name: fieldName }),
    content,
    saveAction: "save-automatic",
    saveLabel: t("buttons.save"),
    busy,
    useBottomSheet,
  });
}

export function renderPackField(pack, field, config, context) {
    const { availablePacks = [], draft, renderNumberField, t } = context;
    const label = t(`automatic.fields.${field.translation_key}.label`);
    if (field.type === "number") {
      return renderNumberField(
        `auto-${pack.id}-${field.id}`,
        label,
        draft[pack.id]?.[field.id] ?? config[field.id],
        field.unit ?? "",
        field.minimum ?? -1000000000,
        field.maximum ?? 1000000000,
        { step: field.step ?? "any" },
      );
    }
    if (field.type === "pack_settings_map") {
      const configured = draft[pack.id]?.[field.id] ?? {};
      return `<div class="field full pack-source-field">
        <div class="configuration-section-heading pack-map-heading"><div><span class="field-label">${esc(label)}</span><small>${esc(t(`automatic.fields.${field.translation_key}.help`))}</small></div></div>
        <div class="pack-source-list">${availablePacks.filter((sourcePack) => sourcePack.id !== pack.id).map((sourcePack) => {
          const enabled = Object.hasOwn(configured, sourcePack.id);
          const settings = configured[sourcePack.id] ?? {};
          const sourceName = t(`packs.${sourcePack.translation_key || sourcePack.id}.name`);
          return `<div class="pack-source-row">
            <div class="switch-field-row"><span class="field-label">${esc(sourceName)}</span><ha-switch data-pack-source-toggle="${esc(pack.id)}" data-pack-field="${esc(field.id)}" data-source-pack-id="${esc(sourcePack.id)}" aria-label="${esc(t("automatic.enable_source_pack", { name: sourceName }))}" ${enabled ? "checked" : ""}></ha-switch></div>
            <div class="pack-settings-values" data-pack-source-values="${esc(sourcePack.id)}" ${enabled ? "" : "hidden"}>${(field.fields ?? []).map((setting) => `<label class="pack-setting-field"><span class="field-label">${esc(t(`automatic.fields.${setting.translation_key}.label`))}</span><ha-input type="number" min="${setting.minimum ?? -1000000000}" max="${setting.maximum ?? 1000000000}" step="${setting.step ?? "any"}" value="${esc(settings[setting.id])}" data-pack-source-setting="${esc(pack.id)}" data-pack-field="${esc(field.id)}" data-source-pack-id="${esc(sourcePack.id)}" data-setting-id="${esc(setting.id)}" aria-label="${esc(t(`automatic.fields.${setting.translation_key}.label`))}">${setting.unit ? `<span slot="end">${esc(setting.unit)}</span>` : ""}</ha-input></label>`).join("")}</div>
          </div>`;
        }).join("")}</div>
      </div>`;
    }
    if (field.type === "device_settings_map") {
      const rows = draft[pack.id]?.[field.id] ?? [];
      return `<div class="field full pack-map-field">
        <div class="configuration-section-heading pack-map-heading">
          <div><span class="field-label">${esc(label)}</span><small>${esc(t(`automatic.fields.${field.translation_key}.help`))}</small></div>
          <ha-button appearance="plain" data-action="add-pack-map-row" data-pack-id="${esc(pack.id)}" data-field-id="${esc(field.id)}"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button>
        </div>
        <div class="pack-map-list">
          ${rows.length ? rows.map((row, index) => `<div class="pack-map-row pack-settings-row">
            <label class="field full pack-target-field"><span class="field-label">${esc(t("automatic.device"))}</span><ha-selector id="auto-${pack.id}-${field.id}-target-${index}"></ha-selector></label>
            <div class="pack-settings-values">${(field.fields ?? []).map((setting) => `<label class="pack-setting-field"><span class="field-label">${esc(t(`automatic.fields.${setting.translation_key}.label`))}</span><ha-input type="number" min="${setting.minimum ?? -1000000000}" max="${setting.maximum ?? 1000000000}" step="${setting.step ?? "any"}" value="${esc(row[setting.id])}" data-pack-setting="${esc(pack.id)}" data-pack-field="${esc(field.id)}" data-pack-index="${index}" data-setting-id="${esc(setting.id)}" required aria-label="${esc(t(`automatic.fields.${setting.translation_key}.label`))}">${setting.unit ? `<span slot="end">${esc(setting.unit)}</span>` : ""}</ha-input></label>`).join("")}</div>
            <ha-button appearance="plain" variant="danger" data-action="remove-pack-map-row" data-pack-id="${esc(pack.id)}" data-field-id="${esc(field.id)}" data-index="${index}">${esc(t("buttons.remove"))}</ha-button>
          </div>`).join("") : `<div class="empty compact pack-map-empty">${esc(t(`automatic.fields.${field.translation_key}.empty`))}</div>`}
        </div>
      </div>`;
    }
    if (!isNumberMapField(field)) return "";
    const rows = draft[pack.id]?.[field.id] ?? [];
    return `<div class="field full pack-map-field">
      <div class="configuration-section-heading pack-map-heading">
        <div><span class="field-label">${esc(label)}</span><small>${esc(t(`automatic.fields.${field.translation_key}.help`))}</small></div>
        <ha-button appearance="plain" data-action="add-pack-map-row" data-pack-id="${esc(pack.id)}" data-field-id="${esc(field.id)}"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button>
      </div>
      <div class="pack-map-list">
        ${rows.length ? rows.map((row, index) => `<div class="pack-map-row">
          <ha-selector id="auto-${pack.id}-${field.id}-target-${index}"></ha-selector>
          <ha-input type="number" min="${field.minimum ?? -1000000000}" max="${field.maximum ?? 1000000000}" step="${field.step ?? "any"}" value="${esc(row.value)}" data-pack-map="${esc(pack.id)}" data-pack-field="${esc(field.id)}" data-pack-index="${index}" required aria-label="${esc(label)}"><span slot="end">${esc(field.unit ?? "")}</span></ha-input>
          <ha-button appearance="plain" variant="danger" data-action="remove-pack-map-row" data-pack-id="${esc(pack.id)}" data-field-id="${esc(field.id)}" data-index="${index}">${esc(t("buttons.remove"))}</ha-button>
        </div>`).join("") : `<div class="empty compact pack-map-empty">${esc(t(`automatic.fields.${field.translation_key}.empty`))}</div>`}
      </div>
    </div>`;
}

export function collectAutomaticChanges() {
    this._ensureAutomaticDraft();
    captureAutomaticConfigurationValues.call(this);
    const automatic = {};
    for (const pack of this._packs.filter((item) => item.available)) {
      automatic[pack.id] = {
        enabled: this._automaticMapDraft[pack.id].enabled,
        label_ids: [...(this._automaticMapDraft[pack.id].label_ids ?? [])],
      };
      if (pack.uses_delay !== false) {
        automatic[pack.id].delay = this._automaticMapDraft[pack.id].delay;
      }
      for (const field of pack.config_fields ?? []) {
        if (field.type === "number") {
          automatic[pack.id][field.id] = Number(
            this._automaticMapDraft[pack.id]?.[field.id] ?? field.default,
          );
          continue;
        }
        if (field.type === "device_settings_map") {
          const rows = this._automaticMapDraft[pack.id]?.[field.id] ?? [];
          const values = {};
          for (const row of rows) {
            const settingsValid = (field.fields ?? []).every(
              (setting) => Number.isFinite(row[setting.id]),
            );
            if (!row.target_id || !settingsValid || Object.hasOwn(values, row.target_id)) {
              this._notice = {
                kind: "error",
                text: this._t(
                  `automatic.fields.${field.translation_key}.${row.target_id && settingsValid ? "duplicate" : "validation"}`,
                ),
              };
              this._refreshUiState();
              return false;
            }
            values[row.target_id] = Object.fromEntries(
              (field.fields ?? []).map((setting) => [setting.id, row[setting.id]]),
            );
          }
          automatic[pack.id][field.id] = values;
          continue;
        }
        if (field.type === "pack_settings_map") {
          const configured = this._automaticMapDraft[pack.id]?.[field.id] ?? {};
          const values = {};
          for (const [sourcePackId, settings] of Object.entries(configured)) {
            if ((field.fields ?? []).some(
              (setting) => settings[setting.id] !== null
                && !Number.isFinite(settings[setting.id]),
            )) {
              this._notice = {
                kind: "error",
                text: this._t(`automatic.fields.${field.translation_key}.validation`),
              };
              this._refreshUiState();
              return false;
            }
            values[sourcePackId] = { ...settings };
          }
          automatic[pack.id][field.id] = values;
          continue;
        }
        if (!isNumberMapField(field)) continue;
        const rows = this._automaticMapDraft[pack.id]?.[field.id] ?? [];
        const values = {};
        for (const row of rows) {
          if (!row.target_id || !Number.isFinite(row.value)) {
            this._notice = {
              kind: "error",
              text: this._t(
                `automatic.fields.${field.translation_key}.validation`,
              ),
            };
            this._refreshUiState();
            return false;
          }
          if (Object.hasOwn(values, row.target_id)) {
            this._notice = {
              kind: "error",
              text: this._t(
                `automatic.fields.${field.translation_key}.duplicate`,
              ),
            };
            this._refreshUiState();
            return false;
          }
          values[row.target_id] = row.value;
        }
        automatic[pack.id][field.id] = values;
      }
    }
    return { automatic };
}

export async function saveAutomatic() {
    const changes = collectAutomaticChanges.call(this);
    if (!changes) return false;
    const config = await this._call(
      { type: "alert_manager/config/update", config: changes },
      this._t("success.automatic_saved"),
    );
    if (config) {
      this._config = config;
      this._configurationDrawer = null;
      this._resetAutomaticDraft();
      replaceConfigurationDrawer(
        this.shadowRoot?.querySelector?.("#automatic-form"),
        "",
      );
      this._refreshUiState();
      return true;
    }
    return false;
}

export function resetAutomaticDraft() {
    this._automaticDirty = false;
    this._automaticMapDraft = null;
    this._ensureAutomaticDraft();
}

export function ensureAutomaticDraft() {
    if (this._automaticMapDraft || !this._config) return;
    this._automaticMapDraft = {};
    for (const pack of this._packs) {
      const fields = { ...this._config.automatic?.[pack.id] };
      fields.label_ids = [...(fields.label_ids ?? [])];
      for (const field of pack.config_fields ?? []) {
        const configured = this._config.automatic?.[pack.id]?.[field.id]
          ?? field.default;
        fields[field.id] = field.type === "pack_settings_map"
          ? Object.fromEntries(Object.entries(configured ?? {}).map(
            ([sourcePackId, settings]) => [sourcePackId, { ...settings }],
          ))
          : field.type === "device_settings_map"
          ? Object.entries(configured ?? {}).map(
            ([target_id, settings]) => ({ target_id, ...settings }),
          )
          : isNumberMapField(field)
          ? Object.entries(configured ?? {}).map(
            ([target_id, value]) => ({ target_id, value }),
          )
          : configured;
      }
      this._automaticMapDraft[pack.id] = fields;
    }
}

export function captureAutomaticMapValues() {
    if (!this._automaticMapDraft) return;
    this.shadowRoot.querySelectorAll("[data-pack-map]").forEach((input) => {
      const row = this._automaticMapDraft[input.dataset.packMap]?.[
        input.dataset.packField
      ]?.[Number(input.dataset.packIndex)];
      if (row) row.value = Number(input.value);
    });
    this.shadowRoot.querySelectorAll("[data-pack-setting]").forEach((input) => {
      const row = this._automaticMapDraft[input.dataset.packSetting]?.[
        input.dataset.packField
      ]?.[Number(input.dataset.packIndex)];
      if (row) row[input.dataset.settingId] = Number(input.value);
    });
    this.shadowRoot.querySelectorAll("[data-pack-source-setting]").forEach((input) => {
      const settings = this._automaticMapDraft[input.dataset.packSourceSetting]?.[
        input.dataset.packField
      ]?.[input.dataset.sourcePackId];
      if (settings) {
        settings[input.dataset.settingId] = input.value === "" ? null : Number(input.value);
      }
    });
}

export function captureAutomaticConfigurationValues() {
  this._ensureAutomaticDraft();
  captureAutomaticMapValues.call(this);
  for (const pack of this._packs) {
    const draft = this._automaticMapDraft?.[pack.id];
    if (!draft) continue;
    const enabled = this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`);
    const delay = this.shadowRoot.querySelector(`#auto-${pack.id}-delay`);
    if (enabled) draft.enabled = enabled.checked;
    if (delay) draft.delay = delay.value === "" ? null : Number(delay.value);
    for (const field of pack.config_fields ?? []) {
      if (field.type !== "number") continue;
      const input = this.shadowRoot.querySelector(`#auto-${pack.id}-${field.id}`);
      if (input && this._automaticMapDraft?.[pack.id]) {
        this._automaticMapDraft[pack.id][field.id] = Number(input.value);
      }
    }
  }
}

export function refreshAutomaticConfigurationDrawer() {
  const form = this.shadowRoot?.querySelector?.("#automatic-form");
  if (!form) {
    this._render();
    return;
  }
  replaceConfigurationDrawer(form, renderAutomaticConfigurationDrawer({
    availablePacks: this._packs.filter((pack) => pack.available),
    config: this._config,
    draft: this._automaticMapDraft,
    configurationDrawer: this._configurationDrawer,
    busy: this._busy,
    useBottomSheet: this._useNativeBottomSheet(),
    renderNumberField: (...args) => this._numberField(...args),
    t: (key, replacements) => this._t(key, replacements),
  }));
  this._hydrateSelectors();
  this._decorateActionIcons();
}

export function updateAutomaticConfigurationCount(packId) {
  const pack = this._packs.find((item) => item.id === packId);
  if (!pack) return;
  const fields = drawerFields(pack);
  fields.forEach((field) => {
    const button = this.shadowRoot?.querySelector?.(
      `#auto-${packId}-${field.id}-configuration`,
    );
    if (!button) return;
    const count = fieldConfigurationCount(
      pack, field, this._config.automatic[pack.id], this._automaticMapDraft,
    );
    button.textContent = fields.length === 1
      ? this._t("buttons.configuration", { count })
      : this._t("buttons.configuration_named", {
        name: this._t(`automatic.fields.${field.translation_key}.label`), count,
      });
  });
}

export function hydrateAutomaticControls() {
  this._ensureAutomaticDraft();
  for (const pack of this._packs.filter((item) => item.available)) {
    const draft = this._automaticMapDraft[pack.id];
    this._configureSelector(
      `auto-${pack.id}-labels`,
      { label: { multiple: true } },
      draft.label_ids,
      (value) => {
        draft.label_ids = this._multipleSelectorValue(value, draft.label_ids);
        this._markConfigurationDirty("automatic");
      },
    );
    const enabled = this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`);
    if (enabled) {
      enabled.onchange = () => {
        this._automaticMapDraft[pack.id].enabled = enabled.checked;
        const configuration = this.shadowRoot.querySelector(
          `[data-pack-configuration="${pack.id}"]`,
        );
        if (configuration) configuration.hidden = !enabled.checked;
      };
    }
    for (const field of pack.config_fields ?? []) {
      if (!MAP_FIELD_TYPES.has(field.type) || field.type === "pack_settings_map") {
        continue;
      }
      const rows = this._automaticMapDraft[pack.id]?.[field.id] ?? [];
      rows.forEach((row, index) => {
        this._configureSelector(
          `auto-${pack.id}-${field.id}-target-${index}`,
          field.type === "entity_number_map"
            ? { entity: field.entity_domains ? { domain: field.entity_domains } : {} }
            : { device: {} },
          row.target_id,
          (value) => { row.target_id = typeof value === "string" ? value : ""; },
        );
      });
    }
  }
  this.shadowRoot.querySelectorAll("[data-pack-source-toggle]").forEach((toggle) => {
    toggle.onchange = () => {
      captureAutomaticMapValues.call(this);
      const sources = this._automaticMapDraft[toggle.dataset.packSourceToggle]?.[
        toggle.dataset.packField
      ];
      const field = this._packs.find(
        (pack) => pack.id === toggle.dataset.packSourceToggle,
      )?.config_fields?.find((item) => item.id === toggle.dataset.packField);
      if (!sources || !field) return;
      if (toggle.checked) {
        sources[toggle.dataset.sourcePackId] ??= Object.fromEntries(
          (field.fields ?? []).map((setting) => [setting.id, null]),
        );
      } else {
        delete sources[toggle.dataset.sourcePackId];
      }
      const values = toggle.closest?.(".pack-source-row")?.querySelector?.(
        "[data-pack-source-values]",
      );
      if (values) values.hidden = !toggle.checked;
    };
  });
}

export async function handleAutomaticAction(action, button) {
  if (action === "save-automatic") {
    const form = this.shadowRoot.querySelector("#automatic-form");
    if (form && this._reportFormValidity(form) && !this._busy) await this._saveAutomatic();
    return true;
  }
  if (action === "open-automatic-configuration") {
    this._ensureAutomaticDraft();
    captureAutomaticConfigurationValues.call(this);
    this._configurationDrawer = {
      kind: "automatic",
      id: button.dataset.packId,
      fieldId: button.dataset.fieldId,
    };
    refreshAutomaticConfigurationDrawer.call(this);
    return true;
  }
  if (
    action === "close-configuration-drawer"
    && this._configurationDrawer?.kind === "automatic"
  ) {
    const packId = this._configurationDrawer.id;
    captureAutomaticConfigurationValues.call(this);
    this._configurationDrawer = null;
    refreshAutomaticConfigurationDrawer.call(this);
    updateAutomaticConfigurationCount.call(this, packId);
    return true;
  }
  if (action === "add-pack-map-row") {
    this._ensureAutomaticDraft();
    captureAutomaticConfigurationValues.call(this);
    const rows = this._automaticMapDraft[button.dataset.packId]?.[button.dataset.fieldId];
    const field = this._packs.find((pack) => pack.id === button.dataset.packId)
      ?.config_fields?.find((item) => item.id === button.dataset.fieldId);
    if (rows) {
      if (field?.type === "device_settings_map") {
        rows.push({
          target_id: "",
          ...Object.fromEntries((field.fields ?? []).map(
            (setting) => [setting.id, setting.default],
          )),
        });
      } else {
        const minimum = Number(field?.minimum ?? -1000000000);
        const maximum = Number(field?.maximum ?? 1000000000);
        rows.push({ target_id: "", value: Math.min(maximum, Math.max(minimum, 0)) });
      }
      this._markConfigurationDirty("automatic");
    }
    refreshAutomaticConfigurationDrawer.call(this);
    return true;
  }
  if (action === "remove-pack-map-row") {
    captureAutomaticConfigurationValues.call(this);
    const rows = this._automaticMapDraft?.[button.dataset.packId]?.[button.dataset.fieldId];
    rows?.splice(Number(button.dataset.index), 1);
    this._markConfigurationDirty("automatic");
    refreshAutomaticConfigurationDrawer.call(this);
    return true;
  }
  return false;
}
