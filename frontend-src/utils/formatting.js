import { ATTRIBUTE_RULE_SOURCES } from "./constants.js";

const lines = (value) =>
  String(value ?? "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const newRuleDefaults = () => ({
  name: "",
  entity_ids: [],
  enabled: true,
  source: "state",
  attribute: "",
  operator: "equals",
  value: [""],
  duration: 900,
  message: "",
  update_message_when_active: false,
  condition_template: "",
  flapping_enabled: false,
  flapping_occurrences: null,
  flapping_window: null,
  flapping_recovery: null,
});

const yamlValue = (value) => {
  if (value === null || value === undefined || value === "") return "null";
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  return JSON.stringify(String(value));
};

const ruleToYaml = (rule) => {
  const source = rule.source === "none"
    ? "jinja"
    : rule.source === "variation"
    ? "state_variation"
    : (rule.source ?? "state");
  const lines = [
    `name: ${yamlValue(rule.name)}`,
    `enabled: ${yamlValue(rule.enabled ?? true)}`,
    "entity_ids:",
    ...(rule.entity_ids ?? []).map((entityId) => `  - ${yamlValue(entityId)}`),
    `source: ${yamlValue(source)}`,
  ];
  if (ATTRIBUTE_RULE_SOURCES.has(source)) {
    lines.push(`attribute: ${yamlValue(rule.attribute)}`);
  }
  if (!["jinja", "unchanged"].includes(source)) {
    lines.push(`operator: ${yamlValue(rule.operator)}`);
    if (rule.operator !== "unchanged") {
      lines.push(Array.isArray(rule.value)
        ? "value:\n" + rule.value.map((value) => `  - ${yamlValue(value)}`).join("\n")
        : `value: ${yamlValue(rule.value)}`);
    }
  }
  lines.push(
    `duration: ${yamlValue(rule.duration)}`,
    `message: ${yamlValue(rule.message)}`,
    `update_message_when_active: ${yamlValue(rule.update_message_when_active ?? false)}`,
    `condition_template: ${yamlValue(rule.condition_template)}`,
    `flapping_enabled: ${yamlValue(rule.flapping_enabled ?? false)}`,
    `flapping_occurrences: ${yamlValue(rule.flapping_occurrences)}`,
    `flapping_window: ${yamlValue(rule.flapping_window)}`,
    `flapping_recovery: ${yamlValue(rule.flapping_recovery)}`,
  );
  return `${lines.join("\n")}\n`;
};

export function date(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(this._language, {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(date);
}

export function remaining(value) {
    const due = new Date(value).getTime();
    if (!Number.isFinite(due)) return "—";
    const seconds = Math.max(0, Math.ceil((due - Date.now()) / 1000));
    return seconds === 0 ? this._t("duration.activation") : this._durationText(seconds);
}

export function durationText(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    if (value < 60) return this._t("duration.seconds", { count: value });
    if (value % 3600 === 0) {
      return this._t("duration.hours", { count: value / 3600 });
    }
    if (value % 60 === 0) {
      return this._t("duration.minutes", { count: value / 60 });
    }
    return this._t("duration.minutes_seconds", {
      minutes: Math.floor(value / 60),
      seconds: value % 60,
    });
}

export function historyDurationText(seconds) {
    return this._durationText(Math.max(0, Math.round(Number(seconds) || 0)));
}

export function conditionText(alert) {
    if (!alert?.condition_key) return alert?.condition ?? "";
    const params = { ...(alert.condition_params ?? {}) };
    if (alert.condition_key === "rule.generated") {
      const sourceKey = params.source === "attribute"
        ? "conditions.sources.attribute"
        : params.source === "attribute_variation"
        ? "conditions.sources.attribute_variation"
        : ["state_variation", "variation"].includes(params.source)
        ? "conditions.sources.state_variation"
        : "conditions.sources.state";
      params.source = this._t(sourceKey, { attribute: params.attribute ?? "" });
      params.operator = this._t(`operators.${params.operator}`);
      params.unit = params.unit ? ` ${params.unit}` : "";
      params.duration = Number(params.duration)
        ? ` ${this._t("conditions.fragments.duration", {
          duration: this._durationText(params.duration),
        })}`
        : "";
    } else if (alert.condition_key === "automatic.flapping") {
      params.duration = this._durationText(params.duration_seconds ?? params.duration);
      params.last_occurrence = this._date(params.last_occurrence);
    } else if (alert.condition_key === "rule.selected_unchanged") {
      const sourceKey = params.source === "attribute"
        ? "conditions.sources.attribute"
        : "conditions.sources.state";
      params.source = this._t(sourceKey, { attribute: params.attribute ?? "" });
      params.duration = Number(params.duration)
        ? ` ${this._t("conditions.fragments.duration", {
          duration: this._durationText(params.duration),
        })}`
        : "";
    } else if (["rule.jinja", "rule.unchanged"].includes(alert.condition_key)) {
      params.duration = Number(params.duration)
        ? ` ${this._t("conditions.fragments.duration", {
          duration: this._durationText(params.duration),
        })}`
        : "";
    }
    return this._t(`conditions.${alert.condition_key}`, params);
}

export function updateCountdowns() {
    if (!this._monitoringEnabled) return;
    const roots = [this.shadowRoot];
    this.shadowRoot?.querySelectorAll("ha-data-table").forEach((table) => {
      if (table.shadowRoot) roots.push(table.shadowRoot);
    });
    this.shadowRoot?.querySelectorAll("[data-alert-table-page]").forEach((tablePage) => {
      const table = tablePage.shadowRoot?.querySelector?.("ha-data-table");
      if (table?.shadowRoot) roots.push(table.shadowRoot);
    });
    for (const root of roots) {
      root?.querySelectorAll("[data-due]").forEach((node) => {
        node.textContent = this._remaining(node.dataset.due);
      });
    }
}

export { lines, newRuleDefaults, ruleToYaml };
