import assert from "node:assert/strict";
import test from "node:test";
import {
  configurationDraftToValue, configurationValueToDraft, configurationFieldToYaml, configurationDrawerForTab,
  hydrateConfigurationYaml, switchConfigurationYaml, validateConfigurationYaml,
} from "../frontend-src/components/configuration-yaml.js";
import { confirmConfigurationDiscard } from "../frontend-src/components/configuration-drawer.js";
import { saveAutomatic, renderAutomaticConfigurationDrawer } from "../frontend-src/views/automatic.js";
import { saveConfiguration, saveSettings, renderSettingsConfigurationDrawer } from "../frontend-src/views/settings.js";

function panel(kind = "settings", id = "entity_delays", fieldId = undefined) {
  const p = {
    _configurationDrawer: { kind, id, fieldId },
    _settingsDraft: { excluded_entities: ["sensor.b", "sensor.a"], excluded_devices: ["b", "a"] },
    _entityDelayDraft: [{ entity_id: "sensor.b", delay: 120 }, { entity_id: "sensor.a", delay: 0 }],
    _automaticMapDraft: { flapping: { enabled: false, label_ids: ["b", "a"], entity_overrides: [
      { target_id: "sensor.b", enabled: false, occurrences: 5, window: 7200, recovery: 600 },
      { target_id: "sensor.a", enabled: true, occurrences: 3, window: 300, recovery: 0 },
    ] } },
    _packs: [{ id: "flapping", config_fields: [{ id: "entity_overrides", type: "entity_settings_map" }] }],
    _captureAutomaticConfigurationValues() {}, _captureEntityDelayValues() {},
    _refreshAutomaticConfigurationDrawer() {}, _refreshSettingsConfigurationDrawer() {},
    _refreshUiState() {}, _markConfigurationDirty(kind) { this.dirty = kind; },
    _t: (key, params) => `${key}${params?.error ?? ""}`,
    _errorText: (error) => error.message,
    _api: { call: async () => { throw new Error("invalid YAML"); } },
  };
  return p;
}

for (const [type, value] of [
  ["entity_delays", { "sensor.b": 120, "sensor.a": 0 }],
  ["entity_number_map", { "automation.b": 3, "automation.a": 1 }],
  ["device_number_map", { b: 15, a: 20 }],
  ["entity_settings_map", { "sensor.b": { enabled: false, window: 300 }, "sensor.a": { enabled: true, window: 600 } }],
  ["device_settings_map", { b: { enabled: false }, a: { enabled: true } }],
  ["pack_settings_map", { connectivity: { window: null }, unavailable: { window: 300 } }],
  ["excluded_entities", ["sensor.b", "sensor.a"]],
  ["excluded_devices", ["b", "a"]],
]) {
  test(`${type} preserves values and order between stored configuration and visual rows`, () => {
    const draft = configurationValueToDraft(value, type);
    const restored = configurationDraftToValue(draft, type);
    assert.deepEqual(restored, value);
    assert.deepEqual(Object.keys(restored), Object.keys(value));
    assert.notEqual(restored, value);
  });
}

test("conversion refuses incomplete or duplicate rows instead of losing entries", () => {
  for (const rows of [ [{ entity_id: "", delay: 0 }], [{ entity_id: "sensor.a", delay: 0 }, { entity_id: "sensor.a", delay: 120 }] ]) {
    assert.throws(() => configurationDraftToValue(rows, "entity_delays"));
  }
});

test("serializer exposes only the scoped field and escapes YAML strings", () => {
  assert.equal(configurationFieldToYaml("excluded_devices", ["true", "a: b", "a\nb"]),
    '"excluded_devices": ["true","a: b","a\\nb"]\n');
  assert.equal(configurationFieldToYaml("source_packs", { unavailable: { window: null } }),
    '"source_packs":\n  "unavailable":\n    "window": null\n');
});

