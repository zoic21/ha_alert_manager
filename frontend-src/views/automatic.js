import { automaticPackToDraft, automaticDraftToPack, hydrateConfigurationYaml, renderConfigurationYamlMenu, renderConfigurationYamlContent, validateConfigurationYaml } from "../components/configuration-yaml.js";
import { durationFieldValue, renderDurationControl } from "../components/duration-field.js";
import { MAX_DURATION_SECONDS, MDI_PLUS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { confirmConfigurationDiscard, renderConfigurationDrawer, renderConfigurationRemove, replaceConfigurationDrawer, revealAddedRow } from "../components/configuration-drawer.js";

const EXCEPTION_FIELDS = ["device_overrides", "entity_overrides"];
const settingFields = (pack) => (pack.config_fields ?? []).filter((field) => ["number", "boolean", "text", "select"].includes(field.type));
const sourceField = (pack) => (pack.config_fields ?? []).find((field) => field.id === "source_packs");
const exceptionCount = (settings) => EXCEPTION_FIELDS.reduce((count, key) => count + (settings?.[key]?.length ?? 0), 0);
const totalExceptions = (settings) => exceptionCount(settings) + Object.values(settings?.source_packs ?? {}).reduce((count, source) => count + exceptionCount(source), 0);
const scopeFor = (draft, sourceId) => sourceId ? draft.source_packs?.[sourceId] : draft;

// Target support is owned by the pack, including a selected flapping source.
function exceptionFields(pack, packs, sourceId = "") {
  const targetPack = packs.find((item) => item.id === sourceId) ?? pack;
  const targets = targetPack.exception_targets ?? ["device", "entity"];
  return (pack.config_fields ?? []).filter((field) => EXCEPTION_FIELDS.includes(field.id)
    && targets.includes(field.id.replace("_overrides", "")));
}

function automaticContext(panel) {
  return {
    availablePacks: panel._packs, config: panel._config, draft: panel._automaticMapDraft,
    configurationDrawer: panel._configurationDrawer, busy: panel._busy,
    useBottomSheet: panel._useNativeBottomSheet(), hass: panel._hass,
    t: (key, replacements) => panel._t(key, replacements),
  };
}

function formatSetting(value, field, t) {
  if (field.type === "boolean") return t(field.id === "enabled" ? value ? "automatic.monitoring_enabled" : "automatic.monitoring_disabled" : value ? "automatic.boolean_true" : "automatic.boolean_false");
  if (field.unit === "s") {
    if (value && value % 3600 === 0) return `${value / 3600} ${t("automatic.hours_short")}`;
    if (value && value % 60 === 0) return `${value / 60} ${t("automatic.minutes_short")}`;
  }
  return `${value ?? ""}${field.unit ? ` ${field.unit}` : ""}`;
}

export function renderAutomatic(context) {
  const { availablePacks, draft, t } = context;
  return `<ha-card id="settings-section-automatic" outlined class="panel settings-card automatic-section settings-scroll-section">
    <h2>${esc(t("tabs.automatic"))}</h2><form id="automatic-form" class="automatic-grid">
    ${availablePacks.map((pack) => {
      const settings = draft[pack.id];
      const name = t(`packs.${pack.translation_key || pack.id}.name`);
      const summary = [pack.uses_delay === false ? "" : `${t("automatic.pack_delay")}: ${formatSetting(settings.delay, { unit: "s" }, t)}`, ...settingFields(pack).map((field) => `${t(`automatic.fields.${field.translation_key}.label`)}: ${formatSetting(settings[field.id], field, t)}`)].filter(Boolean).join(" · ");
      return `<section class="category-card automatic-pack-row"><div class="category-header"><h2>${esc(name)}</h2><ha-switch id="auto-${pack.id}-enabled" aria-label="${esc(t("automatic.aria_enable", { name }))}" ${settings.enabled ? "checked" : ""}></ha-switch></div>
        <small>${esc(summary)}</small>${pack.available === false ? `<small>${esc(t("automatic.unavailable_pack"))}</small>` : ""}
        <ha-button appearance="plain" data-action="open-automatic-configuration" data-pack-id="${esc(pack.id)}">${esc(t("buttons.configuration", { count: totalExceptions(settings) }))}</ha-button></section>`;
    }).join("")}</form>${renderAutomaticConfigurationDrawer(context)}</ha-card>`;
}

export function renderAutomaticPanel() {
  this._ensureAutomaticDraft();
  return renderAutomatic(automaticContext(this));
}

// Presentation-only counterpart of the backend field resolver; values are always
// validated and evaluated on the server. Missing fields remain missing in drafts.
export function inheritedPackSetting(draft, fieldId, targetId, kind, sourceId, entities = {}) {
  let value = draft[fieldId];
  let origin = "pack";
  const source = sourceId ? draft.source_packs?.[sourceId] : null;
  if (source?.[fieldId] != null && !(fieldId === "enabled" && value === false)) { value = source[fieldId]; origin = "source"; }
  const deviceId = kind === "entity_overrides" ? entities[targetId]?.device_id : targetId;
  for (const [key, id] of [["device_overrides", deviceId], ["entity_overrides", targetId]]) {
    if (key === "entity_overrides" && kind === "device_overrides") continue;
    for (const [scope, prefix] of [[draft, ""], [source, "source_"]]) {
      // Exclude the field currently edited: its inherited value is its parent.
      if (key === kind && ((!sourceId && scope === draft) || (sourceId && scope === source))) continue;
      const row = scope?.[key]?.find((row) => row.target_id === id);
      if (row && Object.hasOwn(row, fieldId) && !(fieldId === "enabled" && value === false)) { value = row[fieldId]; origin = `${prefix}${key === "device_overrides" ? "device" : "entity"}`; }
    }
  }
  return { value, origin };
}

function targetWarning(pack, row, kind, config, hass, sourceId) {
  const entity = hass?.entities?.[row.target_id];
  const state = hass?.states?.[row.target_id];
  const device = hass?.devices?.[kind === "device_overrides" ? row.target_id : entity?.device_id];
  if (!row.target_id) return null;
  if (kind === "device_overrides" ? !device : !entity && !state) return "automatic.orphan_target";
  const excluded = config?.excluded_labels ?? [];
  if ([...(entity?.labels ?? []), ...(device?.labels ?? [])].some((id) => excluded.includes(id))) return "automatic.blocked_label";
  if (config?.monitoring_enabled === false) return "automatic.blocked_global";
  if (config?.automatic?.[pack.id]?.enabled === false) return "automatic.blocked_source";
  if (pack.available === false || (sourceId && config?.automatic?.[sourceId]?.enabled === false)) return "automatic.blocked_source";
  const filter = pack.target_filter ?? {};
  if (kind === "entity_overrides" && filter.domain && ![].concat(filter.domain).includes(row.target_id.split(".")[0])) return "automatic.inapplicable_target";
  if (kind === "entity_overrides" && filter.device_class && state?.attributes?.device_class && ![].concat(filter.device_class).includes(state.attributes.device_class)) return "automatic.inapplicable_target";
  return null;
}

function renderSetting(field, value, id, attributes, t, sparse = false, disabled = false) {
  if (disabled) attributes = { ...attributes, disabled: "" };
  const label = t(`automatic.fields.${field.translation_key}.label`);
  const attrs = Object.entries(attributes).map(([key, value]) => `${key}="${esc(value)}"`).join(" ");
  if (field.id === "enabled" && attributes["data-pack-setting"]) {
    const label = t("automatic.monitor_target");
    return `<ha-switch id="${id}" ${attrs} aria-label="${esc(label)}" title="${esc(label)}" ${value !== false ? "checked" : ""}></ha-switch>`;
  }
  const control = ["boolean", "select"].includes(field.type)
    ? `<ha-selector id="${id}" ${attrs} aria-label="${esc(label)}"></ha-selector>`
    : field.type === "text"
      ? `<ha-input id="${id}" type="text" value="${esc(value ?? "")}" ${attrs} aria-label="${esc(label)}"></ha-input>`
    : field.unit === "s"
      ? renderDurationControl(id, label, value ?? "", field.minimum ?? 0, field.maximum ?? MAX_DURATION_SECONDS, { attributes, required: !sparse })
      : `<ha-input id="${id}" type="number" value="${esc(value ?? "")}" min="${field.minimum ?? -1000000000}" max="${field.maximum ?? 1000000000}" step="${field.step ?? "any"}" ${attrs} ${!sparse ? "required" : ""} aria-label="${esc(label)}">${field.unit ? `<span slot="end">${esc(field.unit)}</span>` : ""}</ha-input>`;
  return `<div class="field pack-setting-field"><span class="field-label">${esc(label)}</span>${control}</div>`;
}

function exceptionSummary(row, fields, blocked, t) {
  const enabled = row.enabled !== false && !blocked;
  return [t(enabled ? "automatic.monitoring_enabled" : "automatic.monitoring_disabled"),
    ...(enabled ? fields.filter((field) => field.id !== "enabled" && row[field.id] != null)
      .map((field) => `${t(`automatic.fields.${field.translation_key}.label`)}: ${formatSetting(row[field.id], field, t)}`) : []),
  ].join(" · ");
}

export function renderPackField(pack, field, config, context) {
  const { draft, configurationDrawer, hass, t } = context;
  const sourceId = configurationDrawer?.sourceId ?? "";
  const scope = scopeFor(draft[pack.id], sourceId);
  if (!EXCEPTION_FIELDS.includes(field.id)) return "";
  const rows = scope?.[field.id] ?? [];
  return `<section class="field full pack-map-field"><div class="configuration-section-heading"><span class="field-label">${esc(t(`automatic.fields.${field.translation_key}.label`))} (${rows.length})</span><ha-button appearance="plain" data-action="add-pack-map-row" data-pack-id="${pack.id}" data-field-id="${field.id}"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button></div>
    ${rows.length ? rows.map((row, index) => {
      const parent = inheritedPackSetting(draft[pack.id], "enabled", row.target_id, field.id, sourceId, hass?.entities);
      const parentBlocked = parent.value === false;
      const warning = (parentBlocked ? parent.origin.includes("device") ? "automatic.blocked_device" : "automatic.blocked_source" : null) ?? targetWarning(sourceId ? context.availablePacks.find((item) => item.id === sourceId) ?? pack : pack, row, field.id, { ...context.config, automatic: draft }, hass, sourceId);
      const blocked = parentBlocked || ["automatic.blocked_source", "automatic.blocked_global", "automatic.blocked_label"].includes(warning);
      const entity = hass?.entities?.[row.target_id];
      const device = hass?.devices?.[row.target_id];
      const name = field.id === "device_overrides" ? device?.name_by_user || device?.name
        : hass?.states?.[row.target_id]?.attributes?.friendly_name || entity?.name || entity?.original_name;
      const title = name || row.target_id || t("automatic.new_exception");
      const expanded = configurationDrawer?.expandedExceptions?.has(row) ?? !row.target_id;
      const renderField = (setting) => renderSetting(setting, row[setting.id], `auto-${pack.id}-${field.id}-${index}-${setting.id}`, { "data-pack-setting": pack.id, "data-pack-field": field.id, "data-pack-index": index, "data-setting-id": setting.id }, t, true, blocked || (setting.id !== "enabled" && row.enabled === false));
      return `<div class="pack-map-row automatic-exception" data-exception-index="${index}">
        <ha-expansion-panel left-chevron data-pack-exception="${field.id}" data-pack-index="${index}" header="${esc(title)}" secondary="${esc(exceptionSummary(row, field.fields, blocked, t))}" ${expanded ? "expanded" : ""}>
          <div slot="icons" class="automatic-exception-actions">
            ${field.fields.filter((setting) => setting.id === "enabled").map(renderField).join("")}
            ${renderConfigurationRemove(t("buttons.remove"), "remove-pack-map-row", { "data-pack-id": pack.id, "data-field-id": field.id, "data-index": index })}
          </div>
          <div class="automatic-exception-content">
            <div class="automatic-exception-target"><ha-selector id="auto-${pack.id}-${field.id}-target-${index}"></ha-selector></div>
            ${warning ? `<ha-alert alert-type="info">${esc(t(warning))}</ha-alert>` : ""}
            <div class="pack-settings-values" ${row.enabled === false || blocked ? "hidden" : ""}>${field.fields.filter((setting) => setting.id !== "enabled").map(renderField).join("")}</div>
          </div>
        </ha-expansion-panel>
      </div>`;
    }).join("") : `<small>${esc(t("automatic.no_exceptions"))}</small>`}</section>`;
}

export function renderAutomaticConfigurationDrawer(context) {
  const { availablePacks, draft, configurationDrawer: drawer, busy, useBottomSheet, t } = context;
  if (drawer?.kind !== "automatic") return "";
  const pack = availablePacks.find((pack) => pack.id === drawer.id);
  if (!pack) return "";
  const settings = draft[pack.id];
  const sourceId = drawer.sourceId ?? "";
  const scope = scopeFor(settings, sourceId);
  const fields = [...(pack.uses_delay === false ? [] : [{ id: "delay", type: "number", translation_key: "trigger_delay", unit: "s", minimum: 0 }]), ...settingFields(pack)];
  const title = t(`packs.${pack.translation_key || pack.id}.name`);
  const content = `<div class="fields configuration-drawer-fields automatic-configuration-fields">
    <ha-expansion-panel left-chevron class="field full automatic-exceptions-help" header="${esc(t("automatic.exceptions_help"))}"><small>${esc(t("automatic.inheritance_help"))}</small></ha-expansion-panel>
    ${sourceField(pack) ? `<div class="field full"><span class="field-label">${esc(t("automatic.source_context"))}</span><ha-selector id="auto-${pack.id}-source-context"></ha-selector></div>` : ""}
    ${sourceId ? `<div class="field full switch-field-row"><span class="field-label">${esc(t("automatic.source_enabled"))}</span><ha-switch id="auto-${pack.id}-source-enabled" aria-label="${esc(t("automatic.source_enabled"))}" ${scope && scope.enabled !== false ? "checked" : ""}></ha-switch></div>` : `<div class="field full"><span class="field-label">${esc(t("automatic.labels"))}</span><ha-selector id="auto-${pack.id}-labels"></ha-selector></div>`}
    ${scope ? `<div class="automatic-pack-settings">${fields.map((field) => renderSetting(field, scope[field.id], `auto-${pack.id}-${field.id}`, { "data-pack-default": pack.id, "data-setting-id": field.id }, t, Boolean(sourceId))).join("")}</div>` + exceptionFields(pack, availablePacks, sourceId).map((field) => renderPackField(pack, field, settings, context)).join("") : ""}
  </div>`;
  return renderConfigurationDrawer({ resizeLabel: t("rules.aria_resize"), title, ariaLabel: t("automatic.close_configuration_aria", { name: title }), headerAction: renderConfigurationYamlMenu(drawer, t), content: renderConfigurationYamlContent(drawer, content, t), saveAction: "save-automatic", saveLabel: t("buttons.save"), busy, useBottomSheet });
}

export function ensureAutomaticDraft() {
  if (this._automaticMapDraft || !this._config) return;
  this._automaticMapDraft = Object.fromEntries(this._packs.map((pack) => [pack.id, automaticPackToDraft(pack, this._config.automatic[pack.id])]));
}
export function resetAutomaticDraft() { this._automaticDirty = false; this._automaticMapDraft = null; this._ensureAutomaticDraft(); }

export function captureAutomaticMapValues() {
  if (!this._automaticMapDraft || this._configurationDrawer?.mode === "yaml") return;
  const sourceId = this._configurationDrawer?.sourceId ?? "";
  this.shadowRoot.querySelectorAll("[data-pack-setting], [data-pack-default]").forEach((input) => {
    if (input.disabled || input.hasAttribute?.("disabled")) return;
    if (input.tagName?.toLowerCase() === "ha-switch") return;
    if (input.tagName?.toLowerCase() === "ha-selector" && input.dataset.durationValue === undefined) return;
    const scope = scopeFor(this._automaticMapDraft[input.dataset.packSetting ?? input.dataset.packDefault], sourceId);
    const row = input.dataset.packField ? scope?.[input.dataset.packField]?.[Number(input.dataset.packIndex)] : scope;
    if (!row) return;
    const value = durationFieldValue(input);
    if (value === "" && input.dataset.packDefault && !sourceId) row[input.dataset.settingId] = null;
    else if (value === "") delete row[input.dataset.settingId];
    else row[input.dataset.settingId] = input.type === "text" ? value : Number(value);
  });
}
export function captureAutomaticConfigurationValues() {
  this._ensureAutomaticDraft();
  if (this._configurationDrawer?.mode === "yaml") return;
  captureAutomaticMapValues.call(this);
  for (const pack of this._packs) {
    const draft = this._automaticMapDraft[pack.id];
    const enabled = this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`);
    if (enabled) draft.enabled = enabled.checked;
    const scope = scopeFor(draft, this._configurationDrawer?.id === pack.id ? this._configurationDrawer.sourceId : "");
    for (const field of [{ id: "delay", type: "number" }, ...settingFields(pack)]) {
      if (!["number", "text"].includes(field.type)) continue;
      const input = this.shadowRoot.querySelector(`#auto-${pack.id}-${field.id}`);
      if (!input || !scope) continue;
      const value = durationFieldValue(input);
      if (value === "" && this._configurationDrawer?.sourceId) delete scope[field.id];
      else scope[field.id] = field.type === "text" ? value : value === "" ? null : Number(value);
    }
  }
}

