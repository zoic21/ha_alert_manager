import assert from "node:assert/strict";
import test from "node:test";

// Native EventTargets exercise the panel's registered input/change listeners.
class Root extends EventTarget {
  controls = new Map();
  querySelector(selector) { return this.controls.get(selector) ?? null; }
  querySelectorAll(selector) { return this.controls.get(selector) ?? []; }
}
globalThis.HTMLElement = class {
  isConnected = true;
  attachShadow() { return this.shadowRoot = new Root(); }
};
globalThis.customElements = { define() {}, get() { return true; } };
globalThis.window = { localStorage: { getItem() { return null; } }, confirm: () => false };
globalThis.document = { createElement: () => ({ style: {}, setAttribute() {}, append() {} }) };
const { AlertManagerPanel } = await import("../frontend-src/alert-manager-panel.js");
const { updateDrawerLayout } = await import("../frontend-src/components/configuration-drawer.js");
const { handleNotificationProfileAction } = await import("../frontend-src/components/notification-profiles.js");
const { handleRulesAction } = await import("../frontend-src/views/rules.js");

function panel() {
  const p = new AlertManagerPanel();
  p._config = { automatic: { battery: { enabled: true, delay: 60, threshold: 15, overrides: { dev: 20 } } }, entity_delays: { "sensor.a": 60 } };
  p._packs = [{ id: "battery", available: true, config_fields: [
    { id: "threshold", type: "number", default: 15 },
    { id: "overrides", type: "device_number_map" },
  ] }];
  p._clearRuleEditorError = p._clearRuleTestResult = p._updateConfigurationSaveButton = () => {};
  p._refreshTabData = p._hydrateSelectors = p._refreshUiState = () => {};
  p._refreshSettingsConfigurationDrawer = () => {};
  p._render = () => { p.shadowRoot.controls.clear(); };
  p._activeTab = "settings";
  return p;
}
function control(p, selector, props, form = "#automatic-form") {
  const c = Object.assign(new EventTarget(), { id: selector.slice(1), dataset: {}, closest: (s) => s === form ? {} : null }, props);
  for (const type of ["input", "change"]) c.addEventListener(type, (event) => {
    const delegated = new Event(type);
    Object.defineProperty(delegated, "target", { value: event.target });
    p.shadowRoot.dispatchEvent(delegated);
  });
  p.shadowRoot.controls.set(selector, c);
  return c;
}

for (const narrow of [false, true]) {
  test(`automatic inputs survive navigation and resize, then save the draft (narrow=${narrow})`, async () => {
    const p = panel();
    p._ensureAutomaticDraft();
    control(p, "#auto-battery-enabled", { checked: false }).dispatchEvent(new Event("change"));
    control(p, "#auto-battery-delay", { value: "" }).dispatchEvent(new Event("input"));
    control(p, "#auto-battery-threshold", { value: "27" }).dispatchEvent(new Event("input"));
    const map = control(p, "#override", { value: "31", dataset: { packMap: "battery", packField: "overrides", packIndex: "0" } });
    p.shadowRoot.controls.set("[data-pack-map]", [map]);
    map.dispatchEvent(new Event("input"));
    p.route = { path: "/alert-manager/rules" };
    p.route = { path: "/alert-manager/settings" };
    p._configurationDrawer = { kind: "automatic", id: "battery", fieldId: "overrides" };
    p._narrow = narrow;
    p._loadNativeBottomSheet = async () => true;
    updateDrawerLayout.call(p, !narrow);
    await Promise.resolve();
    const markup = p._renderAutomatic();
    assert.doesNotMatch(markup, /auto-battery-enabled[^>]*checked/);
    assert.match(markup, /auto-battery-threshold[^>]*value="27"/);
    assert.match(markup, /value="31" data-pack-map/);
    let sent;
    p._call = async (message) => { sent = message.config.automatic; return null; };
    await p._saveAutomatic();
    assert.deepEqual(sent.battery, { enabled: false, delay: null, threshold: 27, overrides: { dev: 31 } });
  });
}

