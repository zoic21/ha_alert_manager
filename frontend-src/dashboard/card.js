import "./frontend-ready.js";
import { navigate } from "../utils/navigation.js";
import { connectDashboard } from "../api/dashboard.js";
import { esc } from "../utils/escaping.js";
import { conditionText, date, durationText } from "../utils/formatting.js";
import { DASHBOARD_MOBILE_QUERY, dashboardStyles } from "../styles/dashboard-styles.js";
import { dashboardText } from "./translations.js";
import { DASHBOARD_ICONS, dashboardGroups, dashboardName, dashboardTarget } from "./groups.js";
import { AlertManagerCardEditor, dashboardIconColor, validateDashboardConfig } from "./editor.js";

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
    if (this._hass?.connection !== hass?.connection) this._lastReadyValue = null;
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
    if (!this._mobileQuery && globalThis.matchMedia) {
      this._mobileQuery = globalThis.matchMedia(DASHBOARD_MOBILE_QUERY);
      this._onWidthChange = () => this._render();
      this._mobileQuery.addEventListener("change", this._onWidthChange);
    }
    this._connect();
    this._render();
  }
  disconnectedCallback() {
    this._mobileQuery?.removeEventListener("change", this._onWidthChange);
    this._mobileQuery = null;
    this._subscription?.disconnect();
    this._subscription = null;
    this._connection = null;
  }
  _connect() {
    if (!this.isConnected || !this._hass?.connection) return;
    if (this._connection !== this._hass.connection) {
      this._subscription?.disconnect();
      this._connection = this._hass.connection;
      this._subscription = connectDashboard(this._hass, (value) => {
        if (value.status !== "loading") {
          this._lastReadyValue = value.status === "ready" ? value : null;
        }
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
    const fullName = alert.device_name || alert.name || alert.rule_name || alert.entity_id || this._t("dashboard.alert");
    const multiple = group.alerts.length > 1;
    const coherence = !multiple && alert.type === "coherence";
    const name = dashboardName(alert, this._t);
    const count = alert.condition_params?.count ?? alert.value;
    const fullMessage = (alert.type === "rule" && alert.message) || conditionText.call(this, alert) || alert.message || this._typeName(alert.type);
    const message = multiple ? this._t("dashboard.count", { count: group.alerts.length })
      : coherence && Number.isInteger(count) && count >= 0
        ? this._t(count === 1 ? "dashboard.coherence_one" : "dashboard.coherence_count", { count })
        : fullMessage;
    const age = this._config.show_age && group.oldest !== null && Number.isFinite(group.oldest)
      ? `<span class="age">· <ha-relative-time data-age="${esc(new Date(group.oldest).toISOString())}"></ha-relative-time></span>` : "";
    return `<ha-card><a class="tile" data-key="${esc(group.key)}" href="${esc(this._sample ? "/alert-manager/overview" : dashboardTarget(group, this._config))}">
      <ha-ripple></ha-ripple>
      ${multiple ? `<div class="types">${group.types.map((type) => this._icon(type)).join("")}</div>` : this._icon(alert.type)}
      <div class="content"><div class="name" title="${esc(fullName)}">${esc(name)}</div>
      <div class="message${age ? " with-age" : ""}" title="${esc(multiple ? message : fullMessage)}">${age ? `<span class="message-text">${esc(message)}</span>${age}` : esc(message)}</div></div>
    </a></ha-card>`;
  }
  _render() {
    if (!this.shadowRoot) return;
    // Reattaching a card refreshes in the background, including an empty snapshot.
    const { status, snapshot } = this._value.status === "loading" && this._lastReadyValue
      ? this._lastReadyValue : this._value;
    const startup = status === "ready" && snapshot.startup?.in_progress;
    let groups = status === "ready"
      ? dashboardGroups(snapshot.alerts, this._config, this._hass, this._t) : [];
    this._sample = this._preview && !startup && !groups.length;
    if (this._sample) {
      groups = dashboardGroups([{
        id: "preview", type: "battery", name: this._t("dashboard.preview_device"),
        condition: this._t("dashboard.preview_message"), active_since: "2026-01-01T00:00:00Z",
      }]);
    }
    const hidden = status === "ready" && !groups.length && (startup || !this._preview);
    if (this.hidden !== hidden) {
      this.hidden = hidden;
      this.dispatchEvent(new CustomEvent("card-visibility-changed", {
        detail: { value: !hidden }, bubbles: true, composed: true,
      }));
    }
    const mobile = this._mobileQuery?.matches ?? globalThis.matchMedia?.(DASHBOARD_MOBILE_QUERY).matches ?? false;
    const limit = mobile ? this._config.max_tiles_mobile ?? this._config.max_tiles : this._config.max_tiles;
    this._tileCount = Math.min(groups.length, limit);
    const visibleTiles = groups.slice(0, limit).map((group) => this._tile(group));
    if (groups.length && (startup || groups.length > limit)) {
      const count = Math.max(0, groups.length - limit);
      const label = esc([
        startup ? this._t("dashboard.startup_detail") : "",
        count ? this._t(this._config.group_by_device === false ? "dashboard.more_count" : "dashboard.more_devices", { count }) : "",
      ].filter(Boolean).join(" · "));
      const target = dashboardTarget(null, this._config);
      const bubble = `<ha-card class="overflow"><a class="more" data-key="overflow" href="${esc(target)}" aria-label="${label}" title="${label}">
        <ha-ripple></ha-ripple>${startup ? '<ha-icon icon="mdi:timer-sand" aria-hidden="true"></ha-icon>' : ""}
        ${count ? `<span aria-hidden="true">+${count}</span>` : ""}${startup ? "" : '<ha-icon icon="mdi:chevron-right" aria-hidden="true"></ha-icon>'}
      </a></ha-card>`;
      // Keep the bubble attached to the last alert when the row wraps.
      visibleTiles.push(`<div class="tile-tail">${visibleTiles.pop()}${bubble}</div>`);
    }
    const tiles = visibleTiles.join("");
    let content = groups.length ? `<div class="tiles">${tiles}</div>` : "";
    if (this._sample) content += `<div class="status">${esc(this._t("dashboard.preview"))}</div>`;
    else if (status !== "ready") content += `<ha-card><div class="status" role="status">${esc(this._t(`dashboard.${status}`))}
      ${status === "unavailable" ? `<ha-button appearance="plain" data-retry>${esc(this._t("dashboard.retry"))}</ha-button>` : ""}</div></ha-card>`;
    const alignment = this._config.alignment ?? "left";
    const color = dashboardIconColor(this._config.icon_color);
    const markup = `<style>${dashboardStyles}</style><div class="dashboard" data-alignment="${alignment}" style="--alert-icon-color: ${esc(color)}">${content}</div>`;
    if (markup === this._markup) {
      // Locale settings can change without changing the surrounding markup.
      this._hydrateAge();
      return;
    }
    const focused = this.shadowRoot.activeElement?.dataset?.key;
    this._markup = markup;
    this.shadowRoot.innerHTML = markup;
    this._hydrateAge();
    if (focused) [...this.shadowRoot.querySelectorAll("[data-key]")].find((node) => node.dataset.key === focused)?.focus();
    this.dispatchEvent(new CustomEvent("card-updated", { bubbles: true, composed: true }));
  }
  _hydrateAge() {
    for (const relative of this.shadowRoot.querySelectorAll("ha-relative-time[data-age]")) {
      relative.hass = this._hass;
      if (relative.datetime !== relative.dataset.age) {
        relative.datetime = relative.dataset.age;
        relative.textContent = this._date(relative.dataset.age);
      }
    }
  }
}

if (!customElements.get("alert-manager-card-editor")) customElements.define("alert-manager-card-editor", AlertManagerCardEditor);
if (!customElements.get("alert-manager-card")) customElements.define("alert-manager-card", AlertManagerCard);
window.customCards ??= [];
if (!window.customCards.some((card) => card.type === "alert-manager-card")) {
  window.customCards.push({ type: "alert-manager-card", name: "Alert Manager", preview: true,
    description: dashboardText(navigator.language, "dashboard.description") });
}
