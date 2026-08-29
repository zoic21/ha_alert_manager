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
    .table-page-top{display:flow-root}
    .rule-editor-actions{flex-wrap:wrap}
    .rule-editor-error{flex:1 0 100%;width:100%;margin:0 0 4px}
  `;
};

const NARROW_TABLE_HEADER_STYLE_ID = "alert-manager-narrow-table-header-style";
const TABLE_PAGE_SELECTORS = [
  '[data-alert-table-page="overview"]',
  '[data-alert-table-page="history"]',
  "[data-rules-table-page]",
  "[data-coherence-table-page]",
];

AlertManagerPanel.prototype._syncNarrowTableHeaderBackgrounds = function() {
  for (const selector of TABLE_PAGE_SELECTORS) {
    const root = this.shadowRoot?.querySelector?.(selector)?.shadowRoot;
    if (!root || root.querySelector?.(`#${NARROW_TABLE_HEADER_STYLE_ID}`)) continue;

    const style = document.createElement("style");
    style.id = NARROW_TABLE_HEADER_STYLE_ID;
    style.textContent = `
      :host([narrow]) .narrow-header-row {
        background: var(--primary-background-color);
        border-bottom: 1px solid var(--divider-color);
        box-sizing: border-box;
      }
    `;
    root.append(style);
  }
};

const baseHydrateDataTables = AlertManagerPanel.prototype._hydrateDataTables;
AlertManagerPanel.prototype._hydrateDataTables = function() {
  baseHydrateDataTables.call(this);
  this._syncNarrowTableHeaderBackgrounds();
};

AlertManagerPanel.prototype._clearRuleEditorError = function() {
  this._ruleEditorError = null;
  this.shadowRoot?.querySelector?.(".rule-editor-error")?.remove?.();
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
  const wrappedOnChange = id.startsWith("rule-")
    ? (nextValue) => {
      this._clearRuleEditorError();
      onChange?.(nextValue);
      if (id === "rule-entity-ids") this._refreshRuleAttributeSelector();
    }
    : onChange;
  return baseConfigureSelector.call(this, id, selector, value, wrappedOnChange);
};

const baseConfigureSelect = AlertManagerPanel.prototype._configureSelect;
AlertManagerPanel.prototype._configureSelect = function(id, options, value, onChange) {
  const wrappedOnChange = id.startsWith("rule-")
    ? (nextValue) => {
      this._clearRuleEditorError();
      onChange?.(nextValue);
      if (id === "rule-source") this._refreshRuleAttributeSelector();
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
  if (this._ruleEditorMode === "visual" && this._ruleEditorError) {
    markup = markup.replace(
      '<div class="actions rule-editor-actions">',
      `<div class="actions rule-editor-actions"><ha-alert class="rule-editor-error" alert-type="error" role="alert">${escapeHtml(this._ruleEditorError)}</ha-alert>`,
    );
  }
  return markup;
};

const baseHandleRuleInput = AlertManagerPanel.prototype._handleRuleInput;
AlertManagerPanel.prototype._handleRuleInput = function(event) {
  if (event.target?.closest?.("#rule-form")) this._clearRuleEditorError();
  return baseHandleRuleInput.call(this, event);
};

const baseSaveRule = AlertManagerPanel.prototype._saveRule;
AlertManagerPanel.prototype._saveRule = async function(form) {
  this._clearRuleEditorError();
  await baseSaveRule.call(this, form);
  if (this._editingRule !== null && this._notice?.kind === "error") {
    this._ruleEditorError = this._notice.text;
    this._notice = null;
    this._refreshRuleEditor();
  }
};

const baseCancelRuleEditor = AlertManagerPanel.prototype._cancelRuleEditor;
AlertManagerPanel.prototype._cancelRuleEditor = function() {
  const result = baseCancelRuleEditor.call(this);
  if (this._editingRule === null) this._clearRuleEditorError();
  return result;
};

const baseSwitchRuleEditor = AlertManagerPanel.prototype._switchRuleEditor;
AlertManagerPanel.prototype._switchRuleEditor = async function() {
  this._clearRuleEditorError();
  return baseSwitchRuleEditor.call(this);
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
  this._ruleEditorError = null;
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
