import assert from "node:assert/strict";
import test from "node:test";
import { connectDashboard } from "../frontend-src/api/dashboard.js";
import { dashboardGroups, dashboardTarget } from "../frontend-src/dashboard/groups.js";
import { openAlertDeepLink, filteredTableRows, filterValues, historyFacetOptions, renderFilterPane, renderFacetFilter } from "../frontend-src/components/alert-table.js";

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

test("non-admin cards fetch alerts and closed subscriptions never receive stale responses", async () => {
  const { hass, requests } = fixture();
  hass.user.is_admin = false;
  const values = [];
  const subscription = connectDashboard(hass, (value) => values.push(value));
  assert.equal(values.at(-1).status, "loading");
  assert.equal(requests.length, 1);
  const length = values.length;
  subscription.disconnect();
  requests[0].resolve({ alerts: [] });
  await tick();
  assert.equal(values.length, length);
});

test("renamed integration entities are discovered and continue driving card refreshes", async () => {
  const { hass, requests } = fixture();
  const values = [];
  const active = "sensor.alert_manager_main_active", monitoring = "switch.alert_manager_main_monitoring";
  hass.states["sensor.renamed_count"] = hass.states[active];
  hass.states["switch.renamed_monitoring"] = hass.states[monitoring];
  delete hass.states[active]; delete hass.states[monitoring];
  const mapping = { [active]: "sensor.renamed_count", [monitoring]: "switch.renamed_monitoring" };
  const subscription = connectDashboard(hass, (value) => values.push(value));
  assert.equal(requests.length, 1);
  requests[0].resolve({ alerts: [alert("one")], entity_ids: mapping });
  await tick();
  assert.equal(values.at(-1).status, "ready");
  subscription.update(hass);
  assert.equal(requests.length, 1);
  hass.states["sensor.renamed_count"] = { state: "2", attributes: { alerts_revision: 2 } };
  subscription.update(hass);
  assert.equal(requests.length, 2);
  requests[1].resolve({ alerts: [alert("two")], entity_ids: mapping });
  await tick();
  assert.equal(values.at(-1).snapshot.alerts[0].id, "two");
  hass.states["sensor.renamed_again"] = hass.states["sensor.renamed_count"];
  delete hass.states["sensor.renamed_count"];
  subscription.update(hass);
  assert.equal(requests.length, 3);
  requests[2].resolve({ alerts: [], entity_ids: { ...mapping, [active]: "sensor.renamed_again" } });
  await tick();
  assert.equal(values.at(-1).status, "ready");
  hass.states["switch.renamed_monitoring"] = { state: "off", attributes: {} };
  subscription.update(hass);
  assert.equal(values.at(-1).status, "paused");
  assert.equal(requests.length, 3);
  subscription.disconnect();
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
  assert.match(card.shadowRoot.innerHTML, /Voir plus d’appareils/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<img/);
  assert.match(card.shadowRoot.innerHTML, /&lt;img/);
  assert.match(card.shadowRoot.innerHTML, /2 alertes/);
  assert.match(card.shadowRoot.innerHTML, /<div class="types">(?:<ha-icon[^>]*><\/ha-icon>)+<\/div>\s*<div class="content">/);
  card._value = { status: "ready", snapshot: { alerts: [], startup: { in_progress: true } } };
  card._render();
  assert.equal(card.hidden, true);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /mdi:timer-sand/);
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
  assert.deepEqual(config, { type: "custom:alert-manager-card", max_tiles: 3, labels: ["home"] });
});