export function collectAutomaticChanges(allPacks = false) {
  captureAutomaticConfigurationValues.call(this);
  try {
    const activePack = !allPacks && this._configurationDrawer?.kind === "automatic" ? this._configurationDrawer.id : null;
    return { automatic: Object.fromEntries(this._packs.filter((pack) => !activePack || pack.id === activePack).map((pack) => [pack.id, automaticDraftToPack(pack, this._automaticMapDraft[pack.id])])) };
  } catch (_error) {
    this._notice = { kind: "error", text: this._t("settings.yaml_rows_invalid") };
    this._refreshUiState();
    return false;
  }
}

export async function saveAutomatic() {
  if (!await validateConfigurationYaml(this)) return false;
  const changes = collectAutomaticChanges.call(this);
  if (!changes) return false;
  const config = await this._call({ type: "alert_manager/config/update", config: changes }, this._t("success.automatic_saved"));
  if (!config) return false;
  this._config = config;
  for (const pack of this._packs.filter((pack) => Object.hasOwn(changes.automatic, pack.id))) this._automaticMapDraft[pack.id] = automaticPackToDraft(pack, config.automatic[pack.id]);
  this._configurationDrawer = null;
  this._automaticDirty = this._packs.some((pack) => this._automaticMapDraft[pack.id].enabled !== config.automatic[pack.id].enabled);
  this._render();
  return true;
}

