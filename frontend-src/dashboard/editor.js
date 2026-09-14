import "./frontend-ready.js";
import { dashboardLabels } from "./groups.js";
import { dashboardText } from "./translations.js";

// Home Assistant's UI palette maps to theme variables, not fixed RGB values.
const dashboardThemeColors = new Set([
  "primary", "accent", "red", "pink", "purple", "deep-purple", "indigo", "blue",
  "light-blue", "cyan", "teal", "green", "light-green", "lime", "yellow", "amber",
  "orange", "deep-orange", "brown", "light-grey", "grey", "dark-grey", "blue-grey",
  "black", "white", "primary-text", "secondary-text", "disabled",
]);

export function dashboardIconColor(color) {
  if (!color || color === "state") return "var(--state-icon-color)";
  return dashboardThemeColors.has(color) ? `var(--${color}-color)` : color;
}

export function validateDashboardConfig(config, language) {
  const max = config?.max_tiles ?? 5;
  if (!config || !Number.isInteger(max) || max < 1 || max > 100
    || (config.label !== undefined && typeof config.label !== "string")) {
    throw new Error(dashboardText(language, "dashboard.invalid_config"));
  }
  const mobile = config.max_tiles_mobile;
  if ((mobile != null && mobile !== "" && (!Number.isInteger(mobile) || mobile < 1 || mobile > 100))
    || ["labels", "exclude_labels"].some((key) => config[key] !== undefined
      && (!Array.isArray(config[key]) || config[key].some((label) => typeof label !== "string" || !label.trim())))
    || ["group_by_device", "show_age"].some((key) => config[key] !== undefined && typeof config[key] !== "boolean")
    || (config.sort !== undefined && !["newest", "oldest", "alphabetical"].includes(config.sort))) {
    throw new Error(dashboardText(language, "dashboard.invalid_config"));
  }
  if (config.alignment !== undefined && !["left", "center", "right"].includes(config.alignment)) {
    throw new Error(dashboardText(language, "dashboard.invalid_alignment"));
  }
  let color = config.icon_color;
  // Keep colors selected with the previous RGB editor when opening the native picker.
  if (Array.isArray(color) && color.length === 3
    && color.every((channel) => Number.isInteger(channel) && channel >= 0 && channel <= 255)) {
    color = `#${color.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
  }
  if (color !== undefined && (typeof color !== "string"
    || !(color === "state" || dashboardThemeColors.has(color)
      || /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(color)
      || (!/[;{}<>"']/u.test(color) && globalThis.CSS?.supports?.("color", color))))) {
    throw new Error(dashboardText(language, "dashboard.invalid_icon_color"));
  }
  const normalized = { ...config, max_tiles: max, ...(color !== undefined ? { icon_color: color } : {}) };
  if (mobile == null || mobile === "") delete normalized.max_tiles_mobile;
  // Normalize old YAML in memory; explicit empty inclusions override the legacy label.
  if (config.labels !== undefined || config.label) {
    normalized.labels = [...new Set(dashboardLabels(config).include)];
    delete normalized.label;
  }
  if (config.exclude_labels !== undefined) normalized.exclude_labels = [...new Set(config.exclude_labels)];
  return normalized;
}

export class AlertManagerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._form = document.createElement("ha-form");
    this.shadowRoot.append(this._form);
    this._form.addEventListener("value-changed", (event) => {
      event.stopPropagation();
      const config = { ...this._config, ...event.detail.value };
      if (!config.label) delete config.label;
      if (config.icon_color == null) delete config.icon_color;
      this._config = validateDashboardConfig(config, this._hass?.locale?.language);
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: this._config }, bubbles: true, composed: true,
      }));
    });
  }
  setConfig(config) {
    this._config = validateDashboardConfig(config, this._hass?.locale?.language);
    this._update();
  }
  set hass(hass) {
    this._hass = hass;
    this._update();
  }
  _update() {
    this._form.hass = this._hass;
    this._form.data = { alignment: "left", sort: "newest", group_by_device: true, show_age: false, ...this._config };
    this._form.schema = [
      { name: "max_tiles", required: true, selector: { number: { min: 1, max: 100, mode: "box" } } },
      { name: "max_tiles_mobile", selector: { number: { min: 1, max: 100, mode: "box" } } },
      { name: "sort", selector: { select: { mode: "dropdown", options: ["newest", "oldest", "alphabetical"].map((value) => ({
        value, label: dashboardText(this._hass?.locale?.language, `dashboard.sort_${value}`),
      })) } } },
      { name: "labels", selector: { label: { multiple: true } } },
      { name: "exclude_labels", selector: { label: { multiple: true } } },
      { name: "show_age", selector: { boolean: {} } },
      { name: "group_by_device", selector: { boolean: {} } },
      { name: "icon_color", selector: { ui_color: { include_state: true, default_color: "state" } } },
      { name: "alignment", selector: { select: { mode: "dropdown", options: ["left", "center", "right"].map((value) => ({
        value, label: dashboardText(this._hass?.locale?.language, `dashboard.align_${value}`),
      })) } } },
    ];
    this._form.computeLabel = ({ name }) => dashboardText(this._hass?.locale?.language, `dashboard.${name}`);
  }
}
