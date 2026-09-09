import assert from "node:assert/strict";
import test from "node:test";
import { connectDashboard } from "../frontend-src/api/dashboard.js";
import { dashboardGroups, dashboardTarget } from "../frontend-src/dashboard/groups.js";
import { openAlertDeepLink } from "../frontend-src/components/alert-table.js";

const alert = (id, extra = {}) => ({ id, entity_id: `sensor.${id}`, type: "battery",
  name: id, active_since: "2026-09-01T12:00:00Z", acknowledged: false, ...extra });
const tick = () => new Promise((resolve) => setImmediate(resolve));
function fixture() {
  const connection = new EventTarget();
  connection.connected = true;
  const requests = [];
  const hass = { connection, user: { is_admin: true }, locale: { language: "fr" },
    states: {
      "sensor.alert_manager_main_active": { state: "1", attributes: { alerts_revision: 1 } },
      "switch.alert_manager_main_monitoring": { state: "on", attributes: {} },
    },
    callWS: (message) => new Promise((resolve, reject) => requests.push({ message, resolve, reject })),
  };
  const revise = (revision) => { hass.states["sensor.alert_manager_main_active"] = {
    state: "1", attributes: { alerts_revision: revision },
  }; };
  return { hass, connection, requests, revise };
}

test("filter before device grouping, deduplicate types and keep independent device-less alerts", () => {
  const alerts = [alert("a", { device_id: "d", labels: ["home"] }),
    alert("b", { device_id: "d", type: "rule", labels: ["home"] }),
    alert("c", { device_id: "d", type: "rule", labels: ["home"] }),
    alert("excluded", { device_id: "d", type: "unavailable" }),
    alert("ack", { acknowledged: true, labels: ["home"] }),
    alert("pending", { active_since: null, labels: ["home"] }),
    alert("no-device", { labels: ["home"] }), alert("entity-label")];
  const groups = dashboardGroups(alerts, "home", { entities: { "sensor.entity-label": { labels: ["home"] } } });
  assert.equal(groups.length, 3);
  const group = groups.find((value) => value.key === "device:d");
  assert.deepEqual(group.types, ["battery", "rule"]);
  assert.equal(group.alerts.length, 3);
  assert.match(dashboardTarget(group, "home"), /device=d&label=home/);
  assert.match(dashboardTarget(groups[0]), /alert=/);
  assert.deepEqual(dashboardGroups(alerts.reverse(), "home", { entities: { "sensor.entity-label": { labels: ["home"] } } }), groups);
});

test("groups sort by newest activation with stable identity ties and encode deep links", () => {
  const groups = dashboardGroups([alert("old"), alert("z", { device_id: "new", active_since: "2026-09-02T00:00:00Z" }), alert("a&b")]);
  assert.equal(groups[0].key, "device:new");
  assert.equal(groups[1].key, "alert:a&b");
  assert.match(dashboardTarget(groups[1]), /alert=a%26b/);
});

test("multiple cards share complete snapshots and ignore unrelated entity/history changes", async () => {
  const { hass, requests, revise } = fixture();
  const first = [], second = [];
  const a = connectDashboard(hass, (value) => first.push(value));
  const b = connectDashboard(hass, (value) => second.push(value));
  assert.equal(requests.length, 1);
  requests[0].resolve({ alerts: [alert("one")] });
  await tick();
  assert.equal(first.at(-1).snapshot, second.at(-1).snapshot);
  hass.states["sensor.unrelated"] = { state: "on" };
  hass.states["sensor.alert_manager_main_active"].attributes.history_revision = 4;
  a.update(hass); b.update(hass);
  assert.equal(requests.length, 1);
  revise(2); a.update(hass); b.update(hass);
  assert.equal(requests.length, 2);
  a.disconnect();
  requests[1].resolve({ alerts: [] });
  await tick();
  assert.equal(first.at(-1).snapshot.alerts.length, 1);
  assert.equal(second.at(-1).snapshot.alerts.length, 0);
  b.disconnect();
});

