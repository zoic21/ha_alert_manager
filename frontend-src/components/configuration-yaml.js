import { esc } from "../utils/escaping.js";
import { MDI_DOTS_VERTICAL } from "../utils/constants.js";

export function configurationDrawerForTab(panel, activeTab) {
  const drawer = panel._configurationDrawer;
  // Other tabs may be visited while editing. Keep the raw text, including invalid
  // YAML, until Configuration is shown again; never silently fall back to rows.
  if (["settings", "automatic"].includes(drawer?.kind) && drawer.mode === "yaml") {
    panel._suspendedConfigurationYamlDrawer = drawer;
  }
  if (activeTab !== "settings") return null;
  const resumed = panel._suspendedConfigurationYamlDrawer ?? null;
  panel._suspendedConfigurationYamlDrawer = null;
  return resumed;
}

export function renderConfigurationYamlMenu(drawer, t) {
  return `<ha-dropdown slot="actionItems" data-configuration-yaml-menu size="m" placement="bottom-end"><ha-icon-button slot="trigger" aria-label="${esc(t("rules.aria_menu"))}" title="${esc(t("rules.aria_menu"))}"><ha-svg-icon path="${MDI_DOTS_VERTICAL}"></ha-svg-icon></ha-icon-button><ha-dropdown-item value="switch-editor"><ha-icon slot="icon" icon="mdi:playlist-edit"></ha-icon>${esc(t(drawer.mode === "yaml" ? "rules.edit_visually" : "rules.edit_yaml"))}</ha-dropdown-item></ha-dropdown>`;
}

export function renderConfigurationYamlContent(drawer, visualContent, t) {
  if (drawer.mode !== "yaml") return visualContent;
  return `<section class="yaml-rule-section"><small>${esc(t("settings.yaml_help"))}</small><ha-code-editor id="configuration-yaml-editor" mode="yaml" aria-label="${esc(t("rules.edit_yaml"))}"></ha-code-editor></section>`;
}

// Keep the same mapping representation as configuration export/import. Only the
// visual list widgets need conversion; pack source maps already use that shape.
export function configurationValueToDraft(value, fieldType) {
  if (fieldType === "entity_delays") {
    return Object.entries(value).map(([entity_id, delay]) => ({ entity_id, delay }));
  }
  if (["entity_number_map", "device_number_map"].includes(fieldType)) {
    return Object.entries(value).map(([target_id, value]) => ({ target_id, value }));
  }
  if (["entity_settings_map", "device_settings_map"].includes(fieldType)) {
    return Object.entries(value).map(([target_id, settings]) => ({ target_id, ...settings }));
  }
  return structuredClone(value);
}

export function configurationDraftToValue(draft, fieldType) {
  const isDelay = fieldType === "entity_delays";
  const isNumber = ["entity_number_map", "device_number_map"].includes(fieldType);
  const isSettings = ["entity_settings_map", "device_settings_map"].includes(fieldType);
  if (!isDelay && !isNumber && !isSettings) return structuredClone(draft);
  const entries = [];
  const seen = new Set();
  for (const row of draft) {
    const key = isDelay ? row.entity_id : row.target_id;
    if (!key || seen.has(key)) throw new Error("configuration_rows_invalid");
    seen.add(key);
    const { target_id, ...settings } = row;
    entries.push([key, isDelay ? row.delay : isNumber ? row.value : settings]);
  }
  return Object.fromEntries(entries);
}

export function configurationFieldToYaml(fieldId, value) {
  const mapping = (data, indent = "") => Object.entries(data).map(([key, item]) => {
    const prefix = `${indent}${JSON.stringify(key)}:`;
    return item && !Array.isArray(item) && typeof item === "object" && Object.keys(item).length
      ? `${prefix}\n${mapping(item, `${indent}  `)}`
      : `${prefix} ${JSON.stringify(item)}`;
  }).join("\n");
  return `${mapping({ [fieldId]: value })}\n`;
}

function convertAutomaticFields(fields, value, toDraft) {
  const result = structuredClone(value ?? {});
  for (const field of fields ?? []) {
    const item = value?.[field.id] ?? field.default;
    if (field.type === "pack_settings_map") {
      result[field.id] = Object.fromEntries(Object.entries(item ?? {}).map(([id, settings]) => [id, convertAutomaticFields(field.fields, settings, toDraft)]));
    } else if (field.type.endsWith("_settings_map")) {
      result[field.id] = toDraft ? configurationValueToDraft(item ?? {}, field.type) : configurationDraftToValue(item ?? [], field.type);
    }
  }
  return result;
}

