import { ATTRIBUTE_RULE_SOURCES, CUSTOM_RULE_EXCLUDED_ENTITY_IDS, MDI_CLOSE, MDI_DOTS_VERTICAL, MDI_PLUS, RANGE_RULE_OPERATORS, TEXT_RULE_OPERATORS, VARIATION_RULE_OPERATORS, VARIATION_RULE_SOURCES } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";
import { newRuleDefaults, ruleToYaml } from "../utils/formatting.js";

export function refreshRuleEditor() {
    const layout = this.shadowRoot?.querySelector(".rules-layout");
    if (!layout || this._activeTab !== "rules") {
      this._render();
      return;
    }
    layout.querySelectorAll(".rule-editor-backdrop,.rule-editor-drawer").forEach((node) => node.remove());
    layout.classList.toggle("has-editor", this._editingRule !== null);
    layout.style.setProperty("--rule-editor-width", `${this._ruleEditorWidth}px`);
    if (this._editingRule !== null) {
      layout.insertAdjacentHTML("beforeend", this._renderRuleEditor());
    }
    this._hydrateSelectors();
    this._hydrateYamlEditor();
}

export function clearRuleEditorError() {
    this._ruleEditorError = null;
    this.shadowRoot?.querySelector?.(".rule-editor-error")?.remove?.();
}

export function ruleAttributeOptions() {
    const attributes = new Set();
    for (const entityId of this._editingRule?.entity_ids ?? []) {
      const stateAttributes = this._hass?.states?.[entityId]?.attributes;
      if (!stateAttributes || typeof stateAttributes !== "object") continue;
      for (const attribute of Object.keys(stateAttributes)) attributes.add(attribute);
    }
    return [...attributes].sort();
}

export function refreshRuleAttributeSelector() {
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
}

export function renderRuleEditor() {
    const rule = { ...newRuleDefaults(), ...(this._editingRule ?? {}) };
    if (rule.source === "none") rule.source = "jinja";
    if (rule.source === "variation") rule.source = "state_variation";
    if (VARIATION_RULE_SOURCES.has(rule.source) && !VARIATION_RULE_OPERATORS.has(rule.operator)) {
      rule.operator = "above";
    }
    if (TEXT_RULE_OPERATORS.has(rule.operator)) {
      rule.value = this._ruleValueList(rule.value);
    } else if (RANGE_RULE_OPERATORS.has(rule.operator)) {
      const bounds = this._ruleValueList(rule.value);
      rule.value = [bounds[0] ?? "", bounds[1] ?? ""];
    } else {
      rule.value = rule.operator === "unchanged"
        ? ""
        : this._ruleValueList(rule.value)[0] ?? "";
    }
    this._editingRule = rule;
    const yamlMode = this._ruleEditorMode === "yaml";
    const editorContent = yamlMode ? this._renderRuleYamlEditor(rule) : this._renderRuleVisualEditor(rule);
    return `<div class="rule-editor-backdrop" data-action="cancel-rule" aria-hidden="true"></div>
    <ha-card outlined class="rule-editor-drawer" role="dialog" aria-modal="false" aria-label="${esc(this._t(rule.id ? "rules.aria_edit_dialog" : "rules.aria_create_dialog"))}">
      <div class="rule-editor-resize" role="separator" aria-orientation="vertical" aria-label="${esc(this._t("rules.aria_resize"))}" tabindex="0"><div class="resize-indicator"></div></div>
      <ha-dialog-header show-border>
        <ha-icon-button id="rule-editor-close" slot="navigationIcon" data-action="cancel-rule"></ha-icon-button>
        <span slot="title">${esc(this._t(rule.id ? "rules.modify" : "rules.create"))}</span>
        ${rule.id ? "" : `<span slot="subtitle">${esc(this._t("rules.new_subtitle"))}</span>`}
        <ha-dropdown slot="actionItems" data-rule-editor-menu size="m" placement="bottom-end"><ha-icon-button slot="trigger" aria-label="${esc(this._t("rules.aria_menu"))}" title="${esc(this._t("rules.aria_menu"))}"><ha-svg-icon path="${MDI_DOTS_VERTICAL}"></ha-svg-icon></ha-icon-button><ha-dropdown-item value="switch-editor"><ha-icon slot="icon" icon="mdi:playlist-edit"></ha-icon>${esc(this._t(yamlMode ? "rules.edit_visually" : "rules.edit_yaml"))}</ha-dropdown-item>${rule.id ? `<ha-dropdown-item value="duplicate-rule"><ha-icon slot="icon" icon="mdi:plus-circle-multiple-outline"></ha-icon>${esc(this._duplicateRuleLabel())}</ha-dropdown-item><ha-dropdown-item value="delete-rule" variant="danger"><ha-icon slot="icon" icon="mdi:delete"></ha-icon>${esc(this._t("buttons.delete"))}</ha-dropdown-item>` : ""}</ha-dropdown>
      </ha-dialog-header>
      <form id="rule-form" class="rule-editor-form">
        ${editorContent}
        <div class="actions rule-editor-actions">${this._ruleEditorMode === "visual" && this._ruleEditorError ? `<ha-alert class="rule-editor-error" alert-type="error" role="alert">${esc(this._ruleEditorError)}</ha-alert>` : ""}<span class="action-spacer"></span><ha-button appearance="accent" variant="brand" data-action="save-rule" ${this._busy ? "disabled" : ""}>${esc(this._t("buttons.save"))}</ha-button></div>
      </form>
    </ha-card>`;
}