test("a change during fetching discards stale data and performs one trailing refresh", async () => {
  const { hass, requests, revise } = fixture();
  const values = [];
  const subscription = connectDashboard(hass, (value) => values.push(value));
  revise(2); subscription.update(hass);
  revise(3); subscription.update(hass);
  requests[0].resolve({ alerts: [alert("stale")] });
  await tick();
  assert.equal(values.some((value) => value.status === "ready"), false);
  assert.equal(requests.length, 2);
  requests[1].resolve({ alerts: [alert("fresh")] });
  await tick();
  assert.equal(values.at(-1).snapshot.alerts[0].id, "fresh");
  subscription.disconnect();
});

test("disconnect, reload, failure and disabled monitoring never imply no alerts", async () => {
  const { hass, connection, requests } = fixture();
  const values = [];
  const subscription = connectDashboard(hass, (value) => values.push(value));
  connection.connected = false;
  connection.dispatchEvent(new Event("disconnected"));
  requests[0].resolve({ alerts: [] });
  await tick();
  assert.equal(values.at(-1).status, "unavailable");
  connection.connected = true;
  connection.dispatchEvent(new Event("ready"));
  requests[1].reject({ code: "not_loaded" });
  await tick();
  assert.equal(values.at(-1).status, "unavailable");
  subscription.retry();
  requests[2].resolve({ alerts: [] });
  await tick();
  assert.equal(values.at(-1).status, "ready");
  hass.states["switch.alert_manager_main_monitoring"].state = "off";
  subscription.update(hass);
  assert.equal(values.at(-1).status, "paused");
  subscription.disconnect();
  connection.dispatchEvent(new Event("ready"));
  assert.equal(requests.length, 3);
});

test("non-admin cards do not fetch and closed subscriptions never receive stale responses", async () => {
  const { hass, requests } = fixture();
  hass.user.is_admin = false;
  const values = [];
  const subscription = connectDashboard(hass, (value) => values.push(value));
  assert.equal(values.at(-1).status, "admin");
  assert.equal(requests.length, 0);
  hass.user.is_admin = true;
  subscription.update(hass);
  const length = values.length;
  subscription.disconnect();
  requests[0].resolve({ alerts: [] });
  await tick();
  assert.equal(values.length, length);
});

// A minimal DOM double tests the card contract; actual HA components are not
// replaced in production. The browser fixture covers layout independently.
class TestElement extends EventTarget {
  isConnected = false;
  hidden = false;
  attachShadow() {
    this.shadowRoot = new EventTarget();
    this.shadowRoot.innerHTML = "";
    this.shadowRoot.querySelectorAll = () => [];
    this.shadowRoot.append = () => {};
    return this.shadowRoot;
  }
}
globalThis.HTMLElement = TestElement;
globalThis.window = { customCards: [] };
globalThis.customElements = { definitions: new Map(), whenDefined() { return Promise.resolve(); }, get(name) { return this.definitions.get(name); },
  define(name, value) { this.definitions.set(name, value); } };
globalThis.document = { createElement: () => new EventTarget() };
const { AlertManagerCard } = await import("../frontend-src/dashboard/card.js");
const { AlertManagerCardEditor, validateDashboardConfig } = await import("../frontend-src/dashboard/editor.js");

test("empty card hides and reappears via native visibility events, with no preview data in live mode", async () => {
  const { hass, requests, revise } = fixture();
  const card = new AlertManagerCard();
  const visible = [];
  card.addEventListener("card-visibility-changed", (event) => visible.push(event.detail.value));
  card.isConnected = true;
  card.hass = hass;
  requests[0].resolve({ alerts: [] });
  await tick();
  assert.equal(card.hidden, true);
  assert.equal(card.connectedWhileHidden, true);
  assert.equal(card.getCardSize(), 0);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /Capteur du salon/);
  card.preview = true;
  assert.equal(card.hidden, false);
  assert.match(card.shadowRoot.innerHTML, /Capteur du salon/);
  card.preview = false;
  revise(2); card.hass = hass;
  requests[1].resolve({ alerts: [alert("real")] });
  await tick();
  assert.equal(card.hidden, false);
  assert.deepEqual(visible, [false, true, false, true]);
  assert.match(card.shadowRoot.innerHTML, /alert=real/);
  card.disconnectedCallback();
});

