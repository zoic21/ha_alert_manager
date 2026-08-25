const TABS = [
  ["overview", "Vue d’ensemble"],
  ["automatic", "Surveillance automatique"],
  ["rules", "Règles personnalisées"],
  ["settings", "Exclusions et paramètres"],
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
        <nav aria-label="Sections">
          ${TABS.map(
            ([id, label]) => `<button class="tab ${id === this._activeTab ? "active" : ""}"
              data-action="tab" data-tab="${id}">${esc(label)}</button>`,
          ).join("")}
        </nav>
        ${this._notice ? `<div class="notice ${this._notice.kind}">${esc(this._notice.text)}</div>` : ""}
        ${content}
      </main>`;
    this._hydrateSelectors();
    this._updateCountdowns();
  }

  _configureSelector(id, selector, value, onChange) {
    const element = this.shadowRoot.querySelector(`#${id}`);
    if (!element) return;
    element.hass = this._hass;
    element.selector = selector;
    element.value = value;
    element.addEventListener("value-changed", (event) => onChange(event.detail?.value));
  }

  _hydrateSelectors() {
    if (!this._hass || !this._config) return;
    if (this._editingRule !== null) {
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
        <div><dt>Condition</dt><dd>${esc(alert.condition)}</dd></div>
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
            <label class="switch"><input id="auto-${id}-enabled" type="checkbox" ${config.enabled ? "checked" : ""}><span></span></label>
          </div>
          <div class="fields">
            ${this._numberField(`auto-${id}-delay`, "Délai", config.delay, "secondes", 0, 31536000)}
            ${id === "battery" ? this._numberField("battery-threshold", "Seuil", config.threshold, "%", -1000000000, 1000000000, "any") : ""}
          </div>
          ${id === "unavailable" ? "<small>Tous les domaines sont surveillés. Seul l’état unavailable est concerné.</small>" : ""}
          <small>Délai actuel : ${esc(durationText(config.delay))}</small>
        </section>`;
      }).join("")}
      <div class="actions"><button class="primary" type="submit" ${this._busy ? "disabled" : ""}>Enregistrer la surveillance</button></div>
    </form>`;
  }

  _renderRules() {
    const rules = this._config.rules ?? [];
    const editor = this._editingRule !== null ? this._renderRuleEditor() : "";
    return `<section class="panel">
      <div class="row between"><div><h2>Règles personnalisées</h2><p>Comparaisons simples sur l’état ou un attribut.</p></div>
      <button class="primary" data-action="new-rule">Nouvelle règle</button></div>
      ${rules.length ? `<div class="table-wrap"><table><thead><tr><th>Nom</th><th>Entités</th><th>Condition</th><th>Durée</th><th>Active</th><th></th></tr></thead><tbody>
        ${rules.map((rule) => `<tr>
          <td>${esc(rule.name)}</td><td>${rule.entity_ids.map((entityId) => `<code>${esc(entityId)}</code>`).join("")}</td>
          <td>${esc(this._ruleSummary(rule))}</td><td>${esc(durationText(rule.duration))}</td>
          <td><button class="icon-button" data-action="toggle-rule" data-id="${esc(rule.id)}" title="Activer/désactiver">${rule.enabled ? "✓" : "—"}</button></td>
          <td class="nowrap"><button data-action="edit-rule" data-id="${esc(rule.id)}">Modifier</button> <button class="danger-button" data-action="delete-rule" data-id="${esc(rule.id)}">Supprimer</button></td>
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
        <label class="full">Entités<ha-selector id="rule-entity-ids"></ha-selector><small>Chaque entité est évaluée indépendamment.</small></label>
        <label>Source<select name="source"><option value="state" ${rule.source === "state" ? "selected" : ""}>État principal</option><option value="attribute" ${rule.source === "attribute" ? "selected" : ""}>Attribut</option></select></label>
        ${this._textField("attribute", "Nom de l’attribut", rule.attribute || "")}
        <label>Opérateur<select name="operator">
          ${[["equals", "Égal à"], ["not_equals", "Différent de"], ["above", "Supérieur à"], ["below", "Inférieur à"]].map(([value, label]) => `<option value="${value}" ${rule.operator === value ? "selected" : ""}>${label}</option>`).join("")}
        </select></label>
        ${this._textField("value", "Valeur de comparaison", rule.value, true)}
        ${this._numberField("duration", "Durée", rule.duration, "secondes", 0, 31536000, "1", "name")}
        ${this._textField("message", "Message facultatif", rule.message || "")}
        <label class="checkbox"><input name="enabled" type="checkbox" ${rule.enabled ? "checked" : ""}> Règle activée</label>
        <div class="actions full"><button type="button" data-action="cancel-rule">Annuler</button><button class="primary" type="button" data-action="save-rule" ${this._busy ? "disabled" : ""}>Enregistrer</button></div>
      </form>
    </section>`;
  }

  _renderSettings() {
    this._ensureSettingsDraft();
    return `<form id="settings-form" class="stack">
      <section class="panel"><h2>Paramètres généraux</h2><div class="fields">
        ${this._numberField("global-delay", "Délai global", this._config.global_delay, "secondes", 0, 31536000)}
        <label>Labels exclus des surveillances automatiques<ha-selector id="excluded-labels"></ha-selector><small>Une règle personnalisée ignore ces labels.</small></label>
      </div><small>Délai actuel : ${esc(durationText(this._config.global_delay))}. Il est utilisé après les délais de règle, d’entité, d’attribut et de catégorie.</small></section>
      <section class="panel"><h2>Exclusions explicites</h2><div class="fields">
        <label>Entités exclues<ha-selector id="excluded-entities"></ha-selector></label>
        <label>Appareils exclus<ha-selector id="excluded-devices"></ha-selector></label>
      </div></section>
      <section class="panel"><div class="row between"><div><h2>Délais particuliers par entité</h2><small>Prioritaire sur alert_delay et le délai de catégorie.</small></div><button type="button" data-action="add-entity-delay">Ajouter</button></div>
        <div class="delay-list">${this._entityDelayDraft.length ? this._entityDelayDraft.map((row, index) => `<div class="delay-row">
          <ha-selector id="delay-entity-${index}"></ha-selector>
          <div class="input-suffix"><input data-delay-index="${index}" type="number" min="0" max="31536000" step="1" value="${esc(row.delay)}" required><span>secondes</span></div>
          <button type="button" data-action="remove-entity-delay" data-index="${index}" aria-label="Supprimer ce délai">Supprimer</button>
        </div>`).join("") : '<div class="empty compact">Aucun délai particulier.</div>'}</div>
      </section>
      <div class="actions"><button class="primary" type="submit" ${this._busy ? "disabled" : ""}>Enregistrer les paramètres</button></div>
    </form>`;
  }

  _numberField(id, label, value, suffix, min, max, step = "1", nameMode = "id") {
    const name = nameMode === "name" ? ` name="${esc(id)}"` : "";
    return `<label>${esc(label)}<div class="input-suffix"><input ${name} id="${esc(id)}" type="number" min="${min}" max="${max}" step="${step}" value="${esc(value)}" required><span>${esc(suffix)}</span></div></label>`;
  }

  _textField(name, label, value, required = false, mode = "name") {
    const key = mode === "id" ? `id="${esc(name)}"` : `name="${esc(name)}"`;
    return `<label>${esc(label)}<input ${key} type="text" value="${esc(value)}" ${required ? "required" : ""}></label>`;
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
      if (form && form.reportValidity() && !this._busy) await this._saveRule(form);
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
    if (event.target.id === "automatic-form") await this._saveAutomatic();
    if (event.target.id === "settings-form") await this._saveSettings();
    if (event.target.id === "rule-form" && event.target.reportValidity()) {
      await this._saveRule(event.target);
    }
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
    const field = (name) => form.elements.namedItem(name);
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
      :host{display:block;min-height:100%;background:var(--primary-background-color,#fafafa);color:var(--primary-text-color,#212121);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
      *{box-sizing:border-box} main{max-width:1400px;margin:0 auto;padding:24px} header{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:20px}h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:0 0 6px}p{margin:0;color:var(--secondary-text-color,#727272)}
      .header-count{min-width:94px;padding:12px 18px;border-radius:18px;text-align:center;background:var(--secondary-background-color,#fff)}.header-count strong{font-size:28px;display:block}.header-count span{font-size:12px;color:var(--secondary-text-color,#727272)}.header-count.has-alert{background:var(--error-color,#db4437);color:white}.header-count.has-alert span{color:white}
      nav{display:flex;gap:6px;overflow:auto;border-bottom:1px solid var(--divider-color,#ddd);margin-bottom:20px}.tab{border:0;border-bottom:3px solid transparent;background:transparent;padding:12px 16px;white-space:nowrap;color:var(--secondary-text-color,#727272);cursor:pointer}.tab.active{color:var(--primary-color,#03a9f4);border-color:var(--primary-color,#03a9f4);font-weight:600}
      button{font:inherit;border:1px solid var(--divider-color,#ccc);border-radius:8px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#212121);padding:8px 12px;cursor:pointer}button:disabled{opacity:.55;cursor:wait}.primary{background:var(--primary-color,#03a9f4);border-color:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}.danger-button{color:var(--error-color,#db4437)}
      .summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:20px}.summary article,.panel{background:var(--card-background-color,#fff);border-radius:14px;box-shadow:var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.08));padding:20px}.summary article{display:flex;align-items:center;justify-content:space-between}.summary strong{font-size:30px}.danger{color:var(--error-color,#db4437)}.pending{color:var(--warning-color,#f5a623)}
      .panel{margin-bottom:20px}.alert-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin-top:16px}.alert-card{border:1px solid var(--divider-color,#ddd);border-left:5px solid var(--warning-color,#f5a623);border-radius:10px;padding:14px}.alert-card.is-active{border-left-color:var(--error-color,#db4437)}
      .alert-title,.row{display:flex;align-items:center;gap:14px}.between{justify-content:space-between}.alert-title{justify-content:space-between;margin-bottom:12px}.alert-title code{display:block;margin-top:3px}.entity-link{border:0;background:transparent;padding:0;color:var(--primary-color,#03a9f4);font-weight:700;text-align:left}.entity-link:hover{text-decoration:underline}.entity-link:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:3px}
      code{font-family:ui-monospace,SFMono-Regular,monospace;font-size:12px;word-break:break-all}dl{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0}dl div{min-width:0}dt{font-size:11px;text-transform:uppercase;color:var(--secondary-text-color,#727272)}dd{margin:3px 0 0;overflow-wrap:anywhere}
      .stack{display:grid;gap:16px}.category-card p{font-size:13px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:18px}.full{grid-column:1/-1;display:block;margin-top:16px}label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:500}input,select,textarea{width:100%;font:inherit;color:var(--primary-text-color,#212121);background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#bbb);border-radius:8px;padding:10px}textarea{resize:vertical}ha-selector{display:block;width:100%;font-weight:400}.input-suffix{display:flex;align-items:center}.input-suffix input{border-radius:8px 0 0 8px}.input-suffix span{padding:10px;border:1px solid var(--divider-color,#bbb);border-left:0;border-radius:0 8px 8px 0;color:var(--secondary-text-color,#727272);white-space:nowrap}small{display:block;margin-top:8px;color:var(--secondary-text-color,#727272)}
      .switch{display:inline-block;position:relative;width:48px;height:26px;flex:none}.switch input{opacity:0;width:0;height:0}.switch span{position:absolute;inset:0;background:#aaa;border-radius:20px;cursor:pointer}.switch span:before{content:"";position:absolute;width:20px;height:20px;left:3px;top:3px;background:white;border-radius:50%;transition:.15s}.switch input:checked+span{background:var(--primary-color,#03a9f4)}.switch input:checked+span:before{transform:translateX(22px)}.checkbox{flex-direction:row;align-items:center}.checkbox input{width:auto}
      .actions{display:flex;justify-content:flex-end;gap:10px}.table-wrap{overflow:auto;margin-top:16px}table{border-collapse:collapse;width:100%;min-width:850px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--divider-color,#ddd);vertical-align:middle}th{font-size:12px;color:var(--secondary-text-color,#727272)}td code{display:block}.nowrap{white-space:nowrap}.icon-button{min-width:38px}.editor{scroll-margin-top:12px}.delay-list{display:grid;gap:10px;margin-top:16px}.delay-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,260px) auto;gap:10px;align-items:center}
      .empty,.loading{padding:40px;text-align:center;color:var(--secondary-text-color,#727272)}.empty.compact{padding:20px}.notice{padding:12px 16px;border-radius:8px;margin-bottom:16px}.notice.success{background:color-mix(in srgb,var(--success-color,#43a047) 15%,transparent);color:var(--success-color,#2e7d32)}.notice.error{background:color-mix(in srgb,var(--error-color,#db4437) 15%,transparent);color:var(--error-color,#db4437)}
      @media(max-width:700px){main{padding:12px}header{align-items:flex-start}.header-count{min-width:78px}.summary{grid-template-columns:1fr}.summary article{padding:14px}.fields{grid-template-columns:1fr}.alert-list{grid-template-columns:1fr}.panel{padding:15px}dl{grid-template-columns:1fr}.row.between{align-items:flex-start}.category-card .row.between>div{padding-right:8px}.actions button{width:100%}.delay-row{grid-template-columns:1fr}.delay-row button{width:100%}}
    `;
  }
}

if (!customElements.get("alert-manager-panel")) {
  customElements.define("alert-manager-panel", AlertManagerPanel);
}

export { AlertManagerPanel, durationText, lines, newRuleDefaults };