for (const kind of ["settings", "automatic"]) {
  test(`${kind}: switching is draft-only, preserves nested edits, and validates before returning`, async () => {
    const p = kind === "settings" ? panel() : panel("automatic", "flapping", "entity_overrides");
    const before = structuredClone(kind === "settings" ? p._entityDelayDraft : p._automaticMapDraft);
    const drawer = p._configurationDrawer;
    await switchConfigurationYaml(p);
    assert.equal(drawer.mode, "yaml");
    assert.equal(p.dirty, undefined);
    assert.doesNotMatch(drawer.yaml, /label_ids|monitoring_enabled/);
    const value = kind === "settings" ? { "sensor.b": 120, "sensor.a": 0 }
      : configurationDraftToValue(p._automaticMapDraft.flapping.entity_overrides, "entity_settings_map");
    p._api.call = async (request) => {
      assert.equal(request.type, "alert_manager/config/field/yaml/validate");
      assert.equal(request.pack_id, kind === "automatic" ? "flapping" : undefined);
      return { value };
    };
    await switchConfigurationYaml(p);
    assert.equal(drawer.mode, "visual");
    assert.deepEqual(kind === "settings" ? p._entityDelayDraft : p._automaticMapDraft, before);
  });

  test(`${kind}: invalid YAML blocks return and Save, retains draft and shows a panel error`, async () => {
    const p = kind === "settings" ? panel() : panel("automatic", "flapping", "entity_overrides");
    const before = structuredClone(kind === "settings" ? p._entityDelayDraft : p._automaticMapDraft);
    await switchConfigurationYaml(p);
    p._configurationDrawer.yaml = "broken: [";
    await switchConfigurationYaml(p);
    assert.equal(p._configurationDrawer.mode, "yaml");
    assert.equal(p._configurationDrawer.notice.kind, "error");
    assert.match(p._configurationDrawer.notice.text, /invalid YAML/);
    assert.equal(await (kind === "settings" ? saveSettings : saveAutomatic).call(p), false);
    assert.deepEqual(kind === "settings" ? p._entityDelayDraft : p._automaticMapDraft, before);
  });
}

test("closing asks about raw YAML edits even if the visual draft is unchanged", () => {
  const p = panel();
  p._configurationDrawer = { mode: "yaml", yaml: "broken: [", yamlOriginal: "valid: []" };
  let prompts = 0;
  globalThis.window = { confirm: () => { prompts++; return false; } };
  assert.equal(confirmConfigurationDiscard(p, [], "[]"), false);
  assert.equal(prompts, 1);
  p._configurationDrawer.yaml = "valid: []";
  assert.equal(confirmConfigurationDiscard(p, [], "[]"), true);
  assert.equal(prompts, 1);
});

for (const change of ["edit", "close"]) {
  test(`a stale validation response cannot overwrite a draft after ${change}`, async () => {
    const p = panel();
    await switchConfigurationYaml(p);
    let resolve;
    p._api.call = () => new Promise((done) => { resolve = done; });
    const pending = validateConfigurationYaml(p);
    if (change === "edit") p._configurationDrawer.yaml += "# more edits";
    else p._configurationDrawer = null;
    resolve({ value: { "sensor.other": 999 } });
    assert.equal(await pending, false);
    assert.equal(p._entityDelayDraft[0].entity_id, "sensor.b");
    assert.equal(p._busy, false);
  });
}

test("native editor hydration is idempotent and keeps unsaved YAML after remounting", () => {
  const p = panel();
  p._configurationDrawer.mode = "yaml";
  p._configurationDrawer.yaml = "initial";
  const editor = Object.assign(new EventTarget(), { dataset: {} });
  p.shadowRoot = { querySelector: (selector) => selector === "#configuration-yaml-editor" ? editor : null };
  hydrateConfigurationYaml(p);
  hydrateConfigurationYaml(p);
  let updates = 0;
  p._markConfigurationDirty = () => { updates++; };
  editor.dispatchEvent(Object.assign(new Event("value-changed"), { detail: { value: "edited" } }));
  assert.equal(updates, 1);
  hydrateConfigurationYaml(p);
  assert.equal(editor.value, "edited");
});

for (const useBottomSheet of [false, true]) {
  test(`all scoped drawers render the native menu and YAML editor (bottom sheet=${useBottomSheet})`, () => {
    const t = (key) => key;
    for (const id of ["entity_delays", "excluded_entities", "excluded_devices"]) {
      const markup = renderSettingsConfigurationDrawer({
        configurationDrawer: { kind: "settings", id, mode: "yaml" },
        settingsDraft: {}, entityDelayDraft: [], t, useBottomSheet,
      });
      assert.match(markup, /data-configuration-yaml-menu/);
      assert.match(markup, /ha-code-editor/);
      assert.doesNotMatch(markup, /id="excluded-entities"|data-delay-index/);
      assert.equal(markup.includes("<ha-resizable-bottom-sheet"), useBottomSheet);
    }
    const markup = renderAutomaticConfigurationDrawer({
      configurationDrawer: { kind: "automatic", id: "battery", fieldId: "device_thresholds", mode: "yaml" },
      availablePacks: [{ id: "battery", config_fields: [{ id: "device_thresholds", type: "device_number_map", translation_key: "battery_device_thresholds" }] }],
      draft: { battery: { device_thresholds: [] } }, t, useBottomSheet,
    });
    assert.match(markup, /data-configuration-yaml-menu/);
    assert.match(markup, /ha-code-editor/);
  });
}


