const TABS = [
  ["overview", "Vue d’ensemble", "mdi:view-dashboard-outline"],
  ["automatic", "Surveillance automatique", "mdi:radar"],
  ["rules", "Règles personnalisées", "mdi:format-list-checks"],
  ["settings", "Exclusions et paramètres", "mdi:tune-variant"],
];

const CATEGORIES = [
  ["unavailable", "Entités indisponibles", "État unavailable sur toutes les entités"],
  ["connectivity", "Connectivité", "Binary sensors connectivity à off"],
  ["unifi", "Équipements UniFi", "Trackers routeur UniFi absents"],
  ["battery", "Batteries faibles", "Capteurs battery sous leur seuil"],
];

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
  value: "",
  duration: 900,
  message: "",
});

class AlertManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._alerts = { active_count: 0, pending_count: 0, alerts: [], pending: [] };
    this._activeTab = "overview";
    this._editingRule = null;
    this._loading = true;
    this._busy = false;
    this._notice = null;
    this._timer = null;
    this._sensorState = null;
    this._settingsDraft = null;
    this._entityDelayDraft = null;
    this._configuredControls = new WeakSet();
    this.shadowRoot.addEventListener("click", (event) => this._handleClick(event));
    this.shadowRoot.addEventListener("submit", (event) => this._handleSubmit(event));
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
  }

  set narrow(value) {
    this._narrow = value;
    const shell = this.shadowRoot?.querySelector("#panel-shell");
    if (shell) {
      shell.narrow = Boolean(value);
    }
  }

  connectedCallback() {
    this._render();
    if (this._hass && !this._config) this._load();
    this._timer = window.setInterval(() => this._updateCountdowns(), 1000);
  }

  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
  }

  async _load() {
    this._loadPromise = Promise.all([
      this._hass.callWS({ type: "alert_manager/config/get" }),
      this._hass.callWS({ type: "alert_manager/alerts/list" }),
    ]);
    this._loading = true;
    this._render();
    try {
      [this._config, this._alerts] = await this._loadPromise;
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
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-top-app-bar-fixed id="panel-shell" center-title back-button>
        <ha-tab-group slot="title" class="native-tabs" aria-label="Sections">
          ${TABS.map(
            ([id, label, icon]) => `<ha-tab-group-tab slot="nav" panel="${id}" data-action="tab" data-tab="${id}"
              ${id === this._activeTab ? "active" : ""}>
              <span class="tab-label"><ha-icon icon="${icon}" aria-hidden="true"></ha-icon><span>${esc(label)}</span></span>
            </ha-tab-group-tab>`,
          ).join("")}
        </ha-tab-group>
        <main>
          <header>
            <div>
              <h1>Alertes</h1>
              <p>Détection centralisée des anomalies Home Assistant</p>
            </div>
            <div class="header-count ${this._alerts.active_count ? "has-alert" : ""}">
              <strong>${this._alerts.active_count}</strong>
              <span>active${this._alerts.active_count > 1 ? "s" : ""}</span>
            </div>
          </header>
          ${this._notice ? `<div class="notice ${this._notice.kind}">${esc(this._notice.text)}</div>` : ""}
          ${content}
        </main>
      </ha-top-app-bar-fixed>`;
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

  _configureSelect(id, options, value) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element || this._configuredControls.has(element)) return;
    element.options = options;
    element.value = value;
    element.addEventListener("selected", (event) => {
      element.value = event.detail?.value;
    });
    this._configuredControls.add(element);
  }

  _hydrateSelectors() {
    const shell = this.shadowRoot.querySelector("#panel-shell");
    if (shell) shell.narrow = Boolean(this._narrow);
    if (!this._hass || !this._config) return;
    if (this._editingRule !== null) {
      this._configureSelect(
        "rule-source",
        [
          { value: "state", label: "État principal" },
          { value: "attribute", label: "Attribut" },
        ],
        this._editingRule.source ?? "state",
      );
      this._configureSelect(
        "rule-operator",
        [
          { value: "equals", label: "Égal à" },
          { value: "not_equals", label: "Différent de" },
          { value: "above", label: "Supérieur à" },
          { value: "below", label: "Inférieur à" },
        ],
        this._editingRule.operator ?? "equals",
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
        (value) => { row.entity_id = typeof value === "string" ? value : ""; },
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

  _renderOverview() {
    return `
      <section class="summary">
        <article><span>Alertes actives</span><strong class="danger">${this._alerts.active_count}</strong></article>
        <article><span>En attente</span><strong class="pending">${this._alerts.pending_count}</strong></article>
        <article><span>Total suivi</span><strong>${this._alerts.active_count + this._alerts.pending_count}</strong></article>
      </section>
      ${this._renderAlertGroup("Alertes actives", this._alerts.alerts, true)}
      ${this._renderAlertGroup("Alertes en attente", this._alerts.pending, false)}`;
  }

  _renderAlertGroup(title, alerts, active) {
    if (!alerts.length) {
      return `<section class="panel"><h2>${esc(title)}</h2><div class="empty">Aucune alerte ${active ? "active" : "en attente"}.</div></section>`;
    }
    return `<section class="panel"><h2>${esc(title)}</h2><div class="alert-list">
      ${alerts.map((alert) => this._renderAlert(alert, active)).join("")}
    </div></section>`;
  }

  _renderAlert(alert, active) {
    const value = alert.unit ? `${alert.value} ${alert.unit}` : alert.value;
    const entityExists = Boolean(this._hass?.states?.[alert.entity_id]);
    const entityName = esc(alert.name || alert.entity_id);
    const title = entityExists
      ? `<button type="button" class="entity-link" data-action="more-info" data-entity-id="${esc(alert.entity_id)}">${entityName}</button>`
      : `<strong>${entityName}</strong>`;
    return `<article class="alert-card ${active ? "is-active" : "is-pending"}">
      <div class="alert-title">
        <div>${title}<code>${esc(alert.entity_id)}</code></div>
      </div>
      <dl>
        <div><dt>Équipement</dt><dd>${esc(alert.device_name || "—")}</dd></div>
        <div><dt>Pièce</dt><dd>${esc(alert.area || "—")}</dd></div>
        <div><dt>Valeur</dt><dd>${esc(value ?? "—")}</dd></div>
        <div class="alert-condition"><dt>Condition</dt><dd title="${esc(alert.condition)}">${esc(alert.condition)}</dd></div>
        <div><dt>Détectée</dt><dd>${esc(this._date(alert.detected_at))}</dd></div>
        <div><dt>${active ? "Active depuis" : "Temps restant"}</dt><dd>${
          active
            ? esc(this._date(alert.active_since))
            : `<span data-due="${esc(alert.due_at)}">${esc(this._remaining(alert.due_at))}</span>`
        }</dd></div>
      </dl>
    </article>`;
  }

  _renderAutomatic() {
    return `<form id="automatic-form" class="stack">
      ${CATEGORIES.map(([id, title, description]) => {
        const config = this._config.automatic[id];
        return `<section class="panel category-card">
          <div class="row between">
            <div><h2>${esc(title)}</h2><p>${esc(description)}</p></div>
            <ha-switch id="auto-${id}-enabled" aria-label="Activer ${esc(title)}" ${config.enabled ? "checked" : ""}></ha-switch>
          </div>
          <div class="fields">
            ${this._numberField(`auto-${id}-delay`, "Délai", config.delay, "secondes", 0, 31536000)}
            ${id === "battery" ? this._numberField("battery-threshold", "Seuil", config.threshold, "%", -1000000000, 1000000000, "any") : ""}
          </div>
          ${id === "unavailable" ? "<small>Tous les domaines sont surveillés. Seul l’état unavailable est concerné.</small>" : ""}
          <small>Délai actuel : ${esc(durationText(config.delay))}</small>
        </section>`;
      }).join("")}
      <div class="actions"><ha-button appearance="filled" data-action="save-automatic" ${this._busy ? "disabled" : ""}>Enregistrer la surveillance</ha-button></div>
    </form>`;
  }

  _renderRules() {
    const rules = this._config.rules ?? [];
    const editor = this._editingRule !== null ? this._renderRuleEditor() : "";
    return `<section class="panel">
      <div class="row between"><div><h2>Règles personnalisées</h2><p>Comparaisons simples sur l’état ou un attribut.</p></div>
      <ha-button appearance="filled" data-action="new-rule">Nouvelle règle</ha-button></div>
      ${rules.length ? `<div class="table-wrap"><table><thead><tr><th>Nom</th><th>Entités</th><th>Condition</th><th>Durée</th><th>Active</th><th></th></tr></thead><tbody>
        ${rules.map((rule) => `<tr>
          <td>${esc(rule.name)}</td><td>${rule.entity_ids.map((entityId) => `<code>${esc(entityId)}</code>`).join("")}</td>
          <td>${esc(this._ruleSummary(rule))}</td><td>${esc(durationText(rule.duration))}</td>
          <td><ha-button appearance="plain" variant="${rule.enabled ? "brand" : "danger"}" size="xs" class="rule-status" data-action="toggle-rule" data-id="${esc(rule.id)}" aria-label="${rule.enabled ? "Désactiver" : "Activer"} la règle" title="${rule.enabled ? "Règle active" : "Règle inactive"}">${rule.enabled ? "✓" : "✕"}</ha-button></td>
          <td class="nowrap"><ha-button appearance="filled" size="s" data-action="edit-rule" data-id="${esc(rule.id)}">Modifier</ha-button> <ha-button appearance="plain" variant="danger" size="s" data-action="delete-rule" data-id="${esc(rule.id)}">Supprimer</ha-button></td>
        </tr>`).join("")}
      </tbody></table></div>` : '<div class="empty">Aucune règle personnalisée.</div>'}
    </section>${editor}`;
  }

  _renderRuleEditor() {
    const rule = { ...newRuleDefaults(), ...(this._editingRule ?? {}) };
    this._editingRule = rule;
    return `<section class="panel editor"><h2>${rule.id ? "Modifier" : "Créer"} une règle</h2>
      <form id="rule-form" class="fields">
        <input type="hidden" name="id" value="${esc(rule.id || "")}">
        ${this._textField("name", "Nom", rule.name, true)}
        <div class="switch-field"><span class="field-label">Règle activée</span><ha-switch id="rule-enabled" data-field="enabled" ${rule.enabled ? "checked" : ""}></ha-switch></div>
        <div class="field full"><span class="field-label">Entités</span><ha-selector id="rule-entity-ids"></ha-selector><small>Chaque entité est évaluée indépendamment.</small></div>
        <div class="field"><span class="field-label">Source</span><ha-select id="rule-source" data-field="source"></ha-select></div>
        ${this._textField("attribute", "Nom de l’attribut", rule.attribute || "")}
        <div class="field"><span class="field-label">Opérateur</span><ha-select id="rule-operator" data-field="operator"></ha-select></div>
        ${this._textField("value", "Valeur de comparaison", rule.value, true)}
        ${this._numberField("duration", "Durée", rule.duration, "secondes", 0, 31536000, "1", "name")}
        ${this._textField("message", "Message facultatif", rule.message || "")}
        <div class="actions full"><ha-button appearance="plain" data-action="cancel-rule">Annuler</ha-button><ha-button appearance="filled" data-action="save-rule" ${this._busy ? "disabled" : ""}>Enregistrer</ha-button></div>
      </form>
    </section>`;
  }

  _renderSettings() {
    this._ensureSettingsDraft();
    return `<form id="settings-form" class="stack">
      <section class="panel"><h2>Paramètres généraux</h2><div class="fields">
        ${this._numberField("global-delay", "Délai global", this._config.global_delay, "secondes", 0, 31536000)}
        <div class="field"><span class="field-label">Labels exclus des surveillances automatiques</span><ha-selector id="excluded-labels"></ha-selector><small>Une règle personnalisée ignore ces labels.</small></div>
      </div><small>Délai actuel : ${esc(durationText(this._config.global_delay))}. Il est utilisé après les délais de règle, d’entité, d’attribut et de catégorie.</small></section>
      <section class="panel"><h2>Exclusions explicites</h2><div class="fields">
        <div class="field"><span class="field-label">Entités exclues</span><ha-selector id="excluded-entities"></ha-selector></div>
        <div class="field"><span class="field-label">Appareils exclus</span><ha-selector id="excluded-devices"></ha-selector></div>
      </div></section>
      <section class="panel"><div class="row between"><div><h2>Délais particuliers par entité</h2><small>Prioritaire sur alert_delay et le délai de catégorie.</small></div><ha-button appearance="outlined" data-action="add-entity-delay">Ajouter</ha-button></div>
        <div class="delay-list">${this._entityDelayDraft.length ? this._entityDelayDraft.map((row, index) => `<div class="delay-row">
          <ha-selector id="delay-entity-${index}"></ha-selector>
          <ha-input data-delay-index="${index}" type="number" min="0" max="31536000" step="1" value="${esc(row.delay)}" required aria-label="Délai en secondes"><span slot="end">secondes</span></ha-input>
          <ha-button appearance="plain" variant="danger" data-action="remove-entity-delay" data-index="${index}" aria-label="Supprimer ce délai">Supprimer</ha-button>
        </div>`).join("") : '<div class="empty compact">Aucun délai particulier.</div>'}</div>
      </section>
      <div class="actions"><ha-button appearance="filled" data-action="save-settings" ${this._busy ? "disabled" : ""}>Enregistrer les paramètres</ha-button></div>
    </form>`;
  }

  _numberField(id, label, value, suffix, min, max, step = "1", nameMode = "id") {
    const field = nameMode === "name" ? ` data-field="${esc(id)}"` : "";
    return `<div class="field"><span class="field-label">${esc(label)}</span><ha-input ${field} id="${esc(id)}" type="number" min="${min}" max="${max}" step="${step}" value="${esc(value)}" required aria-label="${esc(label)}"><span slot="end">${esc(suffix)}</span></ha-input></div>`;
  }

  _textField(name, label, value, required = false, mode = "name") {
    const key = mode === "id" ? `id="${esc(name)}"` : `name="${esc(name)}"`;
    const field = mode === "name" ? `data-field="${esc(name)}"` : "";
    return `<div class="field"><span class="field-label">${esc(label)}</span><ha-input ${key} ${field} type="text" value="${esc(value)}" ${required ? "required" : ""} aria-label="${esc(label)}"></ha-input></div>`;
  }

  _ruleSummary(rule) {
    const source = rule.source === "attribute" ? rule.attribute : "état";
    const symbols = { equals: "=", not_equals: "≠", above: ">", below: "<" };
    return `${source} ${symbols[rule.operator]} ${rule.value}`;
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
        this._render();
      }
    }
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
    for (const [id] of CATEGORIES) {
      automatic[id] = {
        enabled: this.shadowRoot.querySelector(`#auto-${id}-enabled`).checked,
        delay: Number(this.shadowRoot.querySelector(`#auto-${id}-delay`).value),
      };
    }
    automatic.battery.threshold = Number(this.shadowRoot.querySelector("#battery-threshold").value);
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
    const rule = {
      name: String(value("name")).trim(),
      entity_ids: [...(this._editingRule?.entity_ids ?? [])],
      enabled: Boolean(field("enabled")?.checked),
      source,
      attribute: source === "attribute" ? String(value("attribute")).trim() : null,
      operator: value("operator"),
      value: String(value("value")),
      duration: Number(value("duration")),
      message: String(value("message")).trim() || null,
    };
    const id = String(value("id"));
    // _call renders a busy state. Keep the submitted values as the editor draft so
    // that render cannot clear the form, especially when the backend rejects it.
    this._editingRule = { ...rule, ...(id ? { id } : {}) };
    const message = id
      ? { type: "alert_manager/rules/update", rule_id: id, rule }
      : { type: "alert_manager/rules/create", rule };
    const updated = await this._call(message, id ? "Règle modifiée" : "Règle créée");
    if (updated) {
      this._replaceRule(updated);
      this._editingRule = null;
    }
  }

  _replaceRule(rule) {
    const index = this._config.rules.findIndex((item) => item.id === rule.id);
    if (index === -1) this._config.rules.push(rule);
    else this._config.rules[index] = rule;
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
      *{box-sizing:border-box}ha-top-app-bar-fixed{--app-header-background-color:var(--sidebar-background-color,var(--card-background-color,#fff));--app-header-text-color:var(--sidebar-text-color,var(--primary-text-color,#212121));--app-header-border-bottom:1px solid var(--divider-color,#ddd)}.native-tabs{width:100%;color:var(--sidebar-text-color,var(--primary-text-color,#212121));--ha-tab-active-text-color:var(--primary-color);--ha-tab-indicator-color:var(--primary-color);--ha-tab-track-color:transparent}.tab-label{display:inline-flex;align-items:center;gap:var(--ha-space-2,8px);white-space:nowrap}.tab-label ha-icon{width:24px;height:24px}main{max-width:1400px;margin:0 auto;padding:24px}header{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:20px}h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:0 0 6px}p{margin:0;color:var(--secondary-text-color,#727272)}
      .header-count{min-width:94px;padding:12px 18px;border-radius:18px;text-align:center;background:var(--secondary-background-color,#fff)}.header-count strong{font-size:28px;display:block}.header-count span{font-size:12px;color:var(--secondary-text-color,#727272)}.header-count.has-alert{background:var(--error-color,#db4437);color:white}.header-count.has-alert span{color:white}
      .summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:20px}.summary article,.panel{background:var(--card-background-color,#fff);border-radius:14px;box-shadow:var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.08));padding:20px}.summary article{display:flex;align-items:center;justify-content:space-between}.summary strong{font-size:30px}.danger{color:var(--error-color,#db4437)}.pending{color:var(--warning-color,#f5a623)}
      .panel{margin-bottom:20px}.alert-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin-top:16px}.alert-card{border:1px solid var(--divider-color,#ddd);border-left:5px solid var(--warning-color,#f5a623);border-radius:10px;padding:14px}.alert-card.is-active{border-left-color:var(--error-color,#db4437)}
      .alert-title,.row{display:flex;align-items:center;gap:14px}.between{justify-content:space-between}.alert-title{justify-content:space-between;margin-bottom:12px}.alert-title code{display:block;margin-top:3px}.entity-link{border:0;background:transparent;padding:0;color:var(--primary-color,#03a9f4);font-weight:700;text-align:left}.entity-link:hover{text-decoration:underline}.entity-link:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:3px}
      code{font-family:var(--ha-font-family-code,ui-monospace,SFMono-Regular,monospace);font-size:12px;word-break:break-all}dl{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:10px;margin:0}dl div{min-width:0}dt{font-size:11px;text-transform:uppercase;color:var(--secondary-text-color,#727272)}dd{margin:3px 0 0;overflow-wrap:anywhere}.alert-condition dd{overflow:hidden;overflow-wrap:normal;text-overflow:ellipsis;white-space:nowrap}
      .stack{display:grid;gap:16px}.category-card p{font-size:13px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:18px}.full{grid-column:1/-1;margin-top:16px}.field{display:flex;min-width:0;flex-direction:column;gap:6px}.field-label{font-size:var(--ha-font-size-m,14px);font-weight:var(--ha-font-weight-medium,500)}ha-input,ha-select,ha-selector{display:block;width:100%;font-weight:var(--ha-font-weight-normal,400)}ha-input{--ha-input-padding-bottom:0}ha-input>[slot="end"]{padding-inline-start:var(--ha-space-2,8px);color:var(--secondary-text-color,#727272);white-space:nowrap}.switch-field{display:flex;align-items:center;justify-content:space-between;min-height:56px;gap:16px}.rule-status{font-size:var(--ha-font-size-l,16px)}small{display:block;margin-top:8px;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400)}
      .actions{display:flex;justify-content:flex-end;gap:10px}.table-wrap{overflow:auto;margin-top:16px}table{border-collapse:collapse;width:100%;min-width:850px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--divider-color,#ddd);vertical-align:middle}th{font-size:12px;color:var(--secondary-text-color,#727272)}td code{display:block}.nowrap{white-space:nowrap}.editor{scroll-margin-top:12px}.delay-list{display:grid;gap:10px;margin-top:16px}.delay-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,260px) auto;gap:10px;align-items:end}.delay-row ha-input{min-width:0}
      .empty,.loading{padding:40px;text-align:center;color:var(--secondary-text-color,#727272)}.empty.compact{padding:20px}.notice{padding:12px 16px;border-radius:8px;margin-bottom:16px}.notice.success{background:color-mix(in srgb,var(--success-color,#43a047) 15%,transparent);color:var(--success-color,#2e7d32)}.notice.error{background:color-mix(in srgb,var(--error-color,#db4437) 15%,transparent);color:var(--error-color,#db4437)}
      @media(max-width:700px){main{padding:12px}header{align-items:flex-start}.header-count{min-width:78px}.summary{grid-template-columns:1fr}.summary article{padding:14px}.fields{grid-template-columns:1fr}.alert-list{grid-template-columns:1fr}.panel{padding:15px}dl{grid-template-columns:1fr}.alert-condition dd{white-space:normal}.row.between{align-items:flex-start}.category-card .row.between>div{padding-right:8px}.actions ha-button{width:100%}.delay-row{grid-template-columns:1fr}.delay-row ha-button{width:100%}}
    `;
  }
}

if (!customElements.get("alert-manager-panel")) {
  customElements.define("alert-manager-panel", AlertManagerPanel);
}

export { AlertManagerPanel, durationText, lines, newRuleDefaults };