export function renderRuleVisualEditor(rule) {
    const jinjaOnly = rule.source === "jinja";
    const variation = VARIATION_RULE_SOURCES.has(rule.source);
    const unchanged = rule.source === "unchanged";
    const comparisonFree = jinjaOnly || unchanged;
    return `
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>${esc(this._t("rules.editor_information"))}</h3><small>${esc(this._t("rules.editor_information_help"))}</small></div></div>
          <div class="fields">
            ${this._textField("name", this._t("rules.name"), rule.name, true, "name", "full")}
            <div class="field full"><span class="field-label">${esc(this._t("rules.entities"))}</span><ha-selector id="rule-entity-ids"></ha-selector><small>${esc(this._t("rules.entities_help"))}</small></div>
          </div>
        </section>
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>${esc(this._t("rules.condition"))}</h3><small>${esc(this._t("rules.editor_condition_help"))}</small></div></div>
          <div class="fields">
            <div class="field"><span class="field-label">${esc(this._t("rules.source"))}</span><ha-select id="rule-source" data-field="source"></ha-select></div>
            <div class="field rule-attribute-field" ${ATTRIBUTE_RULE_SOURCES.has(rule.source) ? "" : "hidden"}><span class="field-label">${esc(this._t("rules.attribute_name"))}</span><ha-selector id="rule-attribute" data-field="attribute"></ha-selector><small>${esc(this._t(rule.source === "attribute_variation" ? "rules.attribute_variation_path_help" : "rules.attribute_path_help"))}</small></div>
            ${comparisonFree ? "" : `<div class="field full"><span class="field-label">${esc(this._t("rules.operator"))}</span><ha-select id="rule-operator" data-field="operator"></ha-select></div>${this._renderRuleValues(rule)}`}
            <div class="field full rule-template-field"><span class="field-label">${esc(this._t(jinjaOnly ? "rules.condition_template_only" : variation ? "rules.condition_template_variation" : "rules.condition_template"))}</span><ha-selector id="rule-condition-template" ${jinjaOnly || variation ? 'required aria-required="true"' : ""}></ha-selector><small>${esc(this._t(jinjaOnly ? "rules.condition_template_only_help" : variation ? "rules.condition_template_variation_help" : unchanged ? "rules.condition_template_unchanged_help" : rule.operator === "unchanged" ? "rules.condition_template_selected_unchanged_help" : "rules.condition_template_help"))}</small></div>
          </div>
        </section>
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>${esc(this._t("rules.editor_trigger"))}</h3><small>${esc(this._t("rules.editor_trigger_help"))}</small></div></div>
          <div class="fields">
            ${this._numberField("duration", this._t("rules.duration"), rule.duration, this._t("units.seconds"), 0, 31536000, { nameMode: "name" })}
            <div class="field full rule-message-field"><span class="field-label">${esc(this._t("rules.message_optional"))}</span><ha-selector id="rule-message-template"></ha-selector><small>${esc(this._t("rules.message_help"))}</small></div>
            <div class="field full"><div class="switch-field-row"><span class="field-label">${esc(this._t("rules.update_message_when_active"))}</span><ha-switch id="rule-update-message-when-active" name="update_message_when_active" aria-label="${esc(this._t("rules.update_message_when_active"))}" ${rule.update_message_when_active ? "checked" : ""}></ha-switch></div><small>${esc(this._t("rules.update_message_when_active_help"))}</small></div>
          </div>
        </section>`;
}