test("device deep links replace stale filters, retain the label and allow another visit", () => {
  const panel = { _tableState: { overview: { search: "stale", filters: {} } },
    _resetTableFilters() { this._tableState.overview.filters = { status: ["active"] }; },
    _render() {}, _tableRows: () => [],
  };
  window.location = { search: "?device=one&label=home" };
  openAlertDeepLink.call(panel);
  assert.deepEqual(panel._tableState.overview.filters, { status: ["active"], device: ["id:one"], labels: ["home"], exclude_labels: [] });
  assert.equal(panel._tableState.overview.search, "");
  window.location.search = "";
  openAlertDeepLink.call(panel);
  window.location.search = "?device=two";
  openAlertDeepLink.call(panel);
  assert.deepEqual(panel._tableState.overview.filters.device, ["id:two"]);
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
  assert.deepEqual(validateDashboardConfig({ max_tiles: 3, label: "home" }), { max_tiles: 3, labels: ["home"] });
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
  assert.deepEqual(config, { max_tiles: 5, labels: ["home"], alignment: "right" });
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

test("style selector defaults to Classic and preserves color and filters when switching", () => {
  for (const style of [null, "", "pastel", 1, '<img src=x>']) {
    assert.throws(() => validateDashboardConfig({ style }, "fr"), /style/);
  }
  assert.deepEqual(validateDashboardConfig({}), { max_tiles: 5 });
  const editor = new AlertManagerCardEditor();
  editor.hass = { locale: { language: "fr" } };
  const initial = { max_tiles: 3, icon_color: [0, 128, 255], labels: ["home"], exclude_labels: ["maintenance"] };
  editor.setConfig(initial);
  assert.equal(editor._form.data.style, "classic");
  assert.deepEqual(editor._form.schema.find((field) => field.name === "style").selector.select.options,
    [{ value: "classic", label: "Classique" }, { value: "bubble", label: "Bubble" }]);
  let config;
  editor.addEventListener("config-changed", (event) => { config = event.detail.config; });
  for (const style of ["bubble", "classic"]) {
    editor._form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { style } } }));
    assert.deepEqual(config, { ...initial, icon_color: "#0080ff", style });
    editor.setConfig(config);
    assert.equal(editor._form.data.style, style);
    assert.equal(Boolean(editor._form.computeHelper({ name: "icon_color" })), style === "bubble");
  }
  editor.hass = { locale: { language: "en" } };
  assert.equal(editor._form.schema.find((field) => field.name === "style").selector.select.options[0].label, "Classic");
  editor.setConfig({ ...config, style: "bubble" });
  editor._form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { icon_color: undefined } } }));
  assert.equal(config.style, "bubble");
  assert.equal(Object.hasOwn(config, "icon_color"), false);
});

test("Bubble keeps grouped navigation, age, limits and startup while Classic keeps type icons", () => {
  const card = new AlertManagerCard();
  card.hass = { locale: { language: "fr" } };
  const config = { max_tiles: 1, labels: ["home"], exclude_labels: ["maintenance"], show_age: true, icon_color: "red" };
  const items = [
    alert("a", { device_id: "d", type: "unavailable", labels: ["home"], active_since: "2026-09-03T00:00:00Z" }),
    alert("b", { device_id: "d", labels: ["home"] }),
    alert("excluded", { device_id: "d", labels: ["home", "maintenance"] }),
    alert("ack", { device_id: "d", labels: ["home"], acknowledged: true }),
    alert("other", { labels: ["home"] }),
  ];
  card._value = { status: "ready", snapshot: { alerts: items } };
  card.setConfig(config);
  const markup = () => card.shadowRoot.innerHTML.split("</style>")[1];
  const links = () => [...markup().matchAll(/href="([^"]+)"/g)].map((match) => match[1]);
  const classicLinks = links();
  assert.match(markup(), /data-style="classic"/);
  assert.match(markup(), /class="types"/);
  assert.doesNotMatch(markup(), /class="bubble-icon"/);
  card.setConfig({ ...config, style: "bubble" });
  assert.deepEqual(links(), classicLinks);
  assert.equal(card._tileCount, 1);
  assert.match(markup(), /--alert-icon-color: var\(--red-color\)/);
  assert.match(markup(), /class="bubble-count" aria-hidden="true">2<\/span>/);
  assert.match(markup(), /data-age="2026-09-01T12:00:00.000Z"/);
  assert.match(markup(), /\+1<\/span>/);
  assert.doesNotMatch(markup(), /class="types"|mdi:chevron-right/);
  for (const type of ["battery", "unavailable"]) assert.ok(markup().includes(card._typeName(type)));
  card._value.snapshot.startup = { in_progress: true };
  card._render();
  assert.match(markup(), /mdi:timer-sand/);
  assert.match(markup(), /\+1<\/span>/);
  card.setConfig({ ...config, style: "classic" });
  assert.match(markup(), /class="types"/);
  assert.doesNotMatch(markup(), /class="bubble-count"/);
  assert.deepEqual(links(), classicLinks);
  card.setConfig({ ...config, style: "bubble", group_by_device: false });
  assert.doesNotMatch(markup(), /class="bubble-count"/);
  assert.match(markup(), /overview\?alert=a/);
  card._value = { status: "ready", snapshot: { alerts: [] } };
  card._render();
  assert.equal(card.hidden, true);
});

