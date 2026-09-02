import { MDI_PLUS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import {
  renderConfigurationDrawer,
  replaceConfigurationDrawer,
} from "../components/configuration-drawer.js";

const NUMBER_MAP_FIELD_TYPES = new Set(["device_number_map", "entity_number_map"]);

function isNumberMapField(field) {
  return NUMBER_MAP_FIELD_TYPES.has(field.type);
}

function drawerFields(pack) {
  return (pack.config_fields ?? []).filter(isNumberMapField);
}

export function renderAutomatic(context) {
    const {
      availablePacks, config, draft, configurationDrawer, busy, renderNumberField, t,
    } = context;
    return `<form id="automatic-form" class="automatic-grid">
      ${availablePacks.map((pack) => {
        const packConfig = config.automatic[pack.id];
        const packKey = pack.translation_key || pack.id;
        const packName = t(`packs.${packKey}.name`);
        const configurableFields = drawerFields(pack);
        return `<ha-card outlined class="panel category-card">
          <div class="category-header">
            <h2>${esc(packName)}</h2>
            <ha-switch id="auto-${pack.id}-enabled" aria-label="${esc(t("automatic.aria_enable", { name: packName }))}" ${packConfig.enabled ? "checked" : ""}></ha-switch>
          </div>
          <p>${esc(t(`packs.${packKey}.description`))}</p>
          <div class="fields">
            ${renderNumberField(`auto-${pack.id}-delay`, t("automatic.pack_delay"), packConfig.delay, t("units.seconds"), 0, 31536000, { required: false, help: t("automatic.empty_delay_help") })}
            ${(pack.config_fields ?? []).filter((field) => field.type === "number").map((field) => renderPackField(
              pack,
              field,
              packConfig,
              { draft, renderNumberField, t },
            )).join("")}
          </div>
          ${configurableFields.length ? `<div class="configuration-entry automatic-configuration-entry"><ha-button id="auto-${pack.id}-configuration" appearance="plain" data-action="open-automatic-configuration" data-pack-id="${esc(pack.id)}" aria-label="${esc(t("automatic.configure_aria", { name: packName }))}">${esc(t("buttons.configuration", { count: packConfigurationCount(pack, packConfig, draft) }))}</ha-button></div>` : ""}
        </ha-card>`;
      }).join("")}
      <div class="actions automatic-actions"><ha-button appearance="accent" variant="brand" data-action="save-automatic" ${busy ? "disabled" : ""}>${esc(t("automatic.save"))}</ha-button></div>
      ${renderAutomaticConfigurationDrawer({
        availablePacks, config, draft, configurationDrawer, busy, renderNumberField, t,
      })}
    </form>`;
}

export function renderAutomaticPanel() {
    this._ensureAutomaticDraft();
    return renderAutomatic({
      availablePacks: this._packs.filter((pack) => pack.available),
      config: this._config,
      draft: this._automaticMapDraft,
      configurationDrawer: this._configurationDrawer,
      busy: this._busy,
      renderNumberField: (...args) => this._numberField(...args),
      t: (key, replacements) => this._t(key, replacements),
    });
}

export function packConfigurationCount(pack, config, draft) {
  return drawerFields(pack).reduce((count, field) => {
    const rows = draft?.[pack.id]?.[field.id];
    return count + (rows
      ? rows.filter((row) => row.target_id).length
      : Object.keys(config[field.id] ?? {}).length);
  }, 0);
}

export function renderAutomaticConfigurationDrawer(context) {
  const {
    availablePacks, config, draft, configurationDrawer, busy, renderNumberField, t,
  } = context;
  if (configurationDrawer?.kind !== "automatic") return "";
  const pack = availablePacks.find((item) => item.id === configurationDrawer.id);
  const configurableFields = pack ? drawerFields(pack) : [];
  if (!configurableFields.length) return "";
  const packConfig = config.automatic[pack.id];
  const packName = t(`packs.${pack.translation_key || pack.id}.name`);
  const content = `<div class="fields configuration-drawer-fields">${configurableFields
    .map((field) => renderPackField(
      pack,
      field,
      packConfig,
      { draft, renderNumberField, t },
    )).join("")}</div>`;
  return renderConfigurationDrawer({
    title: packName,
    ariaLabel: t("automatic.close_configuration_aria", { name: packName }),
    content,
    saveAction: "save-automatic",
    saveLabel: t("buttons.save"),
    busy,
  });
}

export function renderPackField(pack, field, config, context) {
    const { draft, renderNumberField, t } = context;
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

export async function saveAutomatic() {
    this._ensureAutomaticDraft();
    captureAutomaticConfigurationValues.call(this);
    const automatic = {};
    for (const pack of this._packs.filter((item) => item.available)) {
      const delayValue = this.shadowRoot.querySelector(`#auto-${pack.id}-delay`).value;
      automatic[pack.id] = {
        enabled: this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`).checked,
        delay: delayValue === "" ? null : Number(delayValue),
      };
      for (const field of pack.config_fields ?? []) {
        if (field.type === "number") {
          automatic[pack.id][field.id] = Number(
            this._automaticMapDraft[pack.id]?.[field.id] ?? field.default,
          );
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
            return;
          }
          if (Object.hasOwn(values, row.target_id)) {
            this._notice = {
              kind: "error",
              text: this._t(
                `automatic.fields.${field.translation_key}.duplicate`,
              ),
            };
            this._refreshUiState();
            return;
          }
          values[row.target_id] = row.value;
        }
        automatic[pack.id][field.id] = values;
      }
    }
    const config = await this._call(
      { type: "alert_manager/config/update", config: { automatic } },
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
    }
}

export function resetAutomaticDraft() {
    this._automaticMapDraft = null;
    this._ensureAutomaticDraft();
}

export function ensureAutomaticDraft() {
    if (this._automaticMapDraft || !this._config) return;
    this._automaticMapDraft = {};
    for (const pack of this._packs) {
      const fields = {};
      for (const field of pack.config_fields ?? []) {
        const configured = this._config.automatic?.[pack.id]?.[field.id]
          ?? field.default;
        fields[field.id] = isNumberMapField(field)
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
}

export function captureAutomaticConfigurationValues() {
  captureAutomaticMapValues.call(this);
  for (const pack of this._packs) {
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
    renderNumberField: (...args) => this._numberField(...args),
    t: (key, replacements) => this._t(key, replacements),
  }));
  this._hydrateSelectors();
  this._decorateActionIcons();
}

export function updateAutomaticConfigurationCount(packId) {
  const pack = this._packs.find((item) => item.id === packId);
  const button = this.shadowRoot?.querySelector?.(`#auto-${packId}-configuration`);
  if (!pack || !button) return;
  button.textContent = this._t("buttons.configuration", {
    count: packConfigurationCount(
      pack,
      this._config.automatic[pack.id],
      this._automaticMapDraft,
    ),
  });
}

export function hydrateAutomaticControls() {
  this._ensureAutomaticDraft();
  for (const pack of this._packs.filter((item) => item.available)) {
    for (const field of pack.config_fields ?? []) {
      if (!isNumberMapField(field)) continue;
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
    this._configurationDrawer = { kind: "automatic", id: button.dataset.packId };
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
    const minimum = Number(field?.minimum ?? -1000000000);
    const maximum = Number(field?.maximum ?? 1000000000);
    if (rows) {
      rows.push({ target_id: "", value: Math.min(maximum, Math.max(minimum, 0)) });
    }
    refreshAutomaticConfigurationDrawer.call(this);
    return true;
  }
  if (action === "remove-pack-map-row") {
    captureAutomaticConfigurationValues.call(this);
    const rows = this._automaticMapDraft?.[button.dataset.packId]?.[button.dataset.fieldId];
    rows?.splice(Number(button.dataset.index), 1);
    refreshAutomaticConfigurationDrawer.call(this);
    return true;
  }
  return false;
}
