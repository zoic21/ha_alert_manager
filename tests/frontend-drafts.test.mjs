import { automaticPacks } from "./automatic-fixtures.mjs";
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
  p._hass = { user: { is_admin: true } };
  p._config = { automatic: { battery: { enabled: true, delay: 60, threshold: 15, device_overrides: { dev: { threshold: 20 } }, entity_overrides: {}, label_ids: [] } }, entity_delays: { "sensor.a": 60 } };
  p._packs = automaticPacks().filter((pack) => pack.id === "battery");
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
    control(p, "#auto-battery-delay", { value: "0" }).dispatchEvent(new Event("input"));
    control(p, "#auto-battery-threshold", { value: "27" }).dispatchEvent(new Event("input"));
    const map = control(p, "#override", { value: "31", dataset: { packSetting: "battery", packField: "device_overrides", packIndex: "0", settingId: "threshold" } });
    p.shadowRoot.controls.set("[data-pack-setting], [data-pack-default]", [map]);
    map.dispatchEvent(new Event("input"));
    p.route = { path: "/alert-manager/rules" };
    p.route = { path: "/alert-manager/settings" };
    p._configurationDrawer = { kind: "automatic", id: "battery", fieldId: "pack" };
    p._narrow = narrow;
    p._loadNativeBottomSheet = async () => true;
    updateDrawerLayout.call(p, !narrow);
    await Promise.resolve();
    const markup = p._renderAutomatic();
    assert.doesNotMatch(markup, /auto-battery-enabled[^>]*checked/);
    assert.match(markup, /auto-battery-threshold[^>]*value="27"/);
    assert.match(markup, /value="31"[^>]*data-pack-setting/);
    let sent;
    p._call = async (message) => { sent = message.config.automatic; return null; };
    await p._saveAutomatic();
    assert.deepEqual(sent.battery, { label_ids: [], enabled: false, delay: 0, threshold: 27, device_overrides: { dev: { threshold: 31 } }, entity_overrides: {} });
  });
}