test("overflow stays inside the tile row and counts hidden tiles after filtering and grouping", () => {
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
  assert.match(card.shadowRoot.innerHTML, /aria-label="Voir plus d’appareils : 1 supplémentaires"/);
  assert.match(card.shadowRoot.innerHTML, /dashboard=1&amp;label=a%26b/);
  assert.match(card.shadowRoot.innerHTML, /\+1<\/span>/);
  assert.match(card.shadowRoot.innerHTML, /<\/a><\/ha-card><\/div><\/div><\/div>$/);
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

test("startup retains restored alerts and combines the hourglass with overflow", () => {
  const card = new AlertManagerCard();
  card.hass = { locale: { language: "fr" } };
  card.setConfig({ max_tiles: 1, alignment: "right", label: "home" });
  const snapshot = { alerts: [alert("restored-a", { labels: ["home"] }),
    alert("restored-b", { labels: ["home"] })], startup: { in_progress: true } };
  card._value = { status: "ready", snapshot };
  for (const preview of [false, true]) {
    card.preview = preview;
    assert.equal(card.hidden, false);
    assert.match(card.shadowRoot.innerHTML, /class="tile-tail"><ha-card>/);
    assert.match(card.shadowRoot.innerHTML, /data-alignment="right"/);
    assert.match(card.shadowRoot.innerHTML, /alert=restored-a/);
    assert.match(card.shadowRoot.innerHTML, /mdi:timer-sand/);
    assert.match(card.shadowRoot.innerHTML, /Démarrage en cours : les alertes connues/);
    assert.match(card.shadowRoot.innerHTML, /\+1<\/span>/);
    assert.equal((card.shadowRoot.innerHTML.match(/class="overflow"/g) ?? []).length, 1);
    assert.match(card.shadowRoot.innerHTML, /href="\/alert-manager\/overview\?dashboard=1&amp;label=home"/);
    assert.doesNotMatch(card.shadowRoot.innerHTML, /Capteur du salon/);
  }
  card.preview = false;
  snapshot.startup.in_progress = false;
  card._render();
  assert.match(card.shadowRoot.innerHTML, /restored-a/);
  assert.match(card.shadowRoot.innerHTML, /<ha-ripple><\/ha-ripple>/);
  assert.match(card.shadowRoot.innerHTML, /class="overflow"/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /mdi:timer-sand/);
  snapshot.alerts = [];
  card._render();
  assert.equal(card.hidden, true);
});

test("startup hourglass without overflow disappears when reevaluation completes", () => {
  const card = new AlertManagerCard();
  const snapshot = { alerts: [alert("known")], startup: { in_progress: true } };
  card._value = { status: "ready", snapshot };
  card._render();
  assert.match(card.shadowRoot.innerHTML, /alert=known/);
  assert.match(card.shadowRoot.innerHTML, /mdi:timer-sand/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /\+0<\/span>/);
  assert.match(card.shadowRoot.innerHTML, /Starting up: known alerts are being reevaluated/);
  snapshot.startup.in_progress = false;
  card._render();
  assert.match(card.shadowRoot.innerHTML, /alert=known/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="overflow"|class="tile-tail"|mdi:timer-sand/);
});

test("startup without matching active alerts uses no space, including in preview", () => {
  const card = new AlertManagerCard();
  card.setConfig({ label: "home" });
  for (const alerts of [[], [alert("excluded"), alert("pending", { active_since: null, labels: ["home"] }),
    alert("ack", { acknowledged: true, labels: ["home"] })]]) {
    card._value = { status: "ready", snapshot: { alerts, startup: { in_progress: true } } };
    for (const preview of [false, true]) {
      card.preview = preview;
      assert.equal(card.hidden, true);
      assert.equal(card.getCardSize(), 0);
      assert.doesNotMatch(card.shadowRoot.innerHTML, /<ha-card>|mdi:timer-sand|class="overflow"/);
    }
  }
});

for (const alerts of [[], [alert("retained")]]) {
  test(`reattaching retains ${alerts.length ? "tiles" : "an empty card"} until refresh completes`, async () => {
    const { hass, requests } = fixture();
    const card = new AlertManagerCard();
    card.isConnected = true;
    card.hass = hass;
    requests[0].resolve({ alerts });
    await tick();
    const markup = card.shadowRoot.innerHTML;
    const hidden = card.hidden;
    card.isConnected = false;
    card.disconnectedCallback();
    card.isConnected = true;
    card.connectedCallback();
    assert.equal(requests.length, 2);
    assert.equal(card.shadowRoot.innerHTML, markup);
    assert.equal(card.hidden, hidden);
    requests[1].resolve({ alerts: [alert("updated")] });
    await tick();
    assert.match(card.shadowRoot.innerHTML, /alert=updated/);
    assert.doesNotMatch(card.shadowRoot.innerHTML, /alert=retained/);
    card.disconnectedCallback();
  });
}

test("WebSocket reconnect keeps tiles, discards in-flight data and exposes refresh errors", async () => {
  const { hass, connection, requests, revise } = fixture();
  const card = new AlertManagerCard();
  card.isConnected = true;
  card.hass = hass;
  requests[0].resolve({ alerts: [alert("retained")] });
  await tick();
  const markup = card.shadowRoot.innerHTML;
  revise(2); card.hass = hass;
  connection.connected = false;
  connection.dispatchEvent(new Event("disconnected"));
  card.hass = hass;
  requests[1].resolve({ alerts: [] });
  await tick();
  assert.equal(card.shadowRoot.innerHTML, markup);
  connection.connected = true;
  connection.dispatchEvent(new Event("ready"));
  assert.equal(card.shadowRoot.innerHTML, markup);
  requests[2].reject({ code: "not_loaded" });
  await tick();
  assert.match(card.shadowRoot.innerHTML, /indisponible/);
  card._subscription.retry();
  requests[3].resolve({ alerts: [] });
  await tick();
  assert.equal(card.hidden, true);
  card.disconnectedCallback();
});

test("a different HA connection does not reuse the previous snapshot", async () => {
  const first = fixture(), second = fixture();
  const card = new AlertManagerCard();
  card.isConnected = true;
  card.hass = first.hass;
  first.requests[0].resolve({ alerts: [alert("private")] });
  await tick();
  card.hass = second.hass;
  assert.doesNotMatch(card.shadowRoot.innerHTML, /alert=private/);
  second.requests[0].resolve({ alerts: [] });
  await tick();
  assert.equal(card.hidden, true);
  card.disconnectedCallback();
});


test("group link selects device IDs with matching facet and preserves label filtering", () => {
  const items = [alert("a", { device_id: "one", device_name: "Cloudflared" }),
    alert("b", { device_id: "one", device_name: "Cloudflared" })];
  window.location = { search: dashboardTarget(dashboardGroups(items)[0], "home").split("?")[1] };
  const panel = { _tableState: { overview: { search: "stale", filters: {} } },
    _resetTableFilters() { this._tableState.overview.filters = {}; },
    _render() {}, _filterValues: filterValues, _dateMatches: () => true,
    _compareTableRows: () => 0,
  };
  openAlertDeepLink.call(panel);
  const rows = [
    ...items.map((source) => ({ id: source.id, source, status: "active", device: source.device_name, labelIds: ["home"] })),
    { id: "same-name", source: { device_id: "two" }, device: "Cloudflared", labelIds: ["home"] },
    { id: "other-label", source: { device_id: "one" }, device: "Cloudflared", labelIds: [] },
  ];
  assert.deepEqual(filteredTableRows.call(panel, "overview", rows).map((row) => row.id), ["a", "b"]);
  const options = historyFacetOptions(rows, "device", (key) => key);
  assert.ok(options.some((option) => option.value === panel._tableState.overview.filters.device[0] && option.label === "Cloudflared"));
  Object.assign(panel, { _t: (key) => key, _facetOptions: () => [],
    _renderDateFilter: () => "", _renderFacetFilter: renderFacetFilter });
  rows.forEach((row) => { row.labels = []; });
  assert.match(renderFilterPane.call(panel, "overview", rows), /<ha-checkbox[^>]*data-filter-value="id:one" checked/);
  panel._tableState.overview.filters = { device: ["Cloudflared"] };
  assert.equal(filteredTableRows.call(panel, "overview", rows).length, 4);
  assert.match(renderFilterPane.call(panel, "overview", rows), /<ha-checkbox[^>]*data-filter-value="Cloudflared" checked/);
});

test("card options normalize legacy labels and reject malformed YAML", () => {
  assert.deepEqual(validateDashboardConfig({ label: "home" }).labels, ["home"]);
  assert.deepEqual(validateDashboardConfig({ label: "home", labels: [] }).labels, []);
  assert.deepEqual(validateDashboardConfig({ labels: ["home", "home"] }).labels, ["home"]);
  for (const max_tiles_mobile of [0, 101, 2.5, "2", false]) {
    assert.throws(() => validateDashboardConfig({ max_tiles_mobile }));
  }
  for (const max_tiles_mobile of [undefined, null, ""]) {
    assert.equal(validateDashboardConfig({ max_tiles_mobile }).max_tiles_mobile, undefined);
  }
  for (const config of [{ labels: "home" }, { labels: [2] }, { exclude_labels: [""] },
    { exclude_labels: null }, { show_age: "true" }, { group_by_device: 0 }, { sort: "priority" }]) {
    assert.throws(() => validateDashboardConfig(config));
  }
  const editor = new AlertManagerCardEditor();
  editor.setConfig({ type: "custom:alert-manager-card", label: "home", max_tiles_mobile: 2 });
  assert.deepEqual(editor._form.data.labels, ["home"]);
  for (const name of ["labels", "exclude_labels"]) {
    assert.deepEqual(editor._form.schema.find((field) => field.name === name).selector, { label: { multiple: true } });
  }
  let emitted;
  editor.addEventListener("config-changed", (event) => { emitted = event.detail.config; });
  const edited = { ...editor._form.data, labels: [], exclude_labels: ["maintenance"],
    max_tiles_mobile: null, sort: "oldest", show_age: true, group_by_device: false };
  editor._form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: edited } }));
  assert.equal(emitted.label, undefined);
  assert.equal(emitted.max_tiles_mobile, undefined);
  assert.deepEqual(emitted.labels, []);
  editor.setConfig(JSON.parse(JSON.stringify(emitted)));
  for (const key of ["labels", "exclude_labels", "sort", "show_age", "group_by_device"]) {
    assert.deepEqual(editor._form.data[key], edited[key]);
  }
});

