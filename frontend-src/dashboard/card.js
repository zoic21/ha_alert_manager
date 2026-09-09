import "./frontend-ready.js";
import { navigate } from "../utils/navigation.js";
import { connectDashboard } from "../api/dashboard.js";
import { esc } from "../utils/escaping.js";
import { conditionText, date, durationText } from "../utils/formatting.js";
import { dashboardStyles } from "../styles/dashboard-styles.js";
import { dashboardText } from "./translations.js";
import { DASHBOARD_ICONS, dashboardGroups, dashboardTarget } from "./groups.js";
import { AlertManagerCardEditor, validateDashboardConfig } from "./editor.js";

export class AlertManagerCard extends HTMLElement {
  // HA must keep the hidden card connected so a new alert can make it visible.
  connectedWhileHidden = true;
  _value = { status: "loading" };
  _config = { max_tiles: 5 };
  _preview = false;
  _t = (key, params) => dashboardText(this._hass?.locale?.language, key, params);
  _durationText = durationText;
  _date = date;

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.addEventListener("click", (event) => {
      if (event.composedPath().some((node) => node?.dataset?.retry !== undefined)) {
        this._subscription?.retry();
        return;
      }
      const link = event.composedPath().find((node) => node?.tagName === "A");
      if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (this._sample) return;
      navigate(link.getAttribute("href"));
    });
  }
  static getStubConfig() { return { type: "custom:alert-manager-card", max_tiles: 5 }; }
  static async getConfigElement() {
    // Use the native tile editor to load HA's form/selectors through its loader.
    if (!customElements.get("ha-form") && window.loadCardHelpers) {
      const helpers = await window.loadCardHelpers();
      const native = helpers.createCardElement({ type: "tile", entity: "sensor.alert_manager_main_active" });
      await native.constructor.getConfigElement?.();
    }
    return document.createElement("alert-manager-card-editor");
  }
  setConfig(config) {
    this._config = validateDashboardConfig(config, this._hass?.locale?.language);
    this._render();
  }
  set hass(hass) {
    const changed = hass?.locale?.language !== this._hass?.locale?.language
      || hass?.entities !== this._hass?.entities;
    this._hass = hass;
    this._language = hass?.locale?.language ?? "en";
    this._connect();
    if (changed) this._render();
  }
  set preview(value) { this._preview = Boolean(value); this._render(); }
  get preview() { return this._preview; }
  set editMode(value) { this.preview = value; }
  getCardSize() {
    return this.hidden ? 0 : Math.max(1, Math.ceil((this.getBoundingClientRect?.().height || 80) / 50));
  }
  getGridOptions() { return { columns: 12, min_columns: 3 }; }
  connectedCallback() {
    this._connect();
    this._render();
  }
  disconnectedCallback() {
    this._subscription?.disconnect();
    this._subscription = null;
    this._connection = null;
    this._value = { status: "loading" };
  }
  _connect() {
    if (!this.isConnected || !this._hass?.connection) return;
    if (this._connection !== this._hass.connection) {
      this._subscription?.disconnect();
      this._connection = this._hass.connection;
      this._subscription = connectDashboard(this._hass, (value) => {
        this._value = value;
        this._render();
      });
    } else {
      this._subscription?.update(this._hass);
    }
  }
  _typeName(type) {
    return this._t(type === "rule" ? "dashboard.custom_rules"
      : type === "coherence" ? "coherence.title"
        : Object.hasOwn(DASHBOARD_ICONS, type) ? `packs.${type}.name` : "dashboard.alert");
  }
  _icon(type) {
    const name = esc(this._typeName(type));
    return `<ha-icon icon="${Object.hasOwn(DASHBOARD_ICONS, type) ? DASHBOARD_ICONS[type] : "mdi:alert-circle-outline"}" role="img" aria-label="${name}" title="${name}"></ha-icon>`;
  }
  _tile(group) {
    const alert = group.alerts[0];
    const name = alert.device_name || alert.name || alert.rule_name || alert.entity_id || this._t("dashboard.alert");
    const multiple = group.alerts.length > 1;
    const message = multiple ? this._t("dashboard.count", { count: group.alerts.length })
      : (alert.type === "rule" && alert.message) || conditionText.call(this, alert) || alert.message || this._typeName(alert.type);
    return `<ha-card><a class="tile" data-key="${esc(group.key)}" href="${esc(this._sample ? "/alert-manager/overview" : dashboardTarget(group, this._config.label))}">
      ${multiple ? "" : this._icon(alert.type)}
      <div class="content"><div class="name" title="${esc(name)}">${esc(name)}</div>
      <div class="message">${esc(message)}</div>
      ${multiple ? `<div class="types">${group.types.map((type) => this._icon(type)).join("")}</div>` : ""}</div>
    </a></ha-card>`;
  }
  _render() {
    if (!this.shadowRoot) return;
    const { status, snapshot } = this._value;
    let groups = status === "ready"
      ? dashboardGroups(snapshot.alerts, this._config.label, this._hass) : [];
    this._sample = this._preview && !groups.length;
    if (this._sample) {
      groups = dashboardGroups([{
        id: "preview", type: "battery", name: this._t("dashboard.preview_device"),
        condition: this._t("dashboard.preview_message"), active_since: "2026-01-01T00:00:00Z",
      }]);
    }
    const startup = status === "ready" && snapshot.startup?.in_progress;
    const hidden = status === "ready" && !startup && !groups.length && !this._preview;
    if (this.hidden !== hidden) {
      this.hidden = hidden;
      this.dispatchEvent(new CustomEvent("card-visibility-changed", {
        detail: { value: !hidden }, bubbles: true, composed: true,
      }));
    }
    this._tileCount = Math.min(groups.length, this._config.max_tiles);
    let content = groups.length ? `<div class="tiles">${groups.slice(0, this._config.max_tiles).map((group) => this._tile(group)).join("")}</div>` : "";
    if (groups.length > this._config.max_tiles) content += `<a class="more" href="${esc(`/alert-manager/overview?${new URLSearchParams({ dashboard: "1", ...(this._config.label ? { label: this._config.label } : {}) })}`)}">${esc(this._t("dashboard.more"))}</a>`;
    if (this._sample) content += `<div class="status">${esc(this._t("dashboard.preview"))}</div>`;
    else if (status !== "ready" || startup) content += `<ha-card><div class="status" role="status">${esc(this._t(`dashboard.${startup ? "startup" : status}`))}
      ${status === "unavailable" ? `<ha-button appearance="plain" data-retry>${esc(this._t("dashboard.retry"))}</ha-button>` : ""}</div></ha-card>`;
    const alignment = this._config.alignment ?? "left";
    const color = this._config.icon_color ? `rgb(${this._config.icon_color.join(", ")})` : "var(--state-icon-color)";
    const markup = `<style>${dashboardStyles}</style><div class="dashboard" data-alignment="${alignment}" style="--alert-icon-color: ${color}">${content}</div>`;
    if (markup === this._markup) return;
    const focused = this.shadowRoot.activeElement?.dataset?.key;
    this._markup = markup;
    this.shadowRoot.innerHTML = markup;
    if (focused) [...this.shadowRoot.querySelectorAll("[data-key]")].find((node) => node.dataset.key === focused)?.focus();
    this.dispatchEvent(new CustomEvent("card-updated", { bubbles: true, composed: true }));
  }
}

if (!customElements.get("alert-manager-card-editor")) customElements.define("alert-manager-card-editor", AlertManagerCardEditor);
if (!customElements.get("alert-manager-card")) customElements.define("alert-manager-card", AlertManagerCard);
window.customCards ??= [];
if (!window.customCards.some((card) => card.type === "alert-manager-card")) {
  window.customCards.push({ type: "alert-manager-card", name: "Alert Manager", preview: true,
    description: dashboardText(navigator.language, "dashboard.description") });
}