test("rule input/change events retain text, numbers and switches across navigation", async () => {
  const p = panel();
  p._editingRule = { name: "Old", source: "state", operator: "above", value: "10", duration: 60 };
  const form = new Root();
  p.shadowRoot.controls.set("#rule-form", form);
  for (const [name, value] of [["name", "New"], ["duration", "123"], ["value", "42"]]) {
    const c = control(p, `#rule-${name}`, { value }, "#rule-form");
    form.controls.set(`[data-field="${name}"]`, c);
    c.dispatchEvent(new Event("input"));
  }
  const toggle = control(p, "#rule-update-message-when-active", { checked: true }, "#rule-form");
  form.controls.set("#rule-update-message-when-active", toggle);
  toggle.dispatchEvent(new Event("change"));
  p.route = { path: "/alert-manager/overview" };
  p.route = { path: "/alert-manager/rules" };
  assert.equal(p._editingRule.name, "New");
  assert.equal(p._editingRule.duration, 123);
  assert.equal(p._editingRule.value, "42");
  assert.equal(p._editingRule.update_message_when_active, true);
  assert.match(p._renderRuleEditor(), /value="New"/);
  await handleRulesAction.call(p, "new-rule", {});
  p._cancelRuleEditor();
  assert.equal(p._editingRule.name, "New", "declining discard keeps the rule");
});

test("entity delay input survives leaving the drawer", () => {
  const p = panel();
  p._ensureSettingsDraft();
  const c = control(p, "#delay", { value: "456", dataset: { delayIndex: "0" } }, "#settings-form");
  p.shadowRoot.controls.set("[data-delay-index]", [c]);
  c.dispatchEvent(new Event("input"));
  p.route = { path: "/alert-manager/overview" };
  assert.equal(p._entityDelayDraft[0].delay, 456);
});

test("notification edits survive navigation and decline discard on close or replacement", async () => {
  const p = panel();
  await handleNotificationProfileAction.call(p, "new-notification-profile", {});
  control(p, "#notification-profile-name", { value: "Edited" }, "#settings-form").dispatchEvent(new Event("input"));
  control(p, "#notification-profile-enabled", { checked: true }, "#settings-form").dispatchEvent(new Event("change"));
  control(p, "#notification-reminder", { value: "900" }, "#settings-form").dispatchEvent(new Event("input"));
  p.route = { path: "/alert-manager/overview" };
  p.route = { path: "/alert-manager/settings" };
  p._captureNotificationProfileDraft();
  await handleNotificationProfileAction.call(p, "new-notification-profile", {});
  assert.equal(p._notificationProfileDraft.name, "Edited");
  assert.equal(p._notificationProfileDraft.enabled, true);
  assert.equal(p._notificationProfileDraft.default_policy.reminder_interval, 900);
  await handleNotificationProfileAction.call(p, "close-configuration-drawer", {});
  assert.equal(p._configurationDrawer.kind, "notification");
  p._settingsDraft.notification_profiles = [{ id: "other", name: "Other" }];
  await handleNotificationProfileAction.call(p, "edit-notification-profile", { dataset: { profileId: "other" } });
  assert.equal(p._notificationProfileDraft.name, "Edited");
});

test("native selector events retain source, operator, entities and cleared Jinja fields", async () => {
  const p = panel();
  p._editingRule = { name: "Rule", source: "state", operator: "above", value: "10", duration: 60, condition_template: "old", message: "old" };
  p._ruleAttributeOptions = () => [];
  p._refreshRuleAttributeSelector = p._refreshRuleConditionSection = () => {};
  for (const id of ["source", "operator", "entity-ids", "attribute", "condition-template", "message-template"]) {
    control(p, `#rule-${id}`, {}, "#rule-form");
  }
  p._hydrateRuleEditorControls();
  for (const [id, type, value] of [
    ["source", "selected", "attribute"],
    ["operator", "selected", "below"],
    ["entity-ids", "value-changed", ["sensor.changed"]],
    ["attribute", "value-changed", "battery"],
    ["condition-template", "value-changed", "{{ true }}"],
    ["message-template", "value-changed", "New message"],
    ["message-template", "value-changed", ""],
  ]) {
    p.shadowRoot.querySelector(`#rule-${id}`).dispatchEvent(new CustomEvent(type, { detail: { value } }));
  }
  p.route = { path: "/alert-manager/overview" };
  p.route = { path: "/alert-manager/rules" };
  let sent;
  p._call = async (message) => { sent = message; return null; };
  await p._saveRule(new Root());
  assert.equal(sent.rule.source, "attribute");
  assert.equal(sent.rule.operator, "below");
  assert.equal(sent.rule.attribute, "battery");
  assert.deepEqual(sent.rule.entity_ids, ["sensor.changed"]);
  assert.equal(sent.rule.condition_template, "{{ true }}");
  assert.equal(sent.rule.message, null);
});

test("saving general settings retains a notification draft left in another drawer", async () => {
  const p = panel();
  await handleNotificationProfileAction.call(p, "new-notification-profile", {});
  control(p, "#notification-profile-name", { value: "Unsaved" }, "#settings-form").dispatchEvent(new Event("input"));
  p._resetSettingsDraft({ preserveNotification: true });
  assert.equal(p._notificationProfileDraft.name, "Unsaved");
});