export function renderRuleYamlEditor(rule) {
    if (!this._ruleYaml) this._ruleYaml = ruleToYaml(rule);
    return `<section class="rule-editor-section yaml-rule-section">
      <div class="rule-section-heading"><div><h3>${esc(this._t("rules.yaml_title"))}</h3><small>${esc(this._t("rules.yaml_help"))}</small></div></div>
      <ha-code-editor id="rule-yaml-editor" mode="yaml" aria-label="${esc(this._t("rules.yaml_title"))}"></ha-code-editor>
      ${this._ruleYamlError ? `<div class="yaml-error" role="alert">${esc(this._ruleYamlError)}</div>` : ""}
    </section>`;
}

export function renderRuleValues(rule) {
    if (rule.operator === "unchanged") return "";
    if (RANGE_RULE_OPERATORS.has(rule.operator)) {
      const bounds = this._ruleValueList(rule.value);
      return `<div class="field"><span class="field-label">${esc(this._t("rules.lower_bound"))}</span><ha-input data-field="lower-bound" type="number" step="any" value="${esc(bounds[0] ?? "")}" required aria-label="${esc(this._t("rules.lower_bound"))}"></ha-input></div><div class="field"><span class="field-label">${esc(this._t("rules.upper_bound"))}</span><ha-input data-field="upper-bound" type="number" step="any" value="${esc(bounds[1] ?? "")}" required aria-label="${esc(this._t("rules.upper_bound"))}"></ha-input></div>`;
    }
    if (!TEXT_RULE_OPERATORS.has(rule.operator)) {
      return `<div class="field full"><span class="field-label">${esc(this._t("rules.value"))}</span><ha-input data-field="value" name="value" type="number" step="any" value="${esc(rule.value)}" required aria-label="${esc(this._t("rules.value"))}"></ha-input></div>`;
    }
    const values = this._ruleValueList(rule.value);
    const multipleHint = rule.operator === "equals" || rule.operator === "contains"
      ? this._t("rules.multiple_any")
      : this._t("rules.multiple_none");
    return `<div class="field full rule-values-field"><span class="field-label">${esc(this._t("rules.values"))}</span><div class="rule-value-list">
      ${values.map((value, index) => `<div class="rule-value-row"><ha-input data-rule-value-index="${index}" type="text" value="${esc(value)}" required aria-label="${esc(this._t("rules.aria_value", { index: index + 1 }))}"></ha-input>${values.length > 1 ? `<ha-button appearance="plain" variant="danger" data-action="remove-rule-value" data-index="${index}" aria-label="${esc(this._t("rules.aria_remove_value", { index: index + 1 }))}">${esc(this._t("buttons.remove"))}</ha-button>` : ""}</div>`).join("")}
    </div><div class="rule-value-footer"><small>${esc(multipleHint)}</small><ha-button appearance="plain" data-action="add-rule-value"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(this._t("buttons.add"))}</ha-button></div></div>`;
}

export function ruleValueList(value) {
    return (Array.isArray(value) ? value : [value ?? ""]).map((item) => String(item));
}

