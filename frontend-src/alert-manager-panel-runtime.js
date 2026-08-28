const entryModuleUrl = new URL("./alert-manager-panel-entry.js", import.meta.url);
entryModuleUrl.search = new URL(import.meta.url).search;
await import(entryModuleUrl.href);

const panelModuleUrl = new URL("./alert-manager-panel.js", import.meta.url);
panelModuleUrl.search = new URL(import.meta.url).search;
const { AlertManagerPanel } = await import(panelModuleUrl.href);

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const duplicateLabel = (panel) => panel._hass?.localize?.(
  "ui.panel.config.automation.editor.duplicate",
) || (String(panel._language ?? "").toLowerCase().startsWith("fr") ? "Dupliquer" : "Duplicate");

const baseRenderRuleEditor = AlertManagerPanel.prototype._renderRuleEditor;
AlertManagerPanel.prototype._renderRuleEditor = function() {
  let markup = baseRenderRuleEditor.call(this);
  markup = markup.replace(
    '<ha-dropdown-item value="switch-editor">',
    '<ha-dropdown-item value="switch-editor"><ha-icon slot="icon" icon="mdi:playlist-edit"></ha-icon>',
  );
  if (this._editingRule?.id) {
    markup = markup.replace(
      '<ha-dropdown-item value="delete-rule">',
      `<ha-dropdown-item value="duplicate-rule"><ha-icon slot="icon" icon="mdi:plus-circle-multiple-outline"></ha-icon>${escapeHtml(duplicateLabel(this))}</ha-dropdown-item><ha-dropdown-item value="delete-rule" variant="danger"><ha-icon slot="icon" icon="mdi:delete"></ha-icon>`,
    );
  }
  return markup;
};

AlertManagerPanel.prototype._duplicateRuleDraft = async function() {
  if (!this._editingRule?.id) return;

  if (this._ruleEditorMode === "yaml") {
    await this._switchRuleEditor();
    if (this._ruleEditorMode !== "visual" || !this._editingRule?.id) return;
  } else {
    this._captureRuleDraft();
  }

  const source = this._editingRule;
  const duplicate = {
    ...source,
    name: "",
    entity_ids: [...(source.entity_ids ?? [])],
    value: Array.isArray(source.value) ? [...source.value] : source.value,
  };
  delete duplicate.id;

  this._editingRule = duplicate;
  this._ruleEditorMode = "visual";
  this._ruleYaml = "";
  this._ruleYamlError = null;
  this._ruleDirty = true;
  this._refreshRuleEditor();
};

const baseHandleSelected = AlertManagerPanel.prototype._handleSelected;
AlertManagerPanel.prototype._handleSelected = async function(event) {
  const path = event.composedPath?.() ?? [event.target];
  const ruleMenu = path.find((node) => node?.dataset?.ruleEditorMenu !== undefined);
  const value = event.detail?.item?.value ?? event.detail?.value;
  if (ruleMenu && value === "duplicate-rule") {
    await this._duplicateRuleDraft();
    return;
  }
  await baseHandleSelected.call(this, event);
};