test("card enforces group limit, escapes names, translates conditions and shows startup", () => {
  const card = new AlertManagerCard();
  card.hass = { locale: { language: "fr" } };
  card.setConfig({ max_tiles: 1 });
  card._value = { status: "ready", snapshot: { alerts: [
    alert("a", { name: '<img src=x onerror="bad">', device_id: "d", active_since: "2026-09-03T00:00:00Z", condition_key: "automatic.unavailable" }),
    alert("b", { device_id: "d", type: "rule" }), alert("c"),
  ] } };
  card._render();
  assert.equal((card.shadowRoot.innerHTML.match(/class="tile"/g) ?? []).length, 1);
  assert.match(card.shadowRoot.innerHTML, /Voir plus d’alertes/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<img/);
  assert.match(card.shadowRoot.innerHTML, /&lt;img/);
  assert.match(card.shadowRoot.innerHTML, /2 alertes/);
  card._value = { status: "ready", snapshot: { alerts: [], startup: { in_progress: true } } };
  card._render();
  assert.equal(card.hidden, false);
  assert.match(card.shadowRoot.innerHTML, /Home Assistant démarre/);
  card._value = { status: "unavailable" };
  card._render();
  assert.match(card.shadowRoot.innerHTML, /indisponible/);
});

test("editor validates YAML and emits native config-changed events", () => {
  for (const max_tiles of [0, 101, 1.5, "5"]) assert.throws(() => validateDashboardConfig({ max_tiles }, "fr"));
  assert.equal(validateDashboardConfig({}, "en").max_tiles, 5);
  const editor = new AlertManagerCardEditor();
  editor.setConfig({ type: "custom:alert-manager-card", max_tiles: 5 });
  let config;
  editor.addEventListener("config-changed", (event) => { config = event.detail.config; });
  editor._form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { max_tiles: 3, label: "home" } } }));
  assert.deepEqual(config, { type: "custom:alert-manager-card", max_tiles: 3, label: "home" });
});

test("device deep links replace stale filters, retain the label and allow another visit", () => {
  const panel = { _tableState: { overview: { search: "stale", filters: {} } },
    _resetTableFilters() { this._tableState.overview.filters = { status: ["active"] }; },
    _render() {}, _tableRows: () => [],
  };
  window.location = { search: "?device=one&label=home" };
  openAlertDeepLink.call(panel);
  assert.deepEqual(panel._tableState.overview.filters, { status: ["active"], device: ["one"], labels: ["home"] });
  assert.equal(panel._tableState.overview.search, "");
  window.location.search = "";
  openAlertDeepLink.call(panel);
  window.location.search = "?device=two";
  openAlertDeepLink.call(panel);
  assert.deepEqual(panel._tableState.overview.filters.device, ["two"]);
  window.location.search = "?dashboard=1&label=home";
  openAlertDeepLink.call(panel);
  assert.deepEqual(panel._tableState.overview.filters.device, []);
  assert.deepEqual(panel._tableState.overview.filters.labels, ["home"]);
});

test("appearance settings reject invalid YAML and preserve existing configurations", () => {
  for (const alignment of [null, "top", '<img src=x>']) {
    assert.throws(() => validateDashboardConfig({ alignment }, "fr"), /alignement/);
  }
  for (const icon_color of ["red; display:none", [], [0, 1], [0, 1, 256], [-1, 0, 0], [0.5, 0, 0], ["0", 0, 0]]) {
    assert.throws(() => validateDashboardConfig({ icon_color }, "en"), /color/);
  }
  assert.deepEqual(validateDashboardConfig({ max_tiles: 3, label: "home" }), { max_tiles: 3, label: "home" });
  const card = new AlertManagerCard();
  card.preview = true;
  for (const alignment of ["left", "center", "right"]) {
    card.setConfig({ alignment, icon_color: [255, 152, 0] });
    assert.match(card.shadowRoot.innerHTML, new RegExp(`data-alignment="${alignment}" style=`));
    assert.match(card.shadowRoot.innerHTML, /--alert-icon-color: #ff9800/);
  }
  card.setConfig({});
  assert.match(card.shadowRoot.innerHTML, /data-alignment="left" style="--alert-icon-color: var\(--state-icon-color\)/);
});

test("editor translates appearance controls and allows clearing the custom color", () => {
  const editor = new AlertManagerCardEditor();
  editor.hass = { locale: { language: "fr" } };
  editor.setConfig({ max_tiles: 5, label: "home", alignment: "center", icon_color: [0, 128, 255] });
  assert.deepEqual(editor._form.schema.find((field) => field.name === "alignment").selector.select.options,
    [{ value: "left", label: "Gauche" }, { value: "center", label: "Centre" }, { value: "right", label: "Droite" }]);
  let config;
  editor.addEventListener("config-changed", (event) => { config = event.detail.config; });
  editor._form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { icon_color: undefined, alignment: "right" } } }));
  assert.deepEqual(config, { max_tiles: 5, label: "home", alignment: "right" });
});