export function ruleSummary(rule) {
    if (rule.source === "jinja") return this._t("conditions.rule.jinja", { duration: "" });
    if (rule.source === "unchanged") {
      return this._t("conditions.rule.unchanged", { duration: "" });
    }
    const source = rule.source === "attribute"
      ? this._t("conditions.sources.attribute", { attribute: rule.attribute })
      : rule.source === "attribute_variation"
      ? this._t("conditions.sources.attribute_variation", { attribute: rule.attribute })
      : ["state_variation", "variation"].includes(rule.source)
      ? this._t("conditions.sources.state_variation")
      : this._t("conditions.sources.state");
    if (rule.operator === "unchanged") {
      return this._t("conditions.rule.selected_unchanged", { source, duration: "" });
    }
    const expected = this._ruleValueList(rule.value).join(" / ");
    return `${source} ${this._t(`operators.${rule.operator}`)} ${expected}`;
}

export function duplicateRuleLabel() {
    return this._hass?.localize?.("ui.panel.config.automation.editor.duplicate")
      || (String(this._language).toLowerCase().startsWith("fr") ? "Dupliquer" : "Duplicate");
}

export async function duplicateRuleDraft() {
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
}

export function handleRuleInput(event) {
    if (this._editingRule === null) return;
    const target = event.target;
    if (target?.closest?.("#rule-form")) {
      this._clearRuleEditorError();
      this._ruleDirty = true;
    }
    if (target?.id === "rule-yaml-editor") {
      this._ruleYaml = String(target.value ?? this._ruleYaml);
      this._ruleYamlError = null;
    }
}

export function cancelRuleEditor() {
    if (this._ruleDirty && !window.confirm(this._t("rules.discard_confirm"))) return;
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleDirty = false;
    this._clearRuleEditorError();
    this._refreshRuleEditor();
}

export async function switchRuleEditor() {
    this._clearRuleEditorError();
    if (this._ruleEditorMode === "visual") {
      this._captureRuleDraft();
      this._ruleYaml = ruleToYaml(this._editingRule ?? newRuleDefaults());
      this._ruleYamlError = null;
      this._ruleEditorMode = "yaml";
      this._refreshRuleEditor();
      return;
    }
    const ruleId = this._editingRule?.id;
    const validated = await this._call(
      {
        type: "alert_manager/rules/yaml/validate",
        yaml: this._ruleYaml,
        ...(ruleId ? { rule_id: ruleId } : {}),
      },
      "",
    );
    if (!validated) {
      this._ruleYamlError = this._notice?.text ?? this._t("rules.yaml_invalid");
      this._refreshRuleEditor();
      return;
    }
    this._editingRule = { ...validated, ...(ruleId ? { id: ruleId } : {}) };
    this._ruleYamlError = null;
    this._ruleEditorMode = "visual";
    this._refreshRuleEditor();
}

export async function saveRuleYaml() {
    const id = String(this._editingRule?.id ?? "");
    const message = id
      ? { type: "alert_manager/rules/yaml/update", rule_id: id, yaml: this._ruleYaml }
      : { type: "alert_manager/rules/yaml/create", yaml: this._ruleYaml };
    const updated = await this._call(
      message,
      this._t(id ? "success.rule_updated" : "success.rule_created"),
    );
    if (!updated) {
      this._ruleYamlError = this._notice?.text ?? this._t("rules.yaml_invalid");
      this._refreshRuleEditor();
      return;
    }
    this._editingRule = null;
    this._ruleEditorMode = "visual";
    this._ruleYaml = "";
    this._ruleYamlError = null;
    this._ruleDirty = false;
    this._replaceRule(updated);
}

