import "./frontend-ready.js";
import { dashboardText } from "./translations.js";

export function validateDashboardConfig(config, language) {
  const max = config?.max_tiles ?? 5;
  if (!config || !Number.isInteger(max) || max < 1 || max > 100
    || (config.label !== undefined && typeof config.label !== "string")) {
    throw new Error(dashboardText(language, "dashboard.invalid_config"));
  }
  return { ...config, max_tiles: max };
}

export class AlertManagerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._form = document.createElement("ha-form");
    this.shadowRoot.append(this._form);
    this._form.schema = [
      { name: "max_tiles", required: true, selector: { number: { min: 1, max: 100, mode: "box" } } },
      { name: "label", selector: { label: {} } },
    ];
    this._form.addEventListener("value-changed", (event) => {
      event.stopPropagation();
      const config = { ...this._config, ...event.detail.value };
      if (!config.label) delete config.label;
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
    this._form.data = this._config;
    this._form.computeLabel = ({ name }) => dashboardText(this._hass?.locale?.language, `dashboard.${name}`);
  }
}