test("native palette colors resolve through the theme and previous RGB colors remain editable", () => {
  const card = new AlertManagerCard();
  for (const color of ["primary", "accent", "red", "deep-purple", "light-grey"]) {
    card.setConfig({ icon_color: color });
    assert.match(card.shadowRoot.innerHTML, new RegExp(`--alert-icon-color: var\\(--${color}-color\\)`));
  }
  card.setConfig({ icon_color: "state" });
  assert.match(card.shadowRoot.innerHTML, /--alert-icon-color: var\(--state-icon-color\)/);
  const editor = new AlertManagerCardEditor();
  editor.setConfig({ icon_color: [0, 128, 255] });
  assert.equal(editor._form.data.icon_color, "#0080ff");
  assert.deepEqual(editor._form.schema.find((field) => field.name === "icon_color").selector,
    { ui_color: { include_state: true, default_color: "state" } });
  for (const icon_color of ['red" onmouseover="bad', "</style><script>bad</script>", "var(--red);display:none"]) {
    assert.throws(() => card.setConfig({ icon_color }));
  }
});

test("overflow stays inside the tile row and counts hidden alerts after filtering and grouping", () => {
  const card = new AlertManagerCard();
  card.hass = { locale: { language: "fr" } };
  card.setConfig({ max_tiles: 1, label: "a&b", alignment: "center" });
  card._value = { status: "ready", snapshot: { alerts: [
    alert("first", { labels: ["a&b"], active_since: "2026-09-03T00:00:00Z" }),
    alert("second", { labels: ["a&b"], device_id: "d" }),
    alert("third", { labels: ["a&b"], device_id: "d" }),
    alert("excluded"),
  ] } };
  card._render();
  assert.match(card.shadowRoot.innerHTML, /<ha-card class="overflow">/);
  assert.match(card.shadowRoot.innerHTML, /aria-label="Voir plus d’alertes : 2 supplémentaires"/);
  assert.match(card.shadowRoot.innerHTML, /dashboard=1&amp;label=a%26b/);
  assert.match(card.shadowRoot.innerHTML, /\+2<\/span>/);
  assert.match(card.shadowRoot.innerHTML, /<\/a><\/ha-card><\/div><\/div>$/);
  card.setConfig({ max_tiles: 2, label: "a&b" });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="overflow"/);
});

test("compact coherence text keeps full details and custom rule messages intact", () => {
  const card = new AlertManagerCard();
  card.hass = { locale: { language: "fr" } };
  const coherence = alert("coherence", { type: "coherence", name: "Cohérence de la configuration",
    condition: "3 problèmes de cohérence de configuration", condition_params: { count: 3 } });
  const tile = card._tile(dashboardGroups([coherence])[0]);
  assert.match(tile, /title="Cohérence de la configuration">Cohérence<\/div>/);
  assert.match(tile, /title="3 problèmes de cohérence de configuration">3 problèmes détectés<\/div>/);
  coherence.condition_params.count = 1;
  assert.match(card._tile(dashboardGroups([coherence])[0]), />1 problème détecté<\/div>/);
  const rule = alert("custom", { type: "rule", message: 'Mon message <personnalisé>', condition: "Status on" });
  const customTile = card._tile(dashboardGroups([rule])[0]);
  assert.match(customTile, /title="Mon message &lt;personnalisé&gt;">Mon message &lt;personnalisé&gt;<\/div>/);
  assert.doesNotMatch(customTile, /Status on/);
});