export function startRuleEditorResize(event) {
    const handle = event.target.closest?.(".rule-editor-resize");
    if (!handle || window.innerWidth <= 700) return;
    event.preventDefault();
    const drawer = this.shadowRoot.querySelector(".rule-editor-drawer");
    this._ruleEditorResize = {
      startX: event.clientX,
      startWidth: drawer?.getBoundingClientRect?.().width ?? this._ruleEditorWidth,
    };
    handle.classList?.add("is-resizing");
    document.addEventListener("pointermove", this._ruleEditorResizeMove);
    document.addEventListener("pointerup", this._ruleEditorResizeEnd);
    document.addEventListener("pointercancel", this._ruleEditorResizeEnd);
    document.body?.style.setProperty("cursor", "ew-resize");
    document.body?.style.setProperty("user-select", "none");
}

export function resizeRuleEditor(event) {
    if (!this._ruleEditorResize) return;
    const delta = this._ruleEditorResize.startX - event.clientX;
    this._setRuleEditorWidth(this._ruleEditorResize.startWidth + delta);
}

export function setRuleEditorWidth(width) {
    const viewportWidth = Number(window.innerWidth) || 1400;
    const maximum = Math.max(360, Math.min(800, viewportWidth - 64));
    this._ruleEditorWidth = Math.round(Math.min(maximum, Math.max(360, width)));
    this.shadowRoot.querySelector(".rules-layout")?.style.setProperty(
      "--rule-editor-width",
      `${this._ruleEditorWidth}px`,
    );
}

export function stopRuleEditorResize() {
    document.removeEventListener("pointermove", this._ruleEditorResizeMove);
    document.removeEventListener("pointerup", this._ruleEditorResizeEnd);
    document.removeEventListener("pointercancel", this._ruleEditorResizeEnd);
    document.body?.style.removeProperty("cursor");
    document.body?.style.removeProperty("user-select");
    this.shadowRoot?.querySelector(".rule-editor-resize")?.classList.remove("is-resizing");
    this._ruleEditorResize = null;
}

export function resetRuleEditorWidth(event) {
    if (!event.target.closest?.(".rule-editor-resize")) return;
    event.preventDefault();
    this._setRuleEditorWidth(560);
}

export async function saveRule(form) {
    this._clearRuleEditorError();
    const field = (name) =>
      form.querySelector?.(`[data-field="${name}"]`) ??
      form.elements?.namedItem(name) ??
      form.querySelector?.(`[name="${name}"]`);
    const value = (name) => field(name)?.value ?? "";
    const source = value("source");
    const comparisonFree = ["jinja", "unchanged"].includes(source);
    const operator = comparisonFree ? "equals" : value("operator");
    const valueInputs = Array.from(form.querySelectorAll?.("[data-rule-value-index]") ?? []);
    const comparisonValue = comparisonFree || operator === "unchanged"
      ? ""
      : RANGE_RULE_OPERATORS.has(operator)
      ? [String(value("lower-bound")), String(value("upper-bound"))]
      : TEXT_RULE_OPERATORS.has(operator)
      ? (valueInputs.length
        ? valueInputs.map((input) => String(input.value).trim())
        : this._ruleValueList(value("value")).map((item) => item.trim()))
      : String(value("value"));
    const conditionTemplate = String(
      this._editingRule?.condition_template
        ?? this.shadowRoot.querySelector("#rule-condition-template")?.value
        ?? "",
    ).trim() || null;
    const rule = {
      name: String(value("name")).trim(),
      entity_ids: [...(this._editingRule?.entity_ids ?? [])],
      enabled: Boolean(this._editingRule?.enabled ?? true),
      source,
      attribute: ATTRIBUTE_RULE_SOURCES.has(source) ? String(value("attribute")).trim() : null,
      operator,
      value: comparisonValue,
      duration: Number(value("duration")),
      message: String(
        this._editingRule?.message
          ?? this.shadowRoot.querySelector("#rule-message-template")?.value
          ?? "",
      ).trim() || null,
      update_message_when_active: Boolean(
        form.querySelector?.("#rule-update-message-when-active")?.checked
          ?? form.elements?.namedItem("update_message_when_active")?.checked
          ?? this._editingRule?.update_message_when_active
          ?? false
      ),
      condition_template: conditionTemplate,
    };
    const id = String(this._editingRule?.id ?? "");
    // _call renders a busy state. Keep the submitted values as the editor draft so
    // that render cannot clear the form, especially when the backend rejects it.
    this._editingRule = { ...rule, ...(id ? { id } : {}) };
    if ((source === "jinja" || VARIATION_RULE_SOURCES.has(source)) && conditionTemplate === null) {
      this._ruleEditorError = this._t(VARIATION_RULE_SOURCES.has(source)
        ? "rules.condition_template_variation_required"
        : "rules.condition_template_required");
      this._refreshRuleEditor();
      return;
    }
    const message = id
      ? { type: "alert_manager/rules/update", rule_id: id, rule }
      : { type: "alert_manager/rules/create", rule };
    const updated = await this._call(
      message,
      this._t(id ? "success.rule_updated" : "success.rule_created"),
    );
    if (updated) {
      this._editingRule = null;
      this._ruleEditorMode = "visual";
      this._ruleDirty = false;
      this._replaceRule(updated);
    } else if (this._notice?.kind === "error") {
      this._ruleEditorError = this._notice.text;
      this._notice = null;
      this._refreshRuleEditor();
    }
}

