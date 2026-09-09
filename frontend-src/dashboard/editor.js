import "./frontend-ready.js";
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
  return { ...config, max_tiles: max, ...(color !== undefined ? { icon_color: color } : {}) };
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
    this._form.data = { alignment: "left", ...this._config };
    this._form.schema = [
      { name: "max_tiles", required: true, selector: { number: { min: 1, max: 100, mode: "box" } } },
      { name: "label", selector: { label: {} } },
      { name: "icon_color", selector: { ui_color: { include_state: true, default_color: "state" } } },
      { name: "alignment", selector: { select: { mode: "dropdown", options: ["left", "center", "right"].map((value) => ({
        value, label: dashboardText(this._hass?.locale?.language, `dashboard.align_${value}`),
      })) } } },
    ];
    this._form.computeLabel = ({ name }) => dashboardText(this._hass?.locale?.language, `dashboard.${name}`);
  }
}