test("rule input/change events retain text, numbers and switches across navigation", async () => {
  const p = panel();
  p._editingRule = { name: "Old", source: "value", operator: "above", value: "10", duration: 60 };
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
  p._editingRule = { name: "Rule", source: "value", operator: "above", value: "10", duration: 60, condition_template: "old", message: "old" };
  p._ruleAttributeOptions = () => [];
  p._refreshRuleAttributeSelector = p._refreshRuleConditionSection = () => {};
  for (const id of ["source", "operator", "entity-ids", "attribute", "condition-template", "message-template"]) {
    control(p, `#rule-${id}`, {}, "#rule-form");
  }
  p._hydrateRuleEditorControls();
  for (const [id, type, value] of [
    ["source", "selected", "value"],
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
  assert.equal(sent.rule.source, "value");
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


test("pack labels use a native multi-selector and retain an independent draft", () => {
  const p = panel();
  p._config.automatic.battery.label_ids = ["old"];
  p._ensureAutomaticDraft();
  let updateLabels;
  p._configureSelector = (id, selector, value, onChange) => {
    if (id !== "auto-battery-labels") return;
    assert.deepEqual(selector, { label: { multiple: true } });
    assert.deepEqual(value, ["old"]);
    updateLabels = onChange;
  };
  p._configurationDrawer = { kind: "automatic", id: "battery" };
  p._hydrateAutomaticControls();
  updateLabels(["cold", "technical"]);
  p._markConfigurationDirty("automatic");
  assert.equal(p._automaticDirty, true);
  assert.deepEqual(p._config.automatic.battery.label_ids, ["old"]);
  assert.deepEqual(p._automaticMapDraft.battery.label_ids, ["cold", "technical"]);
  assert.match(p._renderAutomatic(), /<ha-selector id="auto-battery-labels"/);
  updateLabels([]);
  assert.deepEqual(p._automaticMapDraft.battery.label_ids, []);
});

test("notification batch delay input survives navigation", () => {
  const p = panel();
  p._ensureSettingsDraft();
  assert.equal(p._settingsDraft.notification_batch_delay, 30);
  control(p, "#notification-batch-delay", { value: "120" }, "#settings-form").dispatchEvent(new Event("input"));
  p.route = { path: "/alert-manager/rules" };
  p.route = { path: "/alert-manager/settings" };
  assert.equal(p._settingsDraft.notification_batch_delay, "120");
});


test("detached configuration drawer inputs still capture and mark the correct draft", () => {
  for (const kind of ["automatic", "settings"]) {
    const p = panel();
    p._configurationDrawer = { kind };
    p._automaticDirty = p._settingsDirty = false;
    let captures = 0;
    p._captureAutomaticConfigurationValues = () => { captures += 1; };
    const c = control(p, "#drawer-field", {}, ".configuration-drawer");
    c.dispatchEvent(new Event("input"));
    assert.equal(p._automaticDirty, kind === "automatic");
    assert.equal(p._settingsDirty, kind === "settings");
    assert.equal(captures, kind === "automatic" ? 1 : 0);
  }
});

test("form validation includes the detached configuration drawer", () => {
  const p = panel();
  p._configurationDrawer = { kind: "settings" };
  const drawer = { querySelectorAll: () => [], reportValidity: () => false };
  p.shadowRoot.controls.set(".configuration-drawer", drawer);
  assert.equal(p._reportFormValidity({ id: "settings-form", querySelectorAll: () => [] }), false);
  assert.equal(p._reportFormValidity({ id: "automatic-form", querySelectorAll: () => [] }), true);
});

const { handleAutomaticAction } = await import("../frontend-src/views/automatic.js");
const { handleSettingsAction } = await import("../frontend-src/views/settings.js");
const { handleBottomSheetClosed } = await import("../frontend-src/components/configuration-drawer.js");

for (const kind of ["automatic", "entity_delays", "excluded_entities"]) {
  test(`${kind} drawer confirms changes and discards only its own edits`, async () => {
    const p = panel();
    p._ensureAutomaticDraft();
    p._ensureSettingsDraft();
    p._settingsDraft.excluded_entities = ["sensor.keep"];
    p._automaticDirty = p._settingsDirty = true;
    const handler = kind === "automatic" ? handleAutomaticAction : handleSettingsAction;
    const open = () => handler.call(p, kind === "automatic" ? "open-automatic-configuration" : "open-settings-configuration", {
      dataset: { packId: "battery", fieldId: "pack", configurationId: kind },
    });
    const value = () => kind === "automatic" ? p._automaticMapDraft.battery.device_overrides
      : kind === "entity_delays" ? p._entityDelayDraft : p._settingsDraft.excluded_entities;
    let prompts = 0;
    window.confirm = () => { prompts++; return false; };
    try {
      await open();
      await handler.call(p, "close-configuration-drawer", {});
      assert.equal(prompts, 0, "unchanged drawers close silently");
      assert.equal(p._configurationDrawer, null);
      await open();
      const original = JSON.stringify(value());
      value().push(kind === "automatic" ? { target_id: "new", threshold: 7 }
        : kind === "entity_delays" ? { entity_id: "sensor.new", delay: 7 } : "sensor.new");
      await handler.call(p, "close-configuration-drawer", {});
      assert.equal(prompts, 1);
      assert.ok(p._configurationDrawer, "declining preserves the drawer");
      assert.notEqual(JSON.stringify(value()), original);
      window.confirm = () => true;
      await handler.call(p, "close-configuration-drawer", {});
      assert.equal(p._configurationDrawer, null);
      assert.equal(JSON.stringify(value()), original);
      assert.equal(p._automaticMapDraft.battery.threshold, 15);
      assert.equal(p._settingsDirty, true, "pre-existing unsaved edits stay dirty");
      assert.equal(p._automaticDirty, true);
    } finally { window.confirm = () => false; }
  });
}

test("declining a native swipe close remounts the configuration drawer", async () => {
  const p = panel();
  await handleAutomaticAction.call(p, "open-automatic-configuration", { dataset: { packId: "battery", fieldId: "pack" } });
  p._automaticMapDraft.battery.device_overrides[0].threshold = 99;
  let renders = 0;
  p._render = () => { renders++; };
  await handleBottomSheetClosed(p, [handleAutomaticAction], { target: { dataset: { closeAction: "close-configuration-drawer" } } });
  assert.ok(p._configurationDrawer);
  assert.equal(p._automaticMapDraft.battery.device_overrides[0].threshold, 99);
  assert.equal(renders, 1);
});

const { inheritedPackSetting } = await import("../frontend-src/views/automatic.js");
const { alertDetailsItems } = await import("../frontend-src/components/alert-table.js");

test("sparse inherited values show device origins and source overrides without freezing parents", () => {
  const draft = { delay: 900, threshold: 15, device_overrides: [{ target_id: "dev", delay: 1800 }], entity_overrides: [{ target_id: "sensor.a", threshold: 10 }], source_packs: { unavailable: { delay: 60, device_overrides: [{ target_id: "dev", threshold: 20 }], entity_overrides: [] } } };
  const entities = { "sensor.a": { device_id: "dev" } };
  assert.deepEqual(inheritedPackSetting(draft, "delay", "sensor.a", "entity_overrides", "", entities), { value: 1800, origin: "device" });
  assert.deepEqual(inheritedPackSetting(draft, "threshold", "sensor.a", "entity_overrides", "unavailable", entities), { value: 10, origin: "entity" });
  assert.deepEqual(draft.entity_overrides, [{ target_id: "sensor.a", threshold: 10 }]);
});

test("opening a contextual exception never saves and reset preserves only its target", async () => {
  const p = panel(); let saves = 0; p._call = async () => { saves++; };
  await handleAutomaticAction.call(p, "open-automatic-configuration", { dataset: { packId: "battery", entityId: "sensor.new" } });
  assert.equal(saves, 0);
  assert.deepEqual(p._config.automatic.battery.entity_overrides, {});
  assert.deepEqual(p._automaticMapDraft.battery.entity_overrides, [{ target_id: "sensor.new" }]);
  p._automaticMapDraft.battery.entity_overrides[0].delay = 0;
  p._automaticMapDraft.battery.entity_overrides[0].enabled = false;
  await handleAutomaticAction.call(p, "inherit-pack-row", { dataset: { packId: "battery", fieldId: "entity_overrides", index: "0" } });
  assert.deepEqual(p._automaticMapDraft.battery.entity_overrides, [{ target_id: "sensor.new" }]);
  assert.equal(saves, 0);
});

test("contextual monitoring configuration requires an admin and a current applicable source", () => {
  const context = { _packs: automaticPacks(), _hass: { states: { "sensor.a": { attributes: { device_class: "battery" } } } }, _readOnly: false, _t: (key) => key, _date: (value) => value, _historyDurationText: (value) => value };
  const row = { id: "battery:sensor.a", entityId: "sensor.a", source: { type: "battery" } };
  const action = () => alertDetailsItems.call(context, "history", row).find((item) => item.action === "configure-alert-monitoring");
  assert.deepEqual(action().data, { packId: "battery", sourceId: "", entityId: "sensor.a" });
  context._readOnly = true; assert.equal(action(), undefined);
  context._readOnly = false; row.source.rule_id = "custom"; assert.equal(action(), undefined);
  delete row.source.rule_id; row.source.type = "obsolete"; assert.equal(action(), undefined);
  row.source.type = "battery"; context._hass.states = {}; assert.equal(action(), undefined);
});