export function captureRuleDraft() {
    const form = this.shadowRoot.querySelector?.("#rule-form");
    if (!form || this._editingRule === null) return;
    const field = (name) => form.querySelector?.(`[data-field="${name}"]`);
    const value = (name) => field(name)?.value;
    const valueInputs = Array.from(form.querySelectorAll?.("[data-rule-value-index]") ?? []);
    const operator = value("operator") ?? this._editingRule.operator ?? "equals";
    let ruleValue;
    if (valueInputs.length) {
      ruleValue = valueInputs.map((input) => String(input.value));
    } else if (RANGE_RULE_OPERATORS.has(operator)) {
      ruleValue = [
        String(value("lower-bound") ?? this._ruleValueList(this._editingRule.value)[0] ?? ""),
        String(value("upper-bound") ?? this._ruleValueList(this._editingRule.value)[1] ?? ""),
      ];
    } else {
      ruleValue = operator === "unchanged"
        ? ""
        : String(value("value") ?? this._editingRule.value ?? "");
    }
    this._editingRule = {
      ...this._editingRule,
      name: String(value("name") ?? this._editingRule.name ?? ""),
      enabled: Boolean(this._editingRule.enabled ?? true),
      source: value("source") ?? this._editingRule.source ?? "state",
      attribute: String(value("attribute") ?? this._editingRule.attribute ?? ""),
      operator,
      value: ruleValue,
      duration: Number(value("duration") ?? this._editingRule.duration ?? 900),
      message: String(
        this._editingRule.message
          ?? this.shadowRoot.querySelector("#rule-message-template")?.value
          ?? "",
      ),
      update_message_when_active: Boolean(
        form.querySelector?.("#rule-update-message-when-active")?.checked
          ?? form.elements?.namedItem("update_message_when_active")?.checked
          ?? this._editingRule.update_message_when_active
          ?? false
      ),
      condition_template: String(
        this._editingRule.condition_template
          ?? this.shadowRoot.querySelector("#rule-condition-template")?.value
          ?? "",
      ),
    };
}