test("multi-label inclusion is OR and exclusions precede grouping and age", () => {
  const items = [
    alert("a", { device_id: "d", labels: ["home"], active_since: "2026-09-02T00:00:00Z" }),
    alert("b", { device_id: "d", labels: ["outside"], active_since: "2026-09-03T00:00:00Z" }),
    alert("excluded-old", { device_id: "d", labels: ["home", "maintenance"], active_since: "2020-01-01T00:00:00Z" }),
    alert("excluded-group", { device_id: "gone", labels: ["outside", "maintenance"] }),
    alert("ack", { labels: ["home"], acknowledged: true }),
    alert("pending", { labels: ["home"], active_since: null }),
    alert("resolved", { labels: ["home"], resolved_at: "2026-09-03T00:00:00Z" }),
    alert("entity-label"), alert("other"),
  ];
  const config = { labels: ["home", "outside"], exclude_labels: ["maintenance"] };
  const hass = { entities: { "sensor.entity-label": { labels: ["outside"] } } };
  const groups = dashboardGroups(items, config, hass);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].alerts.map((item) => item.id), ["a", "b"]);
  assert.equal(groups[0].oldest, Date.parse("2026-09-02T00:00:00Z"));
  assert.deepEqual(dashboardGroups(items, { ...config, group_by_device: false }, hass)
    .map((group) => group.alerts[0].id), ["b", "a", "entity-label"]);
  assert.equal(dashboardGroups(items, { exclude_labels: ["home", "outside"] }, hass).length, 1);
});