test("raw YAML survives navigation, then the regular save sends validated pack values", async () => {
  const p = panel("automatic", "flapping", "entity_overrides");
  p._packs[0].available = true;
  p._packs[0].uses_delay = false;
  p._packs[0].config_fields[0].fields = ["enabled", "occurrences", "window", "recovery"].map(
    (id) => ({ id, type: id === "enabled" ? "boolean" : "number" }),
  );
  await switchConfigurationYaml(p);
  const drawer = p._configurationDrawer;
  drawer.yaml += "# unsaved comment";
  p._configurationDrawer = configurationDrawerForTab(p, "history");
  assert.equal(p._configurationDrawer, null);
  p._configurationDrawer = configurationDrawerForTab(p, "settings");
  assert.equal(p._configurationDrawer, drawer);
  assert.match(drawer.yaml, /unsaved comment/);
  const value = { "sensor.changed": { enabled: false, occurrences: 3, window: 300, recovery: 60 } };
  p._api.call = async () => ({ value });
  p._ensureAutomaticDraft = () => {};
  p.shadowRoot = { querySelector: () => null, querySelectorAll: () => [] };
  let sent;
  p._call = async (request) => { sent = request; return null; };
  await saveAutomatic.call(p);
  assert.equal(sent.type, "alert_manager/config/update");
  assert.deepEqual(sent.config.automatic.flapping, {
    enabled: false, label_ids: ["b", "a"], entity_overrides: value,
  });
});


for (const kind of ["settings", "automatic"]) {
  test(`combined Save validates ${kind} YAML once before sending the complete draft`, async () => {
    const p = kind === "settings" ? panel() : panel("automatic", "flapping", "entity_overrides");
    p._packs[0].available = true;
    p._packs[0].uses_delay = false;
    p._packs[0].config_fields[0].fields = ["enabled", "occurrences", "window", "recovery"].map(
      (id) => ({ id, type: id === "enabled" ? "boolean" : "number" }),
    );
    Object.assign(p._settingsDraft, { excluded_labels: [], coherence_ignored_entity_references: [] });
    p._automaticDirty = p._settingsDirty = true;
    p._ensureAutomaticDraft = p._ensureSettingsDraft = p._resetSettingsDraft = p._resetAutomaticDraft = () => {};
    p._commitIgnoredReferenceInput = p._reportFormValidity = () => true;
    p._historyConfig = { retention_limit: 100 };
    const controls = {
      "#automatic-form": {}, "#settings-form": {}, "#history-limit": { value: 100 },
      "#global-delay": { value: 60 }, "#pending-display-delay": { value: 0 },
      "#coherence-schedule": { value: "none" }, "#coherence-scan-esphome": { checked: true },
    };
    p.shadowRoot = { querySelector: (id) => controls[id] ?? null, querySelectorAll: () => [] };
    await switchConfigurationYaml(p);
    const calls = [];
    const value = kind === "settings" ? { "sensor.new": 500 }
      : { "sensor.new": { enabled: false, occurrences: 3, window: 300, recovery: 60 } };
    p._api.call = async (request) => {
      calls.push(request);
      return request.type.endsWith("/validate") ? { value } : {};
    };
    p._saveSettings = saveSettings.bind(p);
    assert.equal(await saveConfiguration.call(p), true);
    assert.deepEqual(calls.map((call) => call.type), [
      "alert_manager/config/field/yaml/validate", "alert_manager/config/update",
    ]);
    const config = calls[1].config;
    assert.deepEqual(kind === "settings" ? config.entity_delays : config.automatic.flapping.entity_overrides, value);
    assert.equal(config.automatic.flapping.enabled, false);
    assert.deepEqual(config.automatic.flapping.label_ids, ["b", "a"]);
  });
}