export function hydrateRuleEditorControls() {
  const closeButton = this.shadowRoot.querySelector("#rule-editor-close");
  if (closeButton) {
    closeButton.label = this._t("rules.aria_close");
    closeButton.path = MDI_CLOSE;
  }
  if (this._ruleEditorMode !== "visual") return;
  this._configureSelect(
    "rule-source",
    [
      { value: "state", label: this._t("rules.source_state") },
      { value: "attribute", label: this._t("rules.source_attribute") },
      { value: "state_variation", label: this._t("rules.source_state_variation") },
      { value: "attribute_variation", label: this._t("rules.source_attribute_variation") },
      { value: "unchanged", label: this._t("rules.source_unchanged") },
      { value: "jinja", label: this._t("rules.source_jinja") },
    ],
    this._editingRule.source ?? "state",
    (value) => {
      const previousSource = this._editingRule.source ?? "state";
      this._captureRuleDraft();
      this._editingRule.source = value;
      if (!ATTRIBUTE_RULE_SOURCES.has(value)) this._editingRule.attribute = "";
      if (VARIATION_RULE_SOURCES.has(value) && !VARIATION_RULE_OPERATORS.has(this._editingRule.operator)) {
        this._editingRule.operator = "above";
        this._editingRule.value = this._ruleValueList(this._editingRule.value)[0] ?? "";
      }
      this._ruleDirty = true;
      if (["jinja", "unchanged"].includes(previousSource)
        || ["jinja", "unchanged"].includes(value)
        || VARIATION_RULE_SOURCES.has(previousSource)
        || VARIATION_RULE_SOURCES.has(value)) {
        this._refreshRuleEditor();
      } else {
        const attributeField = this.shadowRoot.querySelector(".rule-attribute-field");
        if (attributeField) attributeField.hidden = !ATTRIBUTE_RULE_SOURCES.has(value);
      }
    },
  );
  this._configureSelect(
    "rule-operator",
    (VARIATION_RULE_SOURCES.has(this._editingRule.source) ? [
      { value: "above", label: this._t("operators.above") },
      { value: "below", label: this._t("operators.below") },
      { value: "between", label: this._t("operators.between") },
      { value: "outside", label: this._t("operators.outside") },
    ] : [
      { value: "equals", label: this._t("operators.equals") },
      { value: "not_equals", label: this._t("operators.not_equals") },
      { value: "contains", label: this._t("operators.contains") },
      { value: "not_contains", label: this._t("operators.not_contains") },
      { value: "above", label: this._t("operators.above") },
      { value: "below", label: this._t("operators.below") },
      { value: "between", label: this._t("operators.between") },
      { value: "outside", label: this._t("operators.outside") },
      { value: "unchanged", label: this._t("operators.unchanged") },
    ]),
    this._editingRule.operator ?? (VARIATION_RULE_SOURCES.has(this._editingRule.source) ? "above" : "equals"),
    (value) => {
      this._captureRuleDraft();
      this._editingRule.operator = value;
      this._ruleDirty = true;
      if (TEXT_RULE_OPERATORS.has(value)) {
        this._editingRule.value = this._ruleValueList(this._editingRule.value);
      } else if (RANGE_RULE_OPERATORS.has(value)) {
        const bounds = this._ruleValueList(this._editingRule.value);
        this._editingRule.value = [bounds[0] ?? "", bounds[1] ?? ""];
      } else if (value === "unchanged") {
        this._editingRule.value = "";
      } else {
        this._editingRule.value = this._ruleValueList(this._editingRule.value)[0] ?? "";
      }
      this._refreshRuleEditor();
    },
  );
  this._configureSelector(
    "rule-entity-ids",
    { entity: { multiple: true, exclude_entities: CUSTOM_RULE_EXCLUDED_ENTITY_IDS } },
    this._editingRule.entity_ids ?? [],
    (value) => {
      this._editingRule.entity_ids = this._multipleSelectorValue(
        value,
        this._editingRule.entity_ids,
      );
      this._ruleDirty = true;
    },
  );
  this._configureSelector(
    "rule-attribute",
    { select: { options: this._ruleAttributeOptions(), custom_value: true, mode: "dropdown" } },
    this._editingRule.attribute ?? "",
    (value) => {
      this._editingRule.attribute = String(value ?? "");
      this._ruleDirty = true;
    },
  );
  this._configureSelector(
    "rule-condition-template",
    { template: {} },
    this._editingRule.condition_template ?? "",
    (value) => {
      this._editingRule.condition_template = String(value ?? "");
      this._ruleDirty = true;
    },
  );
  this._configureSelector(
    "rule-message-template",
    { template: {} },
    this._editingRule.message ?? "",
    (value) => {
      this._editingRule.message = String(value ?? "");
      this._ruleDirty = true;
    },
  );
}