export function automaticPackToDraft(pack, value) {
  return convertAutomaticFields(pack.config_fields, value, true);
}

export function automaticDraftToPack(pack, draft) {
  return convertAutomaticFields(pack.config_fields, draft, false);
}

function configurationFieldContext(panel) {
  const drawer = panel._configurationDrawer;
  if (drawer?.kind === "automatic") {
    const pack = panel._packs.find((pack) => pack.id === drawer.id);
    return {
      fieldId: "pack", fieldType: "pack",
      draft: automaticDraftToPack(pack, panel._automaticMapDraft[drawer.id]),
      apply: (value) => { panel._automaticMapDraft[drawer.id] = automaticPackToDraft(pack, value); },
    };
  }
  return {
    fieldId: drawer.id,
    fieldType: drawer.id,
    draft: drawer.id === "entity_delays" ? panel._entityDelayDraft : panel._settingsDraft[drawer.id],
    apply: (value) => {
      if (drawer.id === "entity_delays") panel._entityDelayDraft = value;
      else panel._settingsDraft[drawer.id] = value;
    },
  };
}

function refreshConfigurationYamlDrawer(panel) {
  if (panel._configurationDrawer?.kind === "automatic") panel._refreshAutomaticConfigurationDrawer();
  else panel._refreshSettingsConfigurationDrawer();
}

export async function validateConfigurationYaml(panel) {
  const drawer = panel._configurationDrawer;
  if (!["settings", "automatic"].includes(drawer?.kind) || drawer.mode !== "yaml") return true;
  if (panel._busy) return false;
  const yaml = drawer.yaml;
  const context = configurationFieldContext(panel);
  panel._busy = true;
  panel._refreshUiState();
  try {
    const result = await panel._api.call({
      type: "alert_manager/config/field/yaml/validate",
      field_id: context.fieldId,
      ...(drawer.kind === "automatic" ? { pack_id: drawer.id } : {}),
      yaml,
    });
    if (panel._configurationDrawer !== drawer || drawer.yaml !== yaml) return false;
    context.apply(configurationValueToDraft(result.value, context.fieldType));
    drawer.notice = null;
    return true;
  } catch (error) {
    if (panel._configurationDrawer === drawer && drawer.yaml === yaml) {
      const detail = error?.message ?? error?.body?.message ?? panel._errorText(error);
      drawer.notice = { kind: "error", text: panel._t("settings.yaml_invalid", { error: detail }) };
    }
    return false;
  } finally {
    panel._busy = false;
    panel._refreshUiState();
  }
}

export async function switchConfigurationYaml(panel) {
  if (panel._busy) return;
  const drawer = panel._configurationDrawer;
  if (drawer.mode === "yaml") {
    if (!await validateConfigurationYaml(panel)) return;
    drawer.mode = "visual";
  } else {
    panel._captureAutomaticConfigurationValues();
    panel._captureEntityDelayValues();
    const context = configurationFieldContext(panel);
    try {
      drawer.yaml = configurationFieldToYaml(context.fieldId,
        configurationDraftToValue(context.draft, context.fieldType));
    } catch (_error) {
      drawer.notice = { kind: "error", text: panel._t("settings.yaml_rows_invalid") };
      panel._refreshUiState();
      return;
    }
    drawer.yamlOriginal = drawer.yaml;
    drawer.mode = "yaml";
    drawer.notice = null;
  }
  refreshConfigurationYamlDrawer(panel);
}

export function hydrateConfigurationYaml(panel) {
  const drawer = panel._configurationDrawer;
  if (!["settings", "automatic"].includes(drawer?.kind)) return;
  const menu = panel.shadowRoot?.querySelector?.("[data-configuration-yaml-menu]");
  if (menu && !menu.dataset.configured) {
    menu.addEventListener("wa-select", (event) => {
      event.stopPropagation();
      if (event.detail?.item?.value === "switch-editor") void switchConfigurationYaml(panel);
    });
    menu.dataset.configured = "true";
  }
  const editor = panel.shadowRoot?.querySelector?.("#configuration-yaml-editor");
  if (editor) {
    editor.hass = panel._hass;
    editor.value = drawer.yaml;
    editor.lineNumbers = true;
    if (!editor.dataset.configured) {
      editor.addEventListener("value-changed", (event) => {
        if (panel._configurationDrawer !== drawer) return;
        const yaml = String(event.detail?.value ?? editor.value ?? "");
        if (yaml === drawer.yaml) return;
        drawer.yaml = yaml;
        drawer.notice = null;
        panel._markConfigurationDirty(drawer.kind);
        panel._refreshUiState();
      });
      editor.dataset.configured = "true";
    }
  }
}