export function refreshAutomaticConfigurationDrawer(revealSelector) {
  if (!this.shadowRoot?.querySelector?.("#automatic-form")) { this._render(); return; }
  replaceConfigurationDrawer(this.shadowRoot, renderAutomaticConfigurationDrawer(automaticContext(this)), revealSelector);
  this._hydrateSelectors(); this._decorateActionIcons(); this._refreshUiState();
}
export function updateAutomaticConfigurationCount() { /* Counts refresh with the saved page. */ }

function hydratePackChoice(panel, id, field, values, sparse) {
  if (field.id === "enabled") {
    const control = panel.shadowRoot.querySelector(`#${id}`);
    if (control) control.onchange = () => {
      if (control.disabled || control.hasAttribute?.("disabled")) return;
      captureAutomaticMapValues.call(panel);
      values.enabled = control.checked;
      refreshAutomaticConfigurationDrawer.call(panel);
    };
    return;
  }
  const boolean = field.type === "boolean";
  const options = boolean
    ? [{ value: "enabled", label: panel._t("automatic.boolean_true") }, { value: "disabled", label: panel._t("automatic.boolean_false") }]
    : (field.options ?? []).map((value) => ({ value: JSON.stringify(value), label: value }));
  if (sparse) options.unshift({ value: "inherit", label: panel._t("automatic.inherit") });
  const value = values[field.id] == null ? sparse ? "inherit" : "" : boolean ? values[field.id] ? "enabled" : "disabled" : JSON.stringify(values[field.id]);
  panel._configureSelector(id, { select: { mode: "dropdown", options } }, value, (selected) => {
    captureAutomaticMapValues.call(panel);
    if (selected == null || (sparse && ["", "inherit"].includes(selected))) delete values[field.id];
    else values[field.id] = boolean ? selected === "enabled" : JSON.parse(selected);
  });
}