test("all sort orders use retained activations or displayed names with stable ties", () => {
  const items = [alert("a", { device_id: "d", device_name: "Zulu", active_since: "2026-09-01T00:00:00Z" }),
    alert("b", { device_id: "d", device_name: "Zulu", active_since: "2026-09-05T00:00:00Z" }),
    alert("c", { name: "Alpha", active_since: "2026-09-03T00:00:00Z" }),
    alert("z", { name: "Alpha", active_since: "2026-09-03T00:00:00Z" }),
    alert("invalid", { name: "Other", active_since: "invalid" })];
  const keys = (config) => dashboardGroups(items, config).map((group) => group.key);
  assert.deepEqual(keys({ sort: "newest" }), ["device:d", "alert:c", "alert:z", "alert:invalid"]);
  assert.deepEqual(keys({ sort: "oldest" }), ["device:d", "alert:c", "alert:z", "alert:invalid"]);
  assert.deepEqual(keys({ sort: "alphabetical" }), ["alert:c", "alert:z", "alert:invalid", "device:d"]);
  assert.deepEqual(keys({ sort: "oldest", group_by_device: false }), ["alert:a", "alert:c", "alert:z", "alert:b", "alert:invalid"]);
  assert.deepEqual(keys({ sort: "newest", group_by_device: false }), ["alert:b", "alert:c", "alert:z", "alert:a", "alert:invalid"]);
  for (const sort of ["newest", "oldest", "alphabetical"]) {
    const before = dashboardGroups(items, { sort });
    items.reverse();
    assert.deepEqual(dashboardGroups(items, { sort }), before);
  }
  const before = keys({});
  items[0].message = "updated";
  items[0].updated_at = "2030-01-01T00:00:00Z";
  assert.deepEqual(keys({}), before);
});

