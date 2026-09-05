const VALIDATION_ERROR_KEYS = new Map([
  ["Rule name is required", "rule_name_required"],
  ["Rule name is too long", "rule_name_too_long"],
  ["Rule entity_ids must be a non-empty list", "rule_entities_required"],
  ["Rule entity_ids must contain at most 50 items", "rule_entities_too_many"],
  ["An entity cannot be repeated in the same rule", "rule_entity_duplicate"],
  ["Alert Manager entities cannot be monitored", "rule_entity_forbidden"],
  ["Attribute is required for attribute rules", "attribute_required"],
  ["Attribute wildcard paths must use complete .* segments", "attribute_path_invalid"],
  ["Attribute variation does not support wildcard paths", "attribute_variation_wildcard"],
  ["Variation rules require a numeric operator", "variation_operator_required"],
  ["Rule message must not exceed 1024 characters", "message_too_long"],
  ["Rule condition_template must be non-empty text of at most 65536 characters", "condition_template_too_long"],
  ["rules must contain at most 500 items", "rules_too_many"],
  ["Rule condition_template is required for Jinja-only rules", "jinja_required"],
  ["Rule condition_template is required for Variation rules", "variation_condition_required"],
  ["Duration must be an integer", "duration_integer"],
  ["Duration must be between 0 and 31536000 seconds", "duration_range"],
  ["Numeric operators require one finite numeric value", "numeric_value_required"],
  ["Range operators require exactly two numeric bounds", "range_bounds_required"],
  ["Range operators require two finite numeric bounds", "range_bounds_invalid"],
  ["Range lower bound must not exceed upper bound", "range_bounds_order"],
  ["Text operators require at least one value", "text_value_required"],
  ["Text operator values must be scalar", "text_value_scalar"],
  ["Text operator values must not be empty", "text_value_empty"],
  ["Text operator values must be unique", "text_value_duplicate"],
]);

const VALIDATION_ERROR_PREFIX_KEYS = [
  ["Unknown or resolved alert id:", "alert_not_found"],
  ["Alert reevaluation requires running monitoring", "reevaluation_unavailable"],
  ["Missing rule field:", "rule_field_missing"],
  ["Unsupported value source:", "source_unsupported"],
  ["Unsupported operator:", "operator_unsupported"],
  ["Invalid rule condition_template:", "jinja_invalid"],
  ["Invalid rule message template:", "jinja_invalid"],
  ["Jinja templates cannot reference Alert Manager entities", "jinja_self_reference"],
  ["Invalid YAML:", "yaml_invalid"],
];

export async function fetchTranslations(language) {
    const request = (requestedLanguage) => this._api.call({
      type: "frontend/get_translations",
      language: requestedLanguage,
      category: "config_panel",
      integration: "alert_manager",
    });
    const [localized, english] = await Promise.all([
      request(language),
      language === "en" ? Promise.resolve(null) : request("en"),
    ]);
    if (language !== this._language) return;
    this._translations = localized?.resources ?? {};
    this._englishTranslations = english?.resources ?? this._translations;
}

export async function reloadTranslations() {
    this._loading = true;
    this._render();
    const language = this._language;
    this._translationPromise = this._fetchTranslations(language);
    try {
      await this._translationPromise;
      this._notice = null;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._translationPromise = null;
      this._loading = false;
      if (language !== this._language) {
        void this._reloadTranslations();
        return;
      }
      this._render();
    }
}

export function t(key, params = {}) {
    const resourceKey = `component.alert_manager.config_panel.${key}`;
    const template = this._translations[resourceKey]
      ?? this._englishTranslations[resourceKey]
      ?? resourceKey;
    return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => (
      Object.hasOwn(params, name) ? String(params[name] ?? "") : match
    ));
}

export function errorText(error) {
    const code = error?.code ?? error?.body?.code;
    const message = error?.message ?? error?.body?.message;
    if (code === "invalid_format" && typeof message === "string" && message) {
      const exactKey = VALIDATION_ERROR_KEYS.get(message);
      if (exactKey) return this._t(`errors.${exactKey}`);
      const prefix = VALIDATION_ERROR_PREFIX_KEYS.find(([value]) => message.startsWith(value));
      if (prefix) return this._t(`errors.${prefix[1]}`);
    }
    return this._t(`errors.${["invalid_format", "not_loaded"].includes(code) ? code : "unknown"}`);
}