export function hydrateAutomaticControls() {
  hydrateConfigurationYaml(this);
  this._ensureAutomaticDraft();
  const drawer = this._configurationDrawer;
  for (const pack of this._packs) {
    const draft = this._automaticMapDraft[pack.id];
    const control = this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`);
    if (control) control.onchange = () => {
      captureAutomaticMapValues.call(this);
      draft.enabled = control.checked;
      this._markConfigurationDirty("automatic");
      if (drawer?.kind === "automatic") refreshAutomaticConfigurationDrawer.call(this);
    };
    if (drawer?.kind !== "automatic" || drawer.id !== pack.id || drawer.mode === "yaml") continue;
    const scope = scopeFor(draft, drawer.sourceId);
    this._configureSelector(`auto-${pack.id}-labels`, { label: { multiple: true } }, draft.label_ids, (value) => { draft.label_ids = this._multipleSelectorValue(value, draft.label_ids); });
    this._configureSelector(`auto-${pack.id}-source-context`, { select: { mode: "dropdown", options: [{ value: "all_sources", label: this._t("automatic.all_sources") }, ...this._packs.filter((source) => source.id !== pack.id).map((source) => ({ value: source.id, label: this._t(`packs.${source.translation_key || source.id}.name`) }))] } }, drawer.sourceId || "all_sources", (value) => { captureAutomaticMapValues.call(this); drawer.sourceId = value === "all_sources" ? "" : value; refreshAutomaticConfigurationDrawer.call(this); });
    const sourceEnabled = this.shadowRoot.querySelector(`#auto-${pack.id}-source-enabled`);
    if (sourceEnabled) sourceEnabled.onchange = () => {
      captureAutomaticMapValues.call(this);
      draft.source_packs[drawer.sourceId] ??= { device_overrides: [], entity_overrides: [] };
      draft.source_packs[drawer.sourceId].enabled = sourceEnabled.checked;
      refreshAutomaticConfigurationDrawer.call(this);
    };
    if (scope) {
      for (const setting of settingFields(pack).filter((setting) => ["boolean", "select"].includes(setting.type))) {
        hydratePackChoice(this, `auto-${pack.id}-${setting.id}`, setting, scope, Boolean(drawer.sourceId));
      }
    }
    for (const field of exceptionFields(pack, this._packs, drawer.sourceId)) {
      (scope?.[field.id] ?? []).forEach((row, index) => {
        const expansion = this.shadowRoot.querySelector(`[data-pack-exception="${field.id}"][data-pack-index="${index}"]`);
        if (expansion) {
          const remove = expansion.querySelector('[data-action="remove-pack-map-row"]');
          if (remove) {
            // Keep the delegated delete action, but do not toggle the summary.
            remove.onclick = (event) => event.preventDefault();
            remove.onkeydown = (event) => event.stopPropagation();
          }
          const monitoring = expansion.querySelector("ha-switch[data-pack-setting]");
          if (monitoring) {
            monitoring.onclick = (event) => event.stopPropagation();
            monitoring.onkeydown = (event) => event.stopPropagation();
          }
          drawer.expandedExceptions ??= new WeakSet();
          if (expansion.expanded || expansion.hasAttribute("expanded")) drawer.expandedExceptions.add(row);
          if (expansion._automaticExpansionHandler) expansion.removeEventListener("expanded-changed", expansion._automaticExpansionHandler);
          expansion._automaticExpansionHandler = (event) => {
            if (event.target !== expansion) return;
            if (event.detail.expanded) drawer.expandedExceptions.add(row);
            else {
              drawer.expandedExceptions.delete(row);
              captureAutomaticMapValues.call(this);
              const blocked = expansion.querySelector("ha-switch[data-pack-setting]")?.disabled;
              expansion.secondary = exceptionSummary(row, field.fields, blocked, (key) => this._t(key));
            }
          };
          expansion.addEventListener("expanded-changed", expansion._automaticExpansionHandler);
        }
        const filterPack = this._packs.find((source) => source.id === drawer.sourceId) ?? pack;
        const filter = filterPack.target_filter ?? {};
        this._configureSelector(`auto-${pack.id}-${field.id}-target-${index}`, field.id === "entity_overrides" ? { entity: Object.keys(filter).length ? { filter } : {} } : { device: Object.keys(filter).length ? { entity: filter } : {} }, row.target_id, (value) => { captureAutomaticMapValues.call(this); row.target_id = typeof value === "string" ? value : ""; refreshAutomaticConfigurationDrawer.call(this); });
        for (const setting of field.fields.filter((setting) => ["boolean", "select"].includes(setting.type))) {
          hydratePackChoice(this, `auto-${pack.id}-${field.id}-${index}-${setting.id}`, setting, row, true);
        }
      });
    }
  }
}