test("mobile limits follow the layout breakpoint and release listeners on disconnect", () => {
  const queries = [];
  globalThis.matchMedia = (query) => {
    assert.equal(query, "(max-width: 600px)");
    const media = new EventTarget();
    media.matches = false;
    queries.push(media);
    return media;
  };
  try {
    const card = new AlertManagerCard();
    card.connectedCallback();
    card.setConfig({ max_tiles: 5, max_tiles_mobile: 2 });
    card._value = { status: "ready", snapshot: { alerts: ["a", "b", "c", "d", "e", "f"].map((id) => alert(id)) } };
    card._render();
    assert.equal(card._tileCount, 5);
    const media = queries[0];
    media.matches = true;
    media.dispatchEvent(new Event("change"));
    assert.equal(card._tileCount, 2);
    assert.match(card.shadowRoot.innerHTML, /\+4<\/span>/);
    assert.match(card.shadowRoot.innerHTML, /class="tile-tail"><ha-card>/);
    const other = new AlertManagerCard();
    other.connectedCallback();
    other.setConfig({ max_tiles: 3 });
    other._value = card._value;
    queries[1].matches = true;
    other._render();
    assert.equal(other._tileCount, 3);
    card.setConfig({ max_tiles: 5 });
    assert.equal(card._tileCount, 5);
    card.setConfig({ max_tiles: 5, max_tiles_mobile: 2 });
    media.matches = false;
    media.dispatchEvent(new Event("change"));
    assert.equal(card._tileCount, 5);
    card.disconnectedCallback();
    media.matches = true;
    media.dispatchEvent(new Event("change"));
    assert.equal(card._tileCount, 5);
    card.connectedCallback();
    assert.equal(queries.length, 3);
    card.disconnectedCallback();
    other.disconnectedCallback();
  } finally { delete globalThis.matchMedia; }
});

