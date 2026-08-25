const TABS = [
  {
    id: "overview",
    path: "/alert-manager/overview",
    name: "Vue d’ensemble",
    iconPath: "M19,5V7H15V5H19M9,5V11H5V5H9M19,13V19H15V13H19M9,17V19H5V17H9M21,3H13V9H21V3M11,3H3V13H11V3M21,11H13V21H21V11M11,15H3V21H11V15Z",
  },
  {
    id: "automatic",
    path: "/alert-manager/automatic",
    name: "Surveillance automatique",
    iconPath: "M19.07,4.93L17.66,6.34C19.1,7.79 20,9.79 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12C4,7.92 7.05,4.56 11,4.07V6.09C8.16,6.57 6,9.03 6,12A6,6 0 0,0 12,18A6,6 0 0,0 18,12C18,10.34 17.33,8.84 16.24,7.76L14.83,9.17C15.55,9.9 16,10.9 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12C8,10.14 9.28,8.59 11,8.14V10.28C10.4,10.63 10,11.26 10,12A2,2 0 0,0 12,14A2,2 0 0,0 14,12C14,11.26 13.6,10.62 13,10.28V2H12A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12C22,9.24 20.88,6.74 19.07,4.93Z",
  },
  {
    id: "rules",
    path: "/alert-manager/rules",
    name: "Règles personnalisées",
    iconPath: "M3,5H9V11H3V5M5,7V9H7V7H5M11,7H21V9H11V7M11,15H21V17H11V15M5,20L1.5,16.5L2.91,15.09L5,17.17L9.59,12.59L11,14L5,20Z",
  },
  {
    id: "settings",
    path: "/alert-manager/settings",
    name: "Exclusions et paramètres",
    iconPath: "M8 13C6.14 13 4.59 14.28 4.14 16H2V18H4.14C4.59 19.72 6.14 21 8 21S11.41 19.72 11.86 18H22V16H11.86C11.41 14.28 9.86 13 8 13M8 19C6.9 19 6 18.1 6 17C6 15.9 6.9 15 8 15S10 15.9 10 17C10 18.1 9.1 19 8 19M19.86 6C19.41 4.28 17.86 3 16 3S12.59 4.28 12.14 6H2V8H12.14C12.59 9.72 14.14 11 16 11S19.41 9.72 19.86 8H22V6H19.86M16 9C14.9 9 14 8.1 14 7C14 5.9 14.9 5 16 5S18 5.9 18 7C18 8.1 17.1 9 16 9Z",
  },
];

const TAB_PAGES = TABS.map(({ path, name, iconPath }) => ({ path, name, iconPath }));

const MDI_CLOSE = "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z";
const MDI_PLUS = "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z";
const MDI_ALERT_CIRCLE_OUTLINE = "M13,14H11V10H13M13,18H11V16H13M12,2C6.48,2 2,6.48 2,12C2,17.52 6.48,22 12,22C17.52,22 22,17.52 22,12C22,6.48 17.52,2 12,2M12,20C7.58,20 4,16.42 4,12C4,7.58 7.58,4 12,4C16.42,4 20,7.58 20,12C20,16.42 16.42,20 12,20Z";
const MDI_CLOCK_OUTLINE = "M12,20C7.58,20 4,16.42 4,12C4,7.58 7.58,4 12,4C16.42,4 20,7.58 20,12C20,16.42 16.42,20 12,20M12,2C6.48,2 2,6.48 2,12C2,17.52 6.48,22 12,22C17.52,22 22,17.52 22,12C22,6.48 17.52,2 12,2M12.5,7H11V13L16.25,16.15L17,14.92L12.5,12.25V7Z";
const TEXT_RULE_OPERATORS = new Set(["equals", "not_equals", "contains", "not_contains"]);

const esc = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const lines = (value) =>
  String(value ?? "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const durationText = (seconds) => {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${value} s`;
  if (value % 3600 === 0) return `${value / 3600} h`;
  if (value % 60 === 0) return `${value / 60} min`;
  return `${Math.floor(value / 60)} min ${value % 60} s`;
};

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
});

const buildOverviewItems = (activeAlerts = [], pendingAlerts = []) => {
  const groupByStatus = (alerts, status) => {
    const sources = alerts.map((alert) => ({ alert, status }));
    const deviceCounts = new Map();
    for (const source of sources) {
      if (source.alert.device_id) {
        deviceCounts.set(
          source.alert.device_id,
          (deviceCounts.get(source.alert.device_id) ?? 0) + 1,
        );
      }
    }
    const emittedDevices = new Set();
    const items = [];
    for (const source of sources) {
      const deviceId = source.alert.device_id;
      if (!deviceId || deviceCounts.get(deviceId) === 1) {
        items.push({ kind: "alert", ...source });
        continue;
      }
      if (emittedDevices.has(deviceId)) continue;
      emittedDevices.add(deviceId);
      items.push({
        kind: "device",
        device_id: deviceId,
        alerts: sources.filter((item) => item.alert.device_id === deviceId),
      });
    }
    return items;
  };
  return [
    ...groupByStatus(activeAlerts, "active"),
    ...groupByStatus(pendingAlerts, "pending"),
  ];
};

class AlertManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._packs = [];
    this._alerts = {
      active_count: 0,
      pending_count: 0,
      tracked_count: 0,
      alerts: [],
      pending: [],
    };
    this._activeTab = "overview";
    this._editingRule = null;
    this._loading = true;
    this._busy = false;
    this._notice = null;
    this._timer = null;
    this._sensorState = null;
    this._settingsDraft = null;
    this._entityDelayDraft = null;
    this._ruleEditorWidth = 560;
    this._ruleEditorResize = null;
    this._configuredControls = new WeakSet();
    this.shadowRoot.addEventListener("click", (event) => this._handleClick(event));
    this.shadowRoot.addEventListener("keydown", (event) => this._handleKeydown(event));
    this.shadowRoot.addEventListener("pointerdown", (event) => this._startRuleEditorResize(event));
    this.shadowRoot.addEventListener("dblclick", (event) => this._resetRuleEditorWidth(event));
    this.shadowRoot.addEventListener("submit", (event) => this._handleSubmit(event));
    this._ruleEditorResizeMove = (event) => this._resizeRuleEditor(event);
    this._ruleEditorResizeEnd = () => this._stopRuleEditorResize();
  }

  set hass(value) {
    this._hass = value;
    const alertsChanged = this._syncSensor();
    if (this.isConnected && !this._config && !this._loadPromise) {
      this._load();
    } else if (this.isConnected && this._activeTab === "overview" && alertsChanged) {
      this._render();
    } else if (this.isConnected) {
      this._hydrateSelectors();
    }
  }

  get hass() {
    return this._hass;
  }

  set panel(value) {
    this._panel = value;
  }

  set route(value) {
    this._route = value;
    const activeTab = this._tabFromRoute(value);
    if (activeTab !== this._activeTab) {
      this._activeTab = activeTab;
      this._editingRule = null;
      this._notice = null;
      if (this.isConnected) this._render();
    } else if (this.isConnected) {
      this._hydrateSelectors();
    }
  }

  set narrow(value) {
    this._narrow = value;
  }

  connectedCallback() {
    this._render();
    if (this._hass && !this._config) this._load();
    this._timer = window.setInterval(() => this._updateCountdowns(), 1000);
  }

  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
    this._stopRuleEditorResize();
  }

  async _load() {
    this._loadPromise = Promise.all([
      this._hass.callWS({ type: "alert_manager/config/get" }),
      this._hass.callWS({ type: "alert_manager/alerts/list" }),
      this._hass.callWS({ type: "alert_manager/packs/list" }),
    ]);
    this._loading = true;
    this._render();
    try {
      [this._config, this._alerts, this._packs] = await this._loadPromise;
      this._resetSettingsDraft();
      this._syncSensor();
      this._notice = null;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
    } finally {
      this._loading = false;
      this._loadPromise = null;
      this._render();
    }
  }

  _syncSensor() {
    const state = this._hass?.states?.["sensor.alert_manager"];
    if (!state || state === this._sensorState) return false;
    this._sensorState = state;
    const attributes = state.attributes ?? {};
    if (Array.isArray(attributes.alerts) && Array.isArray(attributes.pending)) {
      this._alerts = {
        active_count: Number(attributes.active_count ?? state.state ?? 0),
        pending_count: Number(attributes.pending_count ?? 0),
        tracked_count: Number(attributes.tracked_count ?? 0),
        alerts: attributes.alerts,
        pending: attributes.pending,
      };
      return true;
    }
    return false;
  }

  async _call(message, successText) {
    this._busy = true;
    this._notice = null;
    this._render();
    try {
      const result = await this._hass.callWS(message);
      this._notice = { kind: "success", text: successText };
      return result;
    } catch (error) {
      this._notice = { kind: "error", text: this._errorText(error) };
      return null;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _errorText(error) {
    return error?.message || error?.body?.message || String(error || "Erreur inconnue");
  }

  _render() {
    if (!this.shadowRoot) return;
    const content = this._loading
      ? '<div class="loading">Chargement d’Alert Manager…</div>'
      : this._renderTab();
    const page = `<main class="${this._activeTab === "rules" ? "rules-page" : ""}">
      ${this._notice ? `<div class="notice ${this._notice.kind}">${esc(this._notice.text)}</div>` : ""}
      ${content}
    </main>`;
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      ${this._hass ? `<hass-tabs-subpage id="panel-shell" back-path="/config/integrations">${page}</hass-tabs-subpage>` : page}`;
    this._hydrateSelectors();
    this._updateCountdowns();
  }

  _configureSelector(id, selector, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element) return;
    element.hass = this._hass;
    if (this._configuredControls.has(element)) return;
    element.selector = selector;
    element.value = value;
    element.addEventListener("value-changed", (event) => onChange(event.detail?.value));
    this._configuredControls.add(element);
  }

  _configureSelect(id, options, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element || this._configuredControls.has(element)) return;
    element.options = options;
    element.value = value;
    element.addEventListener("selected", (event) => {
      element.value = event.detail?.value;
      onChange?.(event.detail?.value);
    });
    this._configuredControls.add(element);
  }

  _hydrateSelectors() {
    const shell = this.shadowRoot.querySelector("#panel-shell");
    if (shell && this._hass) {
      const activePage = TABS.find((tab) => tab.id === this._activeTab) ?? TABS[0];
      shell.hass = this._hass;
      shell.tabs = TAB_PAGES;
      shell.route = { prefix: "", path: activePage.path };
      shell.backPath = "/config/integrations";
      shell.backCallback = window.history?.state?.from !== undefined
        ? () => window.history.back()
        : undefined;
    }
    if (!this._hass || !this._config) return;
    if (this._editingRule !== null) {
      const closeButton = this.shadowRoot.querySelector("#rule-editor-close");
      if (closeButton) {
        closeButton.label = "Fermer";
        closeButton.path = MDI_CLOSE;
      }
      this._configureSelect(
        "rule-source",
        [
          { value: "state", label: "État principal" },
          { value: "attribute", label: "Attribut" },
        ],
        this._editingRule.source ?? "state",
        (value) => {
          this._editingRule.source = value;
          const attributeField = this.shadowRoot.querySelector(".rule-attribute-field");
          if (attributeField) attributeField.hidden = value !== "attribute";
        },
      );
      this._configureSelect(
        "rule-operator",
        [
          { value: "equals", label: "Égal à" },
          { value: "not_equals", label: "Différent de" },
          { value: "contains", label: "Contient" },
          { value: "not_contains", label: "Ne contient pas" },
          { value: "above", label: "Supérieur à" },
          { value: "below", label: "Inférieur à" },
        ],
        this._editingRule.operator ?? "equals",
        (value) => {
          this._captureRuleDraft();
          this._editingRule.operator = value;
          if (TEXT_RULE_OPERATORS.has(value)) {
            this._editingRule.value = this._ruleValueList(this._editingRule.value);
          } else {
            this._editingRule.value = this._ruleValueList(this._editingRule.value)[0] ?? "";
          }
          this._render();
        },
      );
      this._configureSelector(
        "rule-entity-ids",
        { entity: { multiple: true } },
        this._editingRule.entity_ids ?? [],
        (value) => { this._editingRule.entity_ids = Array.isArray(value) ? value : []; },
      );
    }
    if (this._activeTab !== "settings") return;
    this._ensureSettingsDraft();
    this._configureSelector(
      "excluded-labels",
      { label: { multiple: true } },
      this._settingsDraft.excluded_labels,
      (value) => { this._settingsDraft.excluded_labels = Array.isArray(value) ? value : []; },
    );
    this._configureSelector(
      "excluded-entities",
      { entity: { multiple: true } },
      this._settingsDraft.excluded_entities,
      (value) => { this._settingsDraft.excluded_entities = Array.isArray(value) ? value : []; },
    );
    this._configureSelector(
      "excluded-devices",
      { device: { multiple: true } },
      this._settingsDraft.excluded_devices,
      (value) => { this._settingsDraft.excluded_devices = Array.isArray(value) ? value : []; },
    );
    this._entityDelayDraft.forEach((row, index) => {
      this._configureSelector(
        `delay-entity-${index}`,
        { entity: {} },
        row.entity_id || "",
        (value) => this._setEntityDelayEntity(index, value),
      );
    });
  }

  _renderTab() {
    if (!this._config) return '<div class="empty">Configuration indisponible.</div>';
    if (this._activeTab === "automatic") return this._renderAutomatic();
    if (this._activeTab === "rules") return this._renderRules();
    if (this._activeTab === "settings") return this._renderSettings();
    return this._renderOverview();
  }

  _tabFromRoute(route) {
    const path = `${route?.prefix ?? ""}${route?.path ?? ""}`.replace(/\/$/, "");
    return TABS.find((tab) => path.endsWith(`/${tab.id}`))?.id ?? "overview";
  }

  _renderOverview() {
    const items = buildOverviewItems(this._alerts.alerts, this._alerts.pending);
    return `
      <section class="summary">
        <article><span>Alertes actives</span><strong class="danger">${this._alerts.active_count}</strong></article>
        <article><span>En attente</span><strong class="pending">${this._alerts.pending_count}</strong></article>
        <article><span>Total suivi</span><strong>${this._alerts.tracked_count ?? 0}</strong></article>
      </section>
      ${this._renderOverviewAlerts(items)}`;
  }

  _renderOverviewAlerts(items) {
    const activeItems = items.filter((item) => item.kind === "device"
      ? item.alerts.some((source) => source.status === "active")
      : item.status === "active");
    const pendingItems = items.filter((item) => !activeItems.includes(item));
    const renderSection = (title, statusItems, status, count, emptyText) => `
      <section class="alert-group alert-group-${status}">
        <div class="alert-group-header"><h2>${title}</h2><span class="alert-group-count">${count}</span></div>
        ${statusItems.length ? `<div class="alert-list alert-list-${status}">
        ${statusItems.map((item) => item.kind === "device"
          ? this._renderDeviceGroup(item)
          : this._renderAlert(item.alert, item.status === "active")).join("")}
        </div>` : `<ha-card outlined class="alert-empty"><div class="empty compact">${emptyText}</div></ha-card>`}
      </section>`;
    return `${renderSection("Alertes actives", activeItems, "active", this._alerts.active_count, "Aucune alerte active.")}
      ${renderSection("Alertes à venir", pendingItems, "pending", this._alerts.pending_count, "Aucune alerte à venir.")}`;
  }

  _renderAlert(alert, active) {
    const value = alert.unit ? `${alert.value} ${alert.unit}` : alert.value;
    const entityExists = Boolean(this._hass?.states?.[alert.entity_id]);
    const entityName = esc(alert.name || alert.entity_id);
    const title = entityExists
      ? `<button type="button" class="entity-link" data-action="more-info" data-entity-id="${esc(alert.entity_id)}">${entityName}</button>`
      : `<strong>${entityName}</strong>`;
    return `<ha-card outlined class="alert-card ${active ? "is-active" : "is-pending"}">
      <div class="alert-card-header">
        <span class="alert-status-icon" aria-hidden="true"><ha-svg-icon path="${active ? MDI_ALERT_CIRCLE_OUTLINE : MDI_CLOCK_OUTLINE}"></ha-svg-icon></span>
        <div class="alert-title">${title}<code>${esc(alert.entity_id)}</code></div>
        <strong class="alert-current-value">${esc(value ?? "—")}</strong>
      </div>
      <div class="alert-card-content">
        <dl class="alert-details">
        ${alert.device_name ? `<div><dt>Équipement</dt><dd>${esc(alert.device_name)}</dd></div>` : ""}
        ${alert.area ? `<div><dt>Pièce</dt><dd>${esc(alert.area)}</dd></div>` : ""}
        <div class="alert-condition"><dt>Condition</dt><dd title="${esc(alert.condition)}">${esc(alert.condition)}</dd></div>
        <div><dt>Détectée</dt><dd>${esc(this._date(alert.detected_at))}</dd></div>
        <div><dt>${active ? "Active depuis" : "Temps restant"}</dt><dd>${
          active
            ? esc(this._date(alert.active_since))
            : `<span data-due="${esc(alert.due_at)}">${esc(this._remaining(alert.due_at))}</span>`
        }</dd></div>
        </dl>
      </div>
    </ha-card>`;
  }

  _renderDeviceGroup(group) {
    const first = group.alerts[0]?.alert ?? {};
    const activeCount = group.alerts.filter((item) => item.status === "active").length;
    const pendingCount = group.alerts.length - activeCount;
    const stateClass = activeCount ? "is-active" : "is-pending";
    const statusText = [
      activeCount ? `${activeCount} active${activeCount > 1 ? "s" : ""}` : "",
      pendingCount ? `${pendingCount} en attente` : "",
    ].filter(Boolean).join(" · ");
    return `<ha-card outlined class="device-alert-group ${stateClass}" data-device-id="${esc(group.device_id)}">
      <div class="device-group-header">
        <span class="alert-status-icon" aria-hidden="true"><ha-svg-icon path="${activeCount ? MDI_ALERT_CIRCLE_OUTLINE : MDI_CLOCK_OUTLINE}"></ha-svg-icon></span>
        <div><h3>${esc(first.device_name || "Appareil")}</h3>${first.area ? `<small>${esc(first.area)}</small>` : ""}</div>
        <strong>${esc(statusText)}</strong>
      </div>
      <div class="device-alert-rows">
        ${group.alerts.map((item) => this._renderDeviceAlertRow(item.alert, item.status)).join("")}
      </div>
    </ha-card>`;
  }

  _renderDeviceAlertRow(alert, status) {
    const active = status === "active";
    const entityExists = Boolean(this._hass?.states?.[alert.entity_id]);
    const entityName = esc(alert.name || alert.entity_id);
    const title = entityExists
      ? `<button type="button" class="entity-link" data-action="more-info" data-entity-id="${esc(alert.entity_id)}">${entityName}</button>`
      : `<strong>${entityName}</strong>`;
    const value = alert.unit ? `${alert.value} ${alert.unit}` : alert.value;
    const time = active
      ? esc(this._date(alert.active_since))
      : `<span data-due="${esc(alert.due_at)}">${esc(this._remaining(alert.due_at))}</span>`;
    return `<article class="device-alert-row ${active ? "is-active" : "is-pending"}">
      <div class="device-alert-source">${title}<code>${esc(alert.entity_id)}</code></div>
      <strong class="device-alert-value">${esc(value ?? "—")}</strong>
      <span class="device-alert-status">${active ? "Active" : "En attente"}</span>
      <div class="device-alert-condition"><small>Condition</small><span>${esc(alert.condition)}</span></div>
      <div class="device-alert-time"><small>${active ? "Active depuis" : "Temps restant"}</small><span>${time}</span></div>
    </article>`;
  }

  _renderAutomatic() {
    const availablePacks = this._packs.filter((pack) => pack.available);
    return `<form id="automatic-form" class="automatic-grid">
      ${availablePacks.map((pack) => {
        const config = this._config.automatic[pack.id];
        return `<section class="panel category-card">
          <div class="category-header">
            <h2>${esc(pack.name)}</h2>
            <ha-switch id="auto-${pack.id}-enabled" aria-label="Activer ${esc(pack.name)}" ${config.enabled ? "checked" : ""}></ha-switch>
          </div>
          <p>${esc(pack.description)}</p>
          <div class="fields">
            ${this._numberField(`auto-${pack.id}-delay`, "Délai propre au pack", config.delay, "secondes", 0, 31536000, "1", "id", false)}
            ${pack.id === "battery" ? this._numberField("battery-threshold", "Seuil", config.threshold, "%", -1000000000, 1000000000, "any") : ""}
          </div>
          <small>Laisser le délai vide pour utiliser le délai global.</small>
        </section>`;
      }).join("")}
      <div class="actions automatic-actions"><ha-button appearance="accent" variant="brand" data-action="save-automatic" ${this._busy ? "disabled" : ""}>Enregistrer la surveillance</ha-button></div>
    </form>`;
  }

  _renderRules() {
    const rules = this._config.rules ?? [];
    const editorOpen = this._editingRule !== null;
    const editor = editorOpen ? this._renderRuleEditor() : "";
    return `<div class="rules-layout ${editorOpen ? "has-editor" : ""}" style="--rule-editor-width:${this._ruleEditorWidth}px"><section class="panel rules-list-panel">
      <div><h2>Règles personnalisées</h2><p>Comparaisons simples sur l’état ou un attribut.</p></div>
      ${rules.length ? `<div class="table-wrap"><table><thead><tr><th>Nom</th><th>Entités</th><th>Condition</th><th>Durée</th><th class="rule-toggle-cell">Active</th></tr></thead><tbody>
        ${rules.map((rule) => `<tr class="rule-row ${this._editingRule?.id === rule.id ? "is-selected" : ""}" data-action="edit-rule" data-id="${esc(rule.id)}" tabindex="0" aria-label="Modifier la règle ${esc(rule.name)}">
          <td>${esc(rule.name)}</td><td>${rule.entity_ids.map((entityId) => `<code>${esc(entityId)}</code>`).join("")}</td>
          <td>${esc(this._ruleSummary(rule))}</td><td>${esc(durationText(rule.duration))}</td>
          <td class="rule-toggle-cell"><ha-switch haptic data-action="toggle-rule" data-id="${esc(rule.id)}" aria-label="${rule.enabled ? "Désactiver" : "Activer"} la règle ${esc(rule.name)}" ${rule.enabled ? "checked" : ""} ${this._busy ? "disabled" : ""}></ha-switch></td>
        </tr>`).join("")}
      </tbody></table></div>` : '<div class="empty">Aucune règle personnalisée.</div>'}
      <div class="actions new-rule-action"><ha-button appearance="accent" variant="brand" data-action="new-rule"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>Nouvelle règle</ha-button></div>
    </section>${editor}</div>`;
  }

  _renderRuleEditor() {
    const rule = { ...newRuleDefaults(), ...(this._editingRule ?? {}) };
    rule.value = TEXT_RULE_OPERATORS.has(rule.operator)
      ? this._ruleValueList(rule.value)
      : this._ruleValueList(rule.value)[0] ?? "";
    this._editingRule = rule;
    return `<div class="rule-editor-backdrop" data-action="cancel-rule" aria-hidden="true"></div>
    <ha-card outlined class="rule-editor-drawer" role="dialog" aria-modal="false" aria-label="${rule.id ? "Modifier" : "Créer"} une règle">
      <div class="rule-editor-resize" role="separator" aria-orientation="vertical" aria-label="Redimensionner le volet" tabindex="0"><div class="resize-indicator"></div></div>
      <ha-dialog-header show-border>
        <ha-icon-button id="rule-editor-close" slot="navigationIcon" data-action="cancel-rule"></ha-icon-button>
        <span slot="title">${rule.id ? "Modifier" : "Créer"} une règle</span>
        <span slot="subtitle">${rule.id ? esc(rule.name) : "Nouvelle règle personnalisée"}</span>
      </ha-dialog-header>
      <form id="rule-form" class="rule-editor-form">
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>Informations</h3><small>Identifiez la règle et choisissez les entités surveillées.</small></div></div>
          <div class="fields">
            ${this._textField("name", "Nom", rule.name, true, "name", "full rule-name-field")}
            <div class="field full"><span class="field-label">Entités</span><ha-selector id="rule-entity-ids"></ha-selector><small>Chaque entité est évaluée indépendamment.</small></div>
          </div>
        </section>
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>Condition</h3><small>Définissez la valeur qui doit déclencher l’alerte.</small></div></div>
          <div class="fields">
            <div class="field"><span class="field-label">Source</span><ha-select id="rule-source" data-field="source"></ha-select></div>
            <div class="field rule-attribute-field" ${rule.source === "attribute" ? "" : "hidden"}><span class="field-label">Nom de l’attribut</span><ha-input name="attribute" data-field="attribute" type="text" value="${esc(rule.attribute || "")}" aria-label="Nom de l’attribut"></ha-input></div>
            <div class="field full"><span class="field-label">Opérateur</span><ha-select id="rule-operator" data-field="operator"></ha-select></div>
            ${this._renderRuleValues(rule)}
          </div>
        </section>
        <section class="rule-editor-section">
          <div class="rule-section-heading"><div><h3>Déclenchement</h3><small>Ajoutez une temporisation et personnalisez le message exposé.</small></div></div>
          <div class="fields">
            ${this._numberField("duration", "Durée", rule.duration, "secondes", 0, 31536000, "1", "name")}
            ${this._textField("message", "Message facultatif", rule.message || "", false, "name", "full rule-message-field")}
          </div>
        </section>
        <div class="actions rule-editor-actions">${rule.id ? `<ha-button appearance="plain" variant="danger" data-action="delete-rule" data-id="${esc(rule.id)}">Supprimer</ha-button>` : ""}<span class="action-spacer"></span><ha-button appearance="plain" data-action="cancel-rule">Annuler</ha-button><ha-button appearance="accent" variant="brand" data-action="save-rule" ${this._busy ? "disabled" : ""}>Enregistrer</ha-button></div>
      </form>
    </ha-card>`;
  }

  _renderRuleValues(rule) {
    if (!TEXT_RULE_OPERATORS.has(rule.operator)) {
      return `<div class="field full"><span class="field-label">Valeur de comparaison</span><ha-input data-field="value" name="value" type="number" step="any" value="${esc(rule.value)}" required aria-label="Valeur de comparaison"></ha-input></div>`;
    }
    const values = this._ruleValueList(rule.value);
    const multipleHint = rule.operator === "equals" || rule.operator === "contains"
      ? "L’alerte se déclenche dès qu’une valeur correspond."
      : "L’alerte se déclenche seulement lorsqu’aucune valeur ne correspond.";
    return `<div class="field full rule-values-field"><span class="field-label">Valeurs de comparaison</span><div class="rule-value-list">
      ${values.map((value, index) => `<div class="rule-value-row"><ha-input data-rule-value-index="${index}" type="text" value="${esc(value)}" required aria-label="Valeur de comparaison ${index + 1}"></ha-input>${values.length > 1 ? `<ha-button appearance="plain" variant="danger" data-action="remove-rule-value" data-index="${index}" aria-label="Retirer la valeur ${index + 1}">Retirer</ha-button>` : ""}</div>`).join("")}
    </div><div class="rule-value-footer"><small>${multipleHint}</small><ha-button appearance="plain" data-action="add-rule-value"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>Ajouter une valeur</ha-button></div></div>`;
  }

  _ruleValueList(value) {
    return (Array.isArray(value) ? value : [value ?? ""]).map((item) => String(item));
  }

  _renderSettings() {
    this._ensureSettingsDraft();
    return `<form id="settings-form" class="stack">
      <section class="panel"><h2>Paramètres généraux</h2><div class="fields">
        ${this._numberField("global-delay", "Délai global", this._config.global_delay, "secondes", 0, 31536000)}
        <div class="field"><span class="field-label">Labels exclus des surveillances automatiques</span><ha-selector id="excluded-labels"></ha-selector><small>Une règle personnalisée ignore ces labels.</small></div>
      </div><small>Ce délai est utilisé lorsqu’aucun délai particulier d’entité ou de pack n’est défini.</small></section>
      <section class="panel"><h2>Exclusions explicites</h2><div class="fields">
        <div class="field"><span class="field-label">Entités exclues</span><ha-selector id="excluded-entities"></ha-selector></div>
        <div class="field"><span class="field-label">Appareils exclus</span><ha-selector id="excluded-devices"></ha-selector></div>
      </div></section>
      <section class="panel"><div><h2>Délais particuliers par entité</h2><small>Prioritaire sur le délai du pack et le délai global.</small></div>
        <div class="delay-list">${this._entityDelayDraft.length ? this._entityDelayDraft.map((row, index) => `<div class="delay-row">
          <ha-selector id="delay-entity-${index}"></ha-selector>
          <ha-input data-delay-index="${index}" type="number" min="0" max="31536000" step="1" value="${esc(row.delay)}" required aria-label="Délai en secondes"><span slot="end">secondes</span></ha-input>
          <ha-button appearance="plain" variant="danger" data-action="remove-entity-delay" data-index="${index}" aria-label="Supprimer ce délai">Supprimer</ha-button>
        </div>`).join("") : '<div class="empty compact">Aucun délai particulier.</div>'}</div>
        <div class="actions delay-add-action"><ha-button appearance="accent" variant="brand" data-action="add-entity-delay"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>Ajouter</ha-button></div>
      </section>
      <div class="actions"><ha-button appearance="accent" variant="brand" data-action="save-settings" ${this._busy ? "disabled" : ""}>Enregistrer les paramètres</ha-button></div>
    </form>`;
  }

  _numberField(id, label, value, suffix, min, max, step = "1", nameMode = "id", required = true) {
    const field = nameMode === "name" ? ` data-field="${esc(id)}"` : "";
    return `<div class="field"><span class="field-label">${esc(label)}</span><ha-input ${field} id="${esc(id)}" type="number" min="${min}" max="${max}" step="${step}" value="${esc(value ?? "")}" ${required ? "required" : ""} aria-label="${esc(label)}"><span slot="end">${esc(suffix)}</span></ha-input></div>`;
  }

  _textField(name, label, value, required = false, mode = "name", className = "") {
    const key = mode === "id" ? `id="${esc(name)}"` : `name="${esc(name)}"`;
    const field = mode === "name" ? `data-field="${esc(name)}"` : "";
    return `<div class="field${className ? ` ${esc(className)}` : ""}"><span class="field-label">${esc(label)}</span><ha-input ${key} ${field} type="text" value="${esc(value)}" ${required ? "required" : ""} aria-label="${esc(label)}"></ha-input></div>`;
  }

  _ruleSummary(rule) {
    const source = rule.source === "attribute" ? rule.attribute : "état";
    const symbols = {
      equals: "=",
      not_equals: "≠",
      contains: "contient",
      not_contains: "ne contient pas",
      above: ">",
      below: "<",
    };
    const expected = this._ruleValueList(rule.value).join(" / ");
    return `${source} ${symbols[rule.operator]} ${expected}`;
  }

  async _handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "more-info") {
      const entityId = button.dataset.entityId;
      if (!this._hass?.states?.[entityId]) return;
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId },
      }));
      return;
    }
    if (action === "tab") {
      this._activeTab = button.dataset.tab;
      this._editingRule = null;
      this._notice = null;
      this._render();
      return;
    }
    if (action === "save-automatic") {
      const form = this.shadowRoot.querySelector("#automatic-form");
      if (form && this._reportFormValidity(form) && !this._busy) {
        await this._saveAutomatic();
      }
      return;
    }
    if (action === "save-settings") {
      const form = this.shadowRoot.querySelector("#settings-form");
      if (form && this._reportFormValidity(form) && !this._busy) {
        await this._saveSettings();
      }
      return;
    }
    if (action === "new-rule") {
      this._editingRule = {};
      this._render();
      return;
    }
    if (action === "cancel-rule") {
      this._editingRule = null;
      this._render();
      return;
    }
    if (action === "add-rule-value") {
      this._captureRuleDraft();
      this._editingRule.value = [...this._ruleValueList(this._editingRule.value), ""];
      this._render();
      return;
    }
    if (action === "remove-rule-value") {
      this._captureRuleDraft();
      const values = this._ruleValueList(this._editingRule.value);
      values.splice(Number(button.dataset.index), 1);
      this._editingRule.value = values.length ? values : [""];
      this._render();
      return;
    }
    if (action === "add-entity-delay") {
      this._ensureSettingsDraft();
      this._captureEntityDelayValues();
      this._entityDelayDraft.push({ entity_id: "", delay: 900 });
      this._render();
      return;
    }
    if (action === "remove-entity-delay") {
      this._captureEntityDelayValues();
      this._entityDelayDraft.splice(Number(button.dataset.index), 1);
      this._render();
      return;
    }
    if (action === "save-rule") {
      const form = this.shadowRoot.querySelector("#rule-form");
      if (form && this._reportFormValidity(form) && !this._busy) await this._saveRule(form);
      return;
    }
    const rule = (this._config.rules || []).find((item) => item.id === button.dataset.id);
    if (!rule) return;
    if (action === "edit-rule") {
      this._editingRule = { ...rule };
      this._render();
    } else if (action === "toggle-rule") {
      const updated = await this._call(
        { type: "alert_manager/rules/update", rule_id: rule.id, rule: { enabled: !rule.enabled } },
        rule.enabled ? "Règle désactivée" : "Règle activée",
      );
      if (updated) this._replaceRule(updated);
    } else if (action === "delete-rule") {
      if (!window.confirm(`Supprimer la règle « ${rule.name} » ?`)) return;
      const result = await this._call(
        { type: "alert_manager/rules/delete", rule_id: rule.id },
        "Règle supprimée",
      );
      if (result !== null) {
        this._config.rules = this._config.rules.filter((item) => item.id !== rule.id);
        if (this._editingRule?.id === rule.id) this._editingRule = null;
        this._render();
      }
    }
  }

  _startRuleEditorResize(event) {
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

  _resizeRuleEditor(event) {
    if (!this._ruleEditorResize) return;
    const delta = this._ruleEditorResize.startX - event.clientX;
    this._setRuleEditorWidth(this._ruleEditorResize.startWidth + delta);
  }

  _setRuleEditorWidth(width) {
    const viewportWidth = Number(window.innerWidth) || 1400;
    const maximum = Math.max(360, Math.min(800, viewportWidth - 64));
    this._ruleEditorWidth = Math.round(Math.min(maximum, Math.max(360, width)));
    this.shadowRoot.querySelector(".rules-layout")?.style.setProperty(
      "--rule-editor-width",
      `${this._ruleEditorWidth}px`,
    );
  }

  _stopRuleEditorResize() {
    document.removeEventListener("pointermove", this._ruleEditorResizeMove);
    document.removeEventListener("pointerup", this._ruleEditorResizeEnd);
    document.removeEventListener("pointercancel", this._ruleEditorResizeEnd);
    document.body?.style.removeProperty("cursor");
    document.body?.style.removeProperty("user-select");
    this.shadowRoot?.querySelector(".rule-editor-resize")?.classList.remove("is-resizing");
    this._ruleEditorResize = null;
  }

  _resetRuleEditorWidth(event) {
    if (!event.target.closest?.(".rule-editor-resize")) return;
    event.preventDefault();
    this._setRuleEditorWidth(560);
  }

  _handleKeydown(event) {
    if (event.target.closest?.(".rule-editor-resize") && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      this._setRuleEditorWidth(this._ruleEditorWidth + (event.key === "ArrowLeft" ? 16 : -16));
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest?.(".rule-row[data-action=\"edit-rule\"]");
    if (!row || event.target.closest?.("ha-switch")) return;
    event.preventDefault();
    void this._handleClick({ target: row });
  }

  async _handleSubmit(event) {
    event.preventDefault();
    if (this._busy) return;
    // The save call rerenders the panel. Keep the form reference before the
    // first await because the browser may clear Event.target afterwards.
    const form = event.target;
    const formId = form?.id;
    if (formId === "automatic-form") {
      await this._saveAutomatic();
      return;
    }
    if (formId === "settings-form") {
      await this._saveSettings();
      return;
    }
    if (formId === "rule-form" && this._reportFormValidity(form)) {
      await this._saveRule(form);
    }
  }

  _reportFormValidity(form) {
    let valid = form.reportValidity?.() ?? true;
    form.querySelectorAll?.("ha-input").forEach((field) => {
      if (typeof field.reportValidity === "function") {
        valid = field.reportValidity() && valid;
      } else if (field.required && String(field.value ?? "") === "") {
        valid = false;
      }
    });
    return valid;
  }

  async _saveAutomatic() {
    const automatic = {};
    for (const pack of this._packs.filter((item) => item.available)) {
      const delayValue = this.shadowRoot.querySelector(`#auto-${pack.id}-delay`).value;
      automatic[pack.id] = {
        enabled: this.shadowRoot.querySelector(`#auto-${pack.id}-enabled`).checked,
        delay: delayValue === "" ? null : Number(delayValue),
      };
      if (pack.id === "battery") {
        automatic[pack.id].threshold = Number(
          this.shadowRoot.querySelector("#battery-threshold").value,
        );
      }
    }
    const config = await this._call({ type: "alert_manager/config/update", config: { automatic } }, "Surveillance enregistrée");
    if (config) {
      this._config = config;
      this._render();
    }
  }

  async _saveSettings() {
    this._ensureSettingsDraft();
    this._captureEntityDelayValues();
    const entityDelays = {};
    for (const row of this._entityDelayDraft) {
      if (!row.entity_id || !Number.isInteger(row.delay) || row.delay < 0) {
        this._notice = { kind: "error", text: "Chaque délai particulier doit avoir une entité et un nombre entier positif." };
        this._render();
        return;
      }
      if (row.entity_id in entityDelays) {
        this._notice = { kind: "error", text: `L’entité ${row.entity_id} est présente deux fois dans les délais.` };
        this._render();
        return;
      }
      entityDelays[row.entity_id] = row.delay;
    }
    const changes = {
      global_delay: Number(this.shadowRoot.querySelector("#global-delay").value),
      excluded_labels: [...this._settingsDraft.excluded_labels],
      excluded_entities: [...this._settingsDraft.excluded_entities],
      excluded_devices: [...this._settingsDraft.excluded_devices],
      entity_delays: entityDelays,
    };
    const config = await this._call({ type: "alert_manager/config/update", config: changes }, "Paramètres enregistrés");
    if (config) {
      this._config = config;
      this._resetSettingsDraft();
      this._render();
    }
  }

  async _saveRule(form) {
    const field = (name) =>
      form.querySelector?.(`[data-field="${name}"]`) ??
      form.elements?.namedItem(name) ??
      form.querySelector?.(`[name="${name}"]`);
    const value = (name) => field(name)?.value ?? "";
    const source = value("source");
    const operator = value("operator");
    const valueInputs = Array.from(form.querySelectorAll?.("[data-rule-value-index]") ?? []);
    const comparisonValue = TEXT_RULE_OPERATORS.has(operator)
      ? (valueInputs.length
        ? valueInputs.map((input) => String(input.value).trim())
        : this._ruleValueList(value("value")).map((item) => item.trim()))
      : String(value("value"));
    const rule = {
      name: String(value("name")).trim(),
      entity_ids: [...(this._editingRule?.entity_ids ?? [])],
      enabled: Boolean(this._editingRule?.enabled ?? true),
      source,
      attribute: source === "attribute" ? String(value("attribute")).trim() : null,
      operator,
      value: comparisonValue,
      duration: Number(value("duration")),
      message: String(value("message")).trim() || null,
    };
    const id = String(this._editingRule?.id ?? "");
    // _call renders a busy state. Keep the submitted values as the editor draft so
    // that render cannot clear the form, especially when the backend rejects it.
    this._editingRule = { ...rule, ...(id ? { id } : {}) };
    const message = id
      ? { type: "alert_manager/rules/update", rule_id: id, rule }
      : { type: "alert_manager/rules/create", rule };
    const updated = await this._call(message, id ? "Règle modifiée" : "Règle créée");
    if (updated) {
      this._editingRule = null;
      this._replaceRule(updated);
    }
  }

  _captureRuleDraft() {
    const form = this.shadowRoot.querySelector?.("#rule-form");
    if (!form || this._editingRule === null) return;
    const field = (name) => form.querySelector?.(`[data-field="${name}"]`);
    const value = (name) => field(name)?.value;
    const valueInputs = Array.from(form.querySelectorAll?.("[data-rule-value-index]") ?? []);
    this._editingRule = {
      ...this._editingRule,
      name: String(value("name") ?? this._editingRule.name ?? ""),
      enabled: Boolean(this._editingRule.enabled ?? true),
      source: value("source") ?? this._editingRule.source ?? "state",
      attribute: String(value("attribute") ?? this._editingRule.attribute ?? ""),
      operator: value("operator") ?? this._editingRule.operator ?? "equals",
      value: valueInputs.length
        ? valueInputs.map((input) => String(input.value))
        : String(value("value") ?? this._editingRule.value ?? ""),
      duration: Number(value("duration") ?? this._editingRule.duration ?? 900),
      message: String(value("message") ?? this._editingRule.message ?? ""),
    };
  }

  _replaceRule(rule) {
    const index = this._config.rules.findIndex((item) => item.id === rule.id);
    if (index === -1) this._config.rules.push(rule);
    else this._config.rules[index] = rule;
    if (this._editingRule?.id === rule.id) {
      this._editingRule = { ...this._editingRule, enabled: rule.enabled };
    }
    this._render();
  }

  _resetSettingsDraft() {
    this._settingsDraft = null;
    this._entityDelayDraft = null;
  }

  _ensureSettingsDraft() {
    if (this._settingsDraft && this._entityDelayDraft) return;
    this._settingsDraft = {
      excluded_labels: [...(this._config.excluded_labels ?? [])],
      excluded_entities: [...(this._config.excluded_entities ?? [])],
      excluded_devices: [...(this._config.excluded_devices ?? [])],
    };
    this._entityDelayDraft = Object.entries(this._config.entity_delays ?? {}).map(
      ([entity_id, delay]) => ({ entity_id, delay }),
    );
  }

  _captureEntityDelayValues() {
    if (!this._entityDelayDraft) return;
    this.shadowRoot.querySelectorAll("[data-delay-index]").forEach((input) => {
      const row = this._entityDelayDraft[Number(input.dataset.delayIndex)];
      if (row) row.delay = Number(input.value);
    });
  }

  _setEntityDelayEntity(index, value) {
    if (!this._entityDelayDraft) return;
    const entityId = typeof value === "string" ? value : "";
    if (
      entityId
      && this._entityDelayDraft.some(
        (row, rowIndex) => rowIndex !== index && row.entity_id === entityId,
      )
    ) {
      this._notice = {
        kind: "error",
        text: `L’entité ${entityId} possède déjà un délai particulier.`,
      };
      this._render();
      return;
    }
    this._entityDelayDraft[index].entity_id = entityId;
  }

  _date(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(this._hass?.locale?.language || "fr-FR", {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(date);
  }

  _remaining(value) {
    const due = new Date(value).getTime();
    if (!Number.isFinite(due)) return "—";
    const seconds = Math.max(0, Math.ceil((due - Date.now()) / 1000));
    return seconds === 0 ? "Activation en cours…" : durationText(seconds);
  }

  _updateCountdowns() {
    this.shadowRoot?.querySelectorAll("[data-due]").forEach((node) => {
      node.textContent = this._remaining(node.dataset.due);
    });
  }

  _styles() {
    return `
      :host{display:block;height:100%;background:var(--primary-background-color,#fafafa);color:var(--primary-text-color,#212121);font-family:var(--ha-font-family-body,var(--paper-font-body1_-_font-family,Roboto,Noto,sans-serif));font-size:var(--ha-font-size-m,14px);line-height:var(--ha-line-height-normal,1.6)}
      *{box-sizing:border-box}main{max-width:1400px;margin:0 auto;padding:24px}main.rules-page{max-width:none}h2{font-size:var(--ha-font-size-xl,20px);font-weight:var(--ha-font-weight-normal,400);line-height:var(--ha-line-height-condensed,1.4);margin:0 0 6px}p{margin:0;color:var(--secondary-text-color,#727272)}
      .summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:20px}.summary article,.panel{background:var(--card-background-color,#fff);border-radius:14px;box-shadow:var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.08));padding:20px}.summary article{display:flex;align-items:center;justify-content:space-between}.summary strong{font-size:30px}.danger{color:var(--error-color,#db4437)}.pending{color:var(--warning-color,#f5a623)}
      .panel{margin-bottom:20px}.alert-group{margin-bottom:24px}.alert-group+.alert-group{margin-top:28px}.alert-group-header{display:flex;align-items:center;gap:8px;margin:0 4px 12px}.alert-group-header h2{margin:0}.alert-group-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;padding:0 8px;border-radius:var(--ha-border-radius-pill,999px);background:var(--secondary-background-color,#f5f5f5);color:var(--secondary-text-color,#727272);font-size:var(--ha-font-size-s,12px);font-weight:var(--ha-font-weight-medium,500)}.alert-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:16px}.alert-card,.device-alert-group{height:100%;overflow:hidden;--alert-state-color:var(--warning-color,#f5a623)}.alert-card.is-active,.device-alert-group.is-active{--alert-state-color:var(--error-color,#db4437)}.alert-card-header{display:grid;grid-template-columns:40px minmax(0,1fr) auto;align-items:center;gap:12px;padding:16px}.alert-status-icon{display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:50%;color:var(--alert-state-color);background:color-mix(in srgb,var(--alert-state-color) 12%,transparent)}.alert-status-icon ha-svg-icon{width:24px;height:24px}.alert-title{min-width:0;line-height:1.35}.alert-title code{display:block;margin-top:2px;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400)}.alert-current-value{color:var(--alert-state-color);font-size:var(--ha-font-size-l,16px);font-weight:var(--ha-font-weight-medium,500);text-align:right;overflow-wrap:anywhere}.alert-card-content{padding:0 16px 16px;border-top:1px solid var(--divider-color,#ddd)}.entity-link{border:0;background:transparent;padding:0;color:var(--primary-text-color,#212121);font:inherit;font-weight:var(--ha-font-weight-medium,500);text-align:left;cursor:pointer}.entity-link:hover{color:var(--primary-color,#03a9f4)}.entity-link:focus-visible{outline:var(--wa-focus-ring,2px solid var(--primary-color,#03a9f4));outline-offset:3px}.device-group-header{display:grid;grid-template-columns:40px minmax(0,1fr) auto;align-items:center;gap:12px;padding:16px}.device-group-header h3{font-size:var(--ha-font-size-l,16px);font-weight:var(--ha-font-weight-medium,500);line-height:1.35;margin:0}.device-group-header small{margin:2px 0 0}.device-group-header>strong{color:var(--alert-state-color);text-align:right}.device-alert-rows{border-top:1px solid var(--divider-color,#ddd)}.device-alert-row{display:grid;grid-template-columns:minmax(0,1.25fr) auto auto;gap:10px 14px;padding:14px 16px;border-bottom:1px solid var(--divider-color,#ddd)}.device-alert-row:last-child{border-bottom:0}.device-alert-source{min-width:0}.device-alert-source code{display:block;color:var(--secondary-text-color,#727272)}.device-alert-value{color:var(--alert-state-color);text-align:right}.device-alert-status{color:var(--alert-state-color);font-weight:var(--ha-font-weight-medium,500);text-align:right}.device-alert-condition{grid-column:1/3;min-width:0}.device-alert-condition span,.device-alert-time span{display:block;overflow-wrap:anywhere}.device-alert-time{text-align:right}.device-alert-row.is-pending{--alert-state-color:var(--warning-color,#f5a623)}.device-alert-row.is-active{--alert-state-color:var(--error-color,#db4437)}
      code{font-family:var(--ha-font-family-code,ui-monospace,SFMono-Regular,monospace);font-size:12px;word-break:break-all}.alert-details{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:12px 16px;margin:14px 0 0}.alert-details div{min-width:0}dt{font-size:var(--ha-font-size-s,12px);font-weight:var(--ha-font-weight-normal,400);color:var(--secondary-text-color,#727272)}dd{margin:2px 0 0;overflow-wrap:anywhere}.alert-condition{grid-column:1/-1}.alert-condition dd{overflow:hidden;overflow-wrap:normal;text-overflow:ellipsis;white-space:nowrap}.alert-empty{margin-bottom:20px}
      .stack{display:grid;gap:16px}.automatic-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.automatic-grid .category-card{margin-bottom:0}.automatic-actions{grid-column:1/-1}.category-header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:16px}.category-header h2{margin:0}.category-header ha-switch{align-self:start}.category-card p{font-size:13px;margin-top:4px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:18px}.full{grid-column:1/-1;margin-top:16px}.field{display:flex;min-width:0;flex-direction:column;gap:6px}.field-label{font-size:var(--ha-font-size-m,14px);font-weight:var(--ha-font-weight-normal,400)}ha-input,ha-select,ha-selector{display:block;width:100%;font-weight:var(--ha-font-weight-normal,400)}ha-input{--ha-input-padding-bottom:0}ha-input>[slot="end"]{padding-inline-start:var(--ha-space-2,8px);color:var(--secondary-text-color,#727272);white-space:nowrap}.switch-field{display:flex;align-items:center;justify-content:space-between;min-height:56px;gap:16px}small{display:block;margin-top:8px;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400)}
      .actions{display:flex;justify-content:flex-end;gap:10px}.table-wrap{overflow:auto;margin-top:16px}table{border-collapse:collapse;width:100%;min-width:720px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--divider-color,#ddd);vertical-align:middle}th{font-size:12px;color:var(--secondary-text-color,#727272)}td code{display:block}.rule-row{cursor:pointer}.rule-row:hover{background:var(--ha-color-fill-neutral-quiet-hover,var(--secondary-background-color,#f5f5f5))}.rule-row:focus-visible{outline:var(--wa-focus-ring,2px solid var(--primary-color,#03a9f4));outline-offset:-2px}.rule-row.is-selected{background:var(--ha-color-fill-primary-quiet-resting,color-mix(in srgb,var(--primary-color,#03a9f4) 12%,transparent))}.rule-toggle-cell{text-align:right;width:72px}.rule-toggle-cell ha-switch{display:inline-block;vertical-align:middle}.new-rule-action{justify-content:flex-start;margin-top:16px}.rules-layout{--rule-editor-width:560px}.rules-layout.has-editor .rules-list-panel{margin-inline-end:calc(var(--rule-editor-width) + 8px)}ha-card.rule-editor-drawer{position:fixed;z-index:6;inset-block-start:calc(var(--header-height,56px) + 16px);inset-block-end:16px;inset-inline-end:16px;width:var(--rule-editor-width);max-width:calc(100vw - 64px);display:flex;flex-direction:column;overflow:visible;border-color:var(--primary-color,#03a9f4);border-width:2px;--ha-card-border-radius:var(--ha-dialog-border-radius,var(--ha-border-radius-2xl,14px))}.rule-editor-drawer ha-dialog-header{flex:none;background:var(--ha-dialog-surface-background,var(--card-background-color,#fff));border-radius:var(--ha-card-border-radius);border-end-start-radius:0;border-end-end-radius:0}.rule-editor-form{flex:1;min-height:0;overflow:auto;margin:0;padding:0;background:var(--primary-background-color,#fafafa)}.rule-editor-section{padding:20px;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#ddd)}.rule-section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.rule-section-heading h3{font-size:var(--ha-font-size-l,16px);font-weight:var(--ha-font-weight-medium,500);line-height:1.4;margin:0}.rule-section-heading small{display:block;margin-top:2px}.rule-editor-form .full{margin-top:0}.rule-name-field{margin-top:0}.rule-attribute-field[hidden]{display:none}.rule-values-field{gap:10px}.rule-value-list{display:grid;gap:10px}.rule-value-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:start}.rule-value-row ha-button{margin-top:8px}.rule-value-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}.rule-value-footer small{margin:0}.rule-editor-actions{position:sticky;bottom:0;z-index:1;align-items:center;justify-content:flex-start;padding:12px 20px max(12px,var(--safe-area-inset-bottom,0px));background:var(--card-background-color,#fff);border-top:1px solid var(--divider-color,#ddd);box-shadow:0 -2px 8px rgba(0,0,0,.08)}.action-spacer{flex:1}.rule-editor-resize{position:absolute;inset-block:var(--ha-card-border-radius) var(--ha-card-border-radius);inset-inline-start:-12px;width:24px;z-index:7;cursor:ew-resize;display:flex;align-items:center;justify-content:center;touch-action:none}.resize-indicator{height:100%;width:4px;border-radius:var(--ha-border-radius-pill,999px);background:var(--primary-color,#03a9f4);opacity:0;transform:scaleX(0);transition:opacity 180ms ease-in-out,transform 180ms ease-in-out}.rule-editor-resize:hover .resize-indicator,.rule-editor-resize:focus-visible .resize-indicator,.rule-editor-resize.is-resizing .resize-indicator{opacity:1;transform:scaleX(1)}.rule-editor-resize:focus-visible{outline:none}.rule-editor-backdrop{display:none}.delay-list{display:grid;gap:10px;margin-top:16px}.delay-add-action{justify-content:flex-start;margin-top:16px}.delay-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,260px) auto;gap:10px;align-items:start}.delay-row ha-input{min-width:0}.delay-row>ha-button{margin-top:8px}
      .empty,.loading{padding:40px;text-align:center;color:var(--secondary-text-color,#727272)}.empty.compact{padding:20px}.notice{padding:12px 16px;border-radius:8px;margin-bottom:16px}.notice.success{background:color-mix(in srgb,var(--success-color,#43a047) 15%,transparent);color:var(--success-color,#2e7d32)}.notice.error{background:color-mix(in srgb,var(--error-color,#db4437) 15%,transparent);color:var(--error-color,#db4437)}
      @media(max-width:1000px){.rules-layout.has-editor .rules-list-panel{margin-inline-end:0}.rule-editor-backdrop{display:block;position:fixed;z-index:5;inset:var(--header-height,56px) 0 0;background:rgba(0,0,0,.32)}}
      @media(max-width:700px){main{padding:12px}.summary,.automatic-grid{grid-template-columns:1fr}.summary article{padding:14px}.fields{grid-template-columns:1fr}.alert-list{grid-template-columns:1fr}.panel{padding:15px}.alert-card-header,.device-group-header{grid-template-columns:40px minmax(0,1fr)}.alert-current-value,.device-group-header>strong{grid-column:2;text-align:left}.alert-details{grid-template-columns:1fr}.alert-condition dd{white-space:normal}.device-alert-row{grid-template-columns:minmax(0,1fr) auto}.device-alert-status{grid-column:2}.device-alert-condition{grid-column:1/-1}.device-alert-time{grid-column:1/-1;text-align:left}.row.between{align-items:flex-start}.category-card .row.between>div{padding-right:8px}.actions ha-button{width:100%}.delay-row{grid-template-columns:1fr}.delay-row ha-button{width:100%}ha-card.rule-editor-drawer{inset-block-start:var(--header-height,56px);inset-block-end:calc(var(--header-height,56px) + var(--safe-area-inset-bottom,0px));inset-inline-end:0;width:100%;max-width:none;border-width:0;overflow:hidden;--ha-card-border-radius:var(--ha-border-radius-square,0)}.rule-editor-resize{display:none}.rule-section-heading,.rule-value-footer{align-items:stretch;flex-direction:column}.rule-value-row{grid-template-columns:1fr}.rule-value-row ha-button{margin-top:0}.rule-editor-actions{flex-wrap:wrap}.rule-editor-actions .action-spacer{display:none}}
    `;
  }
}

if (!customElements.get("alert-manager-panel")) {
  customElements.define("alert-manager-panel", AlertManagerPanel);
}

export { AlertManagerPanel, buildOverviewItems, durationText, lines, newRuleDefaults };
