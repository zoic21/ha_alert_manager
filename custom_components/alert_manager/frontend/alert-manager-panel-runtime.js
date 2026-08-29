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

const baseRuntimeStyles = AlertManagerPanel.prototype._styles;
AlertManagerPanel.prototype._styles = function() {
  return `${baseRuntimeStyles.call(this)}
    @media(max-width:700px){.table-page-top{display:flow-root}}
  `;
};

AlertManagerPanel.prototype._ruleAttributeOptions = function() {
  const attributes = new Set();
  for (const entityId of this._editingRule?.entity_ids ?? []) {
    const stateAttributes = this._hass?.states?.[entityId]?.attributes;
    if (!stateAttributes || typeof stateAttributes !== "object") continue;
    for (const attribute of Object.keys(stateAttributes)) attributes.add(attribute);
  }
  return [...attributes].sort();
};

AlertManagerPanel.prototype._refreshRuleAttributeSelector = function() {
  const element = this.shadowRoot?.querySelector?.("#rule-attribute");
  if (!element) return;
  element.hass = this._hass;
  element.selector = {
    select: {
      options: this._ruleAttributeOptions(),
      custom_value: true,
      mode: "dropdown",
    },
  };
  element.value = this._editingRule?.attribute ?? "";
};

const baseConfigureSelector = AlertManagerPanel.prototype._configureSelector;
AlertManagerPanel.prototype._configureSelector = function(id, selector, value, onChange) {
  const wrappedOnChange = id === "rule-entity-ids"
    ? (nextValue) => {
      onChange?.(nextValue);
      this._refreshRuleAttributeSelector();
    }
    : onChange;
  return baseConfigureSelector.call(this, id, selector, value, wrappedOnChange);
};

const baseConfigureSelect = AlertManagerPanel.prototype._configureSelect;
AlertManagerPanel.prototype._configureSelect = function(id, options, value, onChange) {
  const wrappedOnChange = id === "rule-source"
    ? (nextValue) => {
      onChange?.(nextValue);
      this._refreshRuleAttributeSelector();
    }
    : onChange;
  return baseConfigureSelect.call(this, id, options, value, wrappedOnChange);
};

const baseHydrateSelectors = AlertManagerPanel.prototype._hydrateSelectors;
AlertManagerPanel.prototype._hydrateSelectors = function() {
  baseHydrateSelectors.call(this);
  if (this._activeTab !== "rules" || this._ruleEditorMode !== "visual" || !this._editingRule) return;
  this._configureSelector(
    "rule-attribute",
    {
      select: {
        options: this._ruleAttributeOptions(),
        custom_value: true,
        mode: "dropdown",
      },
    },
    this._editingRule.attribute ?? "",
    (value) => {
      this._editingRule.attribute = String(value ?? "");
      this._ruleDirty = true;
    },
  );
};

const baseRenderRuleEditor = AlertManagerPanel.prototype._renderRuleEditor;
AlertManagerPanel.prototype._renderRuleEditor = function() {
  let markup = baseRenderRuleEditor.call(this);
  markup = markup.replace(
    /<ha-input name="attribute"[^>]*><\/ha-input>/,
    '<ha-selector id="rule-attribute" data-field="attribute"></ha-selector>',
  );
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