test("age uses native relative time with the oldest eligible activation, independently of sort", () => {
  const card = new AlertManagerCard();
  const items = [alert("a", { device_id: "d", active_since: "2026-09-03T00:00:00Z" }),
    alert("b", { device_id: "d", active_since: "2026-09-01T00:00:00Z" }),
    alert("bad", { active_since: "not-a-date" })];
  card._value = { status: "ready", snapshot: { alerts: items } };
  card.setConfig({});
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<ha-relative-time/);
  const native = { dataset: { age: "2026-09-01T00:00:00.000Z" } };
  card.shadowRoot.querySelectorAll = (query) => query === "ha-relative-time[data-age]" ? [native] : [];
  for (const sort of ["newest", "oldest", "alphabetical"]) {
    card.setConfig({ sort, show_age: true });
    assert.equal((card.shadowRoot.innerHTML.match(/<ha-relative-time /g) ?? []).length, 1);
    assert.match(card.shadowRoot.innerHTML, /data-age="2026-09-01T00:00:00.000Z"/);
    assert.match(card.shadowRoot.innerHTML, /message-text">2 alerts/);
    assert.equal(native.datetime, native.dataset.age);
  }
  card.setConfig({ group_by_device: false, show_age: true, max_tiles: 1 });
  assert.match(card.shadowRoot.innerHTML, /href="\/alert-manager\/overview\?alert=a"/);
  assert.match(card.shadowRoot.innerHTML, /data-age="2026-09-03T00:00:00.000Z"/);
  assert.match(card.shadowRoot.innerHTML, /View more alerts: 2/);
});

test("group and overflow links preserve OR inclusion and priority exclusions in Overview", () => {
  const items = [alert("a", { device_id: "d", labels: ["home"] }),
    alert("b", { device_id: "d", labels: ["outside"] })];
  const config = { labels: ["home", "outside"], exclude_labels: ["maintenance&test"] };
  const group = dashboardGroups(items, config)[0];
  const panel = { _tableState: { overview: { search: "stale", filters: {} } },
    _resetTableFilters() { this._tableState.overview.filters = {}; }, _render() {},
    _filterValues: filterValues, _dateMatches: () => true, _compareTableRows: () => 0 };
  const rows = [...items, alert("excluded", { device_id: "d", labels: ["home", "maintenance&test"] }),
    alert("other", { device_id: "another", labels: ["home"] }), alert("unrelated", { device_id: "d" }),
    alert("ack", { device_id: "d", labels: ["home"], acknowledged: true })]
    .map((source) => ({ id: source.id, source, status: source.acknowledged ? "acknowledged" : "active",
      labelIds: source.labels ?? [] }));
  window.location = { search: dashboardTarget(group, config).split("?")[1] };
  openAlertDeepLink.call(panel);
  assert.deepEqual(filteredTableRows.call(panel, "overview", rows).map((row) => row.id), ["a", "b"]);
  window.location.search = dashboardTarget(null, config).split("?")[1];
  openAlertDeepLink.call(panel);
  assert.deepEqual(filteredTableRows.call(panel, "overview", rows).map((row) => row.id), ["a", "b", "other"]);
  assert.deepEqual(panel._tableState.overview.filters.exclude_labels, ["maintenance&test"]);
});