export async function handleAutomaticAction(action, button) {
  if (this._readOnly) return false;
  if (action === "save-automatic") {
    const form = this.shadowRoot.querySelector("#automatic-form");
    if (form && this._reportFormValidity(form) && !this._busy) await this._saveAutomatic();
    return true;
  }
  if (action === "open-automatic-configuration") {
    this._ensureAutomaticDraft(); captureAutomaticConfigurationValues.call(this);
    const id = button.dataset.packId;
    if (!this._packs.some((pack) => pack.id === id)) return true;
    this._configurationDrawer = { kind: "automatic", id, fieldId: "pack", sourceId: button.dataset.sourceId ?? "", original: JSON.stringify(this._automaticMapDraft[id]) };
    // A contextual target is a draft only; opening never calls the save API.
    if (button.dataset.entityId) {
      const draft = this._automaticMapDraft[id];
      const sourceId = this._configurationDrawer.sourceId;
      if (sourceId) draft.source_packs[sourceId] ??= { device_overrides: [], entity_overrides: [] };
      const scope = scopeFor(draft, sourceId);
      scope.entity_overrides ??= [];
      let row = scope.entity_overrides.find((row) => row.target_id === button.dataset.entityId);
      if (!row) { row = { target_id: button.dataset.entityId }; scope.entity_overrides.push(row); }
      this._configurationDrawer.expandedExceptions = new WeakSet([row]);
    }
    refreshAutomaticConfigurationDrawer.call(this); return true;
  }
  if (action === "close-configuration-drawer" && this._configurationDrawer?.kind === "automatic") {
    const { id, original } = this._configurationDrawer;
    captureAutomaticConfigurationValues.call(this);
    const restored = JSON.parse(original);
    restored.enabled = this.shadowRoot.querySelector(`#auto-${id}-enabled`)?.checked ?? restored.enabled;
    if (!confirmConfigurationDiscard(this, this._automaticMapDraft[id], JSON.stringify(restored))) return true;
    this._automaticMapDraft[id] = restored;
    this._configurationDrawer = null; this._render(); return true;
  }
  if (!["add-pack-map-row", "remove-pack-map-row"].includes(action)) return false;
  captureAutomaticConfigurationValues.call(this);
  const scope = scopeFor(this._automaticMapDraft[button.dataset.packId], this._configurationDrawer?.sourceId);
  if (!scope || !EXCEPTION_FIELDS.includes(button.dataset.fieldId)) return true;
  const rows = scope[button.dataset.fieldId] ??= [];
  const index = Number(button.dataset.index);
  if (action === "add-pack-map-row") {
    const row = { target_id: "" };
    rows.push(row);
    if (this._configurationDrawer) {
      this._configurationDrawer.expandedExceptions ??= new WeakSet();
      this._configurationDrawer.expandedExceptions.add(row);
    }
  } else if (action === "remove-pack-map-row") rows.splice(index, 1);
  refreshAutomaticConfigurationDrawer.call(this);
  if (action === "add-pack-map-row") revealAddedRow(this.shadowRoot.querySelector(".configuration-drawer"), `[data-pack-exception="${button.dataset.fieldId}"][data-pack-index="${rows.length - 1}"]`);
  return true;
}
