import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { t as translate } from "../frontend-src/utils/translations.js";
import { settingsStyles } from "../frontend-src/styles/settings-styles.js";

import { openAlertDeepLink } from "../frontend-src/components/alert-table.js";
import {
  captureNotificationProfileDraft,
  handleNotificationProfileAction,
  hydrateNotificationProfileControls,
  newNotificationProfileDraft,
  moveNotificationException,
  notificationProfileValidationError,
  renderNotificationProfileDrawer,
  renderNotificationProfiles,
  updateNotificationProfileUsage,
} from "../frontend-src/components/notification-profiles.js";

const t = (key, replacements = {}) => Object.entries(replacements).reduce(
  (value, [name, replacement]) => value.replaceAll(`{${name}}`, replacement),
  key,
);

test("notification exception actions have no extra gap and retain native button sizing", () => {
  const styles = [...settingsStyles.matchAll(/\.notification-exception-heading\s*\{([^}]+)\}/g)].at(-1)?.[1];
  assert.match(styles, /gap:\s*0\s*;/);
  assert.match(styles, /justify-content:\s*flex-end\s*;/);
  assert.doesNotMatch(styles, /(?:width|height|--mdc-icon-button-size)\s*:/);
});

const profile = {
  id: "owner",
  name: "Owner",
  enabled: true,
  targets: ["notify.phone", "notify.tablet"],
  label_ids: [],
  default_policy: {
    notify_on_start: true,
    notify_on_resolved: false,
    reminder_interval: 300,
  },
  exceptions: [{
    selector_type: "label",
    selector_id: "battery",
    notify_on_resolved: true,
  }],
};

for (const [language, emptyTitle, summary] of [
  ["fr", "Nouvelle exception", "Nouvelle : Oui · Résolue : Oui · Rappel : Jamais"],
  ["en", "New exception", "New: Yes · Resolved: Yes · Reminder: Never"],
]) {
  test(`notification summaries resolve real ${language} resources with and without labels`, () => {
    const catalog = JSON.parse(readFileSync(new URL(
      `../custom_components/alert_manager/translations/${language}.json`, import.meta.url,
    ), "utf8"));
    const resources = {};
    const flatten = (value, prefix) => {
      for (const [key, item] of Object.entries(value)) {
        if (typeof item === "object") flatten(item, `${prefix}.${key}`);
        else resources[`${prefix}.${key}`] = item;
      }
    };
    flatten(catalog.config_panel, "component.alert_manager.config_panel");
    const t = (key, params) => translate.call({
      _translations: resources, _englishTranslations: {},
    }, key, params);
    const draft = structuredClone(profile);
    draft.default_policy.reminder_interval = null;
    draft.exceptions.push({ selector_ids: [], notify_on_resolved: true });
    const markup = renderNotificationProfileDrawer({
      draft, labels: [{ label_id: "battery", name: "Battery" }], t,
    });
    assert.match(markup, /header="Battery"/);
    assert.ok(markup.includes(`header="${emptyTitle}"`));
    assert.equal(markup.split(`secondary="${summary}"`).length - 1, 2);
    assert.doesNotMatch(markup, /component\.alert_manager\.config_panel|\{(?:start|resolved|reminder)\}/);
  });
}

test("exception header uses dense native badges and refreshes selected labels without removal controls", () => {
  const oldDocument = globalThis.document;
  const oldElements = globalThis.customElements;
  globalThis.customElements = { get: () => class {} };
  globalThis.document = { createElement: (tagName) => ({
    tagName, attributes: {}, children: [], style: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    append(child) { this.children.push(child); },
  }) };
  try {
    const draft = structuredClone(profile);
    const header = { replaceChildren(child) { this.child = child; } };
    const summary = {};
    const expansion = {
      querySelector: (selector) => selector === ".notification-exception-labels" ? header : summary,
      querySelectorAll: () => [], hasAttribute: () => false, addEventListener() {},
    };
    const callbacks = {};
    const panel = {
      _notificationProfileDraft: draft,
      _labels: [{ label_id: "battery", name: "Battery", color: "blue", icon: "mdi:battery" }],
      _t: t, _multipleSelectorValue: (value) => value,
      _configureSelector: (id, config, value, callback) => { callbacks[id] = callback; },
      shadowRoot: { querySelector: (selector) => selector === '[data-notification-expansion="0"]' ? expansion : null },
    };
    hydrateNotificationProfileControls(panel);
    const badge = header.child.children[0];
    assert.equal(badge.tagName, "ha-label");
    assert.equal(badge.textContent, "Battery");
    assert.equal(badge.attributes.color, "blue");
    assert.equal(badge.attributes.dense, "");
    assert.equal(badge.attributes.removable, undefined);
    assert.equal(badge.children.length, 1);
    assert.equal(badge.children[0].attributes.icon, "mdi:battery");
    callbacks["notification-exception-selector-0"](["missing"]);
    assert.equal(header.child.children[0].textContent, "missing");
    callbacks["notification-exception-selector-0"]([]);
    assert.equal(header.textContent, "notifications.new_exception");
    assert.match(settingsStyles, /\.notification-exception-labels > span\s*\{ flex-wrap: wrap;/);
  } finally {
    globalThis.document = oldDocument;
    globalThis.customElements = oldElements;
  }
});

test("notification profile list exposes edit without standalone test or delete actions", () => {
  const markup = renderNotificationProfiles({
    profiles: [profile], usage: { owner: 12 }, busy: false, t,
  });

  assert.match(markup, /<ha-card/);
  assert.doesNotMatch(markup, /data-action="test-notification-profile"/);
  assert.match(markup, /data-action="edit-notification-profile"/);
  assert.doesNotMatch(markup, /data-action="delete-notification-profile"/);
  assert.equal(markup.match(/data-profile-id="owner"/g)?.length, 1);
  assert.doesNotMatch(markup, /data-index=/);
  assert.doesNotMatch(markup, /<(button|select|input)\b/);
  assert.match(markup, /notification-profile-name"><strong>Owner<\/strong><\/div>\s*<div class="notification-profile-meta">/);
  assert.match(markup, /data-notification-profile-usage="owner">notifications\.usage_last_24h/);
  assert.doesNotMatch(markup, /notifications\.(targets_summary|policy_summary)/);
});

test("notification usage refresh updates only the matching profile text", () => {
  const elements = [
    { dataset: { notificationProfileUsage: "owner" }, textContent: "" },
    { dataset: { notificationProfileUsage: "backup" }, textContent: "" },
  ];
  updateNotificationProfileUsage(
    { querySelectorAll: () => elements },
    { owner: 1, backup: 4 },
    t,
  );

  assert.equal(elements[0].textContent, "notifications.usage_last_24h_one");
  assert.equal(elements[1].textContent, "notifications.usage_last_24h");
});

test("notification drawer uses HA selectors and keeps advanced exceptions inline", () => {
  const markup = renderNotificationProfileDrawer({
    draft: profile,
    packs: [{ id: "battery", translation_key: "battery" }],
    rules: [{ id: "freezer", name: "Freezer" }],
    busy: false,
    useBottomSheet: false,
    t,
  });

  assert.match(markup, /id="notification-targets"/);
  const header = markup.match(/<ha-dialog-header[\s\S]*?<\/ha-dialog-header>/)?.[0] ?? "";
  assert.match(header, /slot="actionItems" class="notification-profile-header-toggle"/);
  assert.match(header, /id="notification-profile-enabled"/);
  assert.equal(markup.match(/id="notification-profile-enabled"/g)?.length, 1);
  assert.doesNotMatch(markup, /notification-profile-enabled-field/);
  assert.match(markup, /data-notification-exception="0"/);
  assert.doesNotMatch(markup, /notifications\.exception_number|notification-exception-title/);
  assert.match(markup, /notification-exception-heading"><ha-icon-button class="notification-exception-reorder"/);
  assert.match(markup, /<\/ha-icon-button><ha-icon-button class="configuration-remove" data-action="remove-notification-exception"/);
  assert.match(markup, /<ha-selector id="notification-exception-selector-0"/);
  assert.match(markup, /<div class="field full"><span class="field-label">[^<]*<\/span><ha-selector id="notification-exception-selector-0"/);
  assert.doesNotMatch(markup, /notification-exception-type/);
  assert.match(markup, /notification-policy-card[\s\S]*notification-policy-switches[\s\S]*notification-policy-reminder/);
  assert.match(markup, /data-action="save-notification-profile"/);
  assert.doesNotMatch(markup, /data-options=/);
  assert.doesNotMatch(markup, /<(button|select|input)\b/);
});

test("exception switches and reminder reuse the default policy layout", () => {
  const draft = structuredClone(profile);
  draft.exceptions[0].reminder_interval = 300;

  const markup = renderNotificationProfileDrawer({
    draft,
    busy: false,
    useBottomSheet: false,
    t,
  });

  assert.match(markup, /notification-policy-card full[\s\S]*notification-policy-switches[\s\S]*notification-policy-reminder/);
  assert.match(markup, /<ha-switch id="notification-exception-start-0"[^>]*checked/);
  assert.match(markup, /<ha-switch id="notification-exception-resolved-0"[^>]*checked/);
  assert.match(markup, /id="notification-exception-reminder-0"[^>]*data-duration-value="300"/);
  assert.doesNotMatch(markup, /notification-exception-reminder-mode|<ha-select\b/);
});

test("notification validation is rendered inside the open drawer", () => {
  const markup = renderNotificationProfileDrawer({
    draft: newNotificationProfileDraft(),
    busy: false,
    useBottomSheet: false,
    validationError: "Select one entity",
    t,
  });

  const errorIndex = markup.indexOf('<div class="configuration-drawer-banner">');
  const formIndex = markup.indexOf('<div class="side-drawer-form">');
  assert.ok(errorIndex > 0);
  assert.ok(errorIndex < formIndex);
  assert.match(markup, /<ha-alert class="notification-profile-error" alert-type="error">Select one entity<\/ha-alert>/);
  assert.match(markup, /type="button"[^>]*data-action="save-notification-profile"/);
});

test("saving without an entity refreshes the fixed drawer error", async () => {
  const draft = newNotificationProfileDraft();
  draft.name = "Owner";
  let refreshes = 0;
  const panel = {
    _notificationProfileDraft: draft,
    _notificationProfileId: null,
    _t: t,
    _refreshSettingsConfigurationDrawer: () => { refreshes += 1; },
    shadowRoot: { querySelector: () => null },
  };

  await handleNotificationProfileAction.call(
    panel,
    "save-notification-profile",
    { dataset: {} },
  );

  assert.equal(panel._notificationProfileValidationError, "notifications.validation.targets");
  assert.equal(refreshes, 1);
});

test("a valid notification profile is serialized once and closes the drawer", async () => {
  const draft = newNotificationProfileDraft();
  Object.assign(draft, {
    name: "Owner",
    enabled: true,
    targets: ["notify.ha_failover"],
  });
  const requests = [];
  let renders = 0;
  const controls = {
    "#notification-profile-name": { value: "Owner" },
    "#notification-profile-enabled": { checked: true },
    "#notification-start": { checked: true },
    "#notification-resolved": { checked: true },
    "#notification-reminder": { value: "" },
  };
  const panel = {
    _notificationProfileDraft: draft,
    _notificationProfileId: null,
    _notificationProfileValidationError: null,
    _configurationDrawer: { kind: "notification" },
    _settingsDraft: { notification_profiles: [] },
    _busy: false,
    _notice: null,
    _t: t,
    _refreshUiState: () => {},
    _render: () => { renders += 1; },
    _api: {
      call: async (request) => {
        requests.push(request);
        return { notification_profiles: request.config.notification_profiles };
      },
    },
    shadowRoot: { querySelector: (selector) => controls[selector] ?? null },
  };

  await handleNotificationProfileAction.call(
    panel,
    "save-notification-profile",
    { dataset: {} },
  );

  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].config.notification_profiles[0].targets, [
    "notify.ha_failover",
  ]);
  assert.equal(panel._notificationProfileDraft, null);
  assert.equal(panel._configurationDrawer, null);
  assert.equal(panel._notificationProfileValidationError, null);
  assert.equal(renders, 1);
});

test("backend profile errors stay visible at the top of the drawer", async () => {
  const draft = structuredClone(profile);
  let drawerRefreshes = 0;
  const controls = {
    "#notification-profile-name": { value: draft.name },
    "#notification-profile-enabled": { checked: true },
    "#notification-start": { checked: true },
    "#notification-resolved": { checked: false },
    "#notification-reminder": { value: "300" },
  };
  const panel = {
    _notificationProfileDraft: draft,
    _notificationProfileId: draft.id,
    _configurationDrawer: { kind: "notification" },
    _settingsDraft: { notification_profiles: [draft] },
    _busy: false,
    _notice: null,
    _t: t,
    _errorText: () => "Profile rejected",
    _refreshUiState: () => {},
    _refreshSettingsConfigurationDrawer: () => { drawerRefreshes += 1; },
    _api: { call: async () => { throw new Error("rejected"); } },
    shadowRoot: { querySelector: (selector) => controls[selector] ?? null },
  };

  await handleNotificationProfileAction.call(
    panel,
    "save-notification-profile",
    { dataset: {} },
  );

  assert.equal(panel._notice, null);
  assert.equal(panel._notificationProfileValidationError, "Profile rejected");
  assert.equal(panel._notificationProfileDraft.id, profile.id);
  assert.equal(drawerRefreshes, 1);
});

test("notification exception changes refresh only the settings drawer", async () => {
  let drawerRefreshes = 0;
  const panel = {
    _notificationProfileDraft: structuredClone(profile),
    _refreshSettingsConfigurationDrawer: (selector) => {
      drawerRefreshes += 1;
      assert.equal(selector, '[data-notification-exception="1"]');
    },
    _render: () => assert.fail("the complete panel should not render"),
    shadowRoot: { querySelector: () => null },
  };

  await handleNotificationProfileAction.call(
    panel,
    "add-notification-exception",
    { dataset: {} },
  );

  assert.equal(panel._notificationProfileDraft.exceptions.length, 2);
  assert.equal(drawerRefreshes, 1);
});

test("notification label selectors use native HA labels", () => {
  const controls = new Map();
  const panel = {
    _notificationProfileDraft: structuredClone(profile),
    _configureSelector: (id, selector, value) => controls.set(id, { selector, value }),
    _configureSelect: () => {},
    _multipleSelectorValue: (value) => value,
    _t: t,
  };

  hydrateNotificationProfileControls(panel, {
    packs: [{ id: "battery", translation_key: "battery" }],
    rules: [{ id: "freezer", name: "Freezer" }],
  });

  assert.deepEqual(controls.get("notification-exception-selector-0"), {
    selector: { label: { multiple: true } },
    value: ["battery"],
  });
});

test("new profiles default to a small valid policy but require an entity", () => {
  const draft = newNotificationProfileDraft();
  draft.name = "Owner";
  assert.equal(
    notificationProfileValidationError(draft, t),
    "notifications.validation.targets",
  );
  draft.targets = ["notify.phone"];
  assert.equal(notificationProfileValidationError(draft, t), null);
});

test("single-alert query opens the existing details UI and stale ids do nothing", () => {
  const originalWindow = globalThis.window;
  let opened;
  const panel = {
    _handledAlertDeepLink: null,
    _activeTab: "settings",
    _tableRows: () => [{ id: "battery:sensor.test", status: "active" }],
    _openAlertDetails: (kind, row) => { opened = { kind, row }; },
  };
  try {
    globalThis.window = { location: { search: "?alert=battery%3Asensor.test" } };
    openAlertDeepLink.call(panel);
    assert.equal(panel._activeTab, "overview");
    assert.equal(opened.kind, "overview");
    assert.equal(opened.row.id, "battery:sensor.test");

    globalThis.window.location.search = "?alert=missing";
    opened = undefined;
    openAlertDeepLink.call(panel);
    assert.equal(opened, undefined);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("notification exceptions have no type or pack dropdown", () => {
  const selects = new Map();
  hydrateNotificationProfileControls({
    _notificationProfileDraft: structuredClone(profile),
    _t: t,
    _configureSelector() {},
    _configureSelect: (id, options) => selects.set(id, options),
  }, { packs: [{ id: "battery" }] });
  assert.equal(selects.has("notification-exception-type-0"), false);
  assert.equal(selects.has("notification-exception-selector-0"), false);
});


test("exception label chips retain every selected label and support removal", () => {
  const draft = structuredClone(profile);
  let selectLabel;
  const panel = {
    _notificationProfileDraft: draft,
    _configureSelector: (id, schema, value, onChange) => {
      if (id === "notification-exception-selector-0") selectLabel = onChange;
    },
    _configureSelect: () => {},
    _multipleSelectorValue: (value) => value,
    _t: t,
  };
  hydrateNotificationProfileControls(panel);
  selectLabel(["battery", "important"]);
  assert.deepEqual(draft.exceptions[0].selector_ids, ["battery", "important"]);
  assert.equal(Object.hasOwn(draft.exceptions[0], "selector_id"), false);
  selectLabel([]);
  assert.deepEqual(draft.exceptions[0].selector_ids, []);
  assert.equal(notificationProfileValidationError(draft, t), "notifications.validation.selector");
  selectLabel(["battery"]);
  assert.deepEqual(draft.exceptions[0].selector_ids, ["battery"]);
});

test("cloning exception labels isolates edits and converts legacy single labels", async () => {
  const { cloneNotificationProfile } = await import("../frontend-src/components/notification-profiles.js");
  const legacy = cloneNotificationProfile(profile);
  assert.deepEqual(legacy.exceptions[0].selector_ids, ["battery"]);
  assert.equal(Object.hasOwn(legacy.exceptions[0], "selector_id"), false);
  const clone = cloneNotificationProfile(legacy);
  clone.exceptions[0].selector_ids.push("important");
  assert.deepEqual(legacy.exceptions[0].selector_ids, ["battery"]);
});


test("moving exceptions preserves edited values and saves their new priority order", async () => {
  const draft = structuredClone(profile);
  draft.exceptions = [
    { selector_type: "label", selector_ids: ["first"], reminder_interval: 300 },
    { selector_type: "label", selector_ids: ["second"], notify_on_start: false },
    { selector_type: "label", selector_ids: ["third"], notify_on_resolved: true },
  ];
  const original = JSON.stringify(draft);
  const controls = {
    "#notification-profile-name": { value: "Edited name" },
    "#notification-profile-enabled": { checked: true },
    "#notification-start": { checked: true },
    "#notification-resolved": { checked: false },
    "#notification-reminder": { value: "300" },
    "#notification-exception-reminder-0": { value: "600" },
  };
  let refreshes = 0;
  let saved;
  const panel = {
    _notificationProfileDraft: draft,
    _notificationProfileOriginal: original,
    _notificationProfileId: draft.id,
    _configurationDrawer: { kind: "notification" },
    _settingsDraft: { notification_profiles: [structuredClone(profile)] },
    shadowRoot: { querySelector: (selector) => controls[selector] ?? null },
    _refreshSettingsConfigurationDrawer: () => {
      refreshes += 1;
      delete controls["#notification-exception-reminder-0"];
      controls["#notification-exception-reminder-2"] = { value: "600" };
    },
    _t: t,
    _refreshUiState() {},
    _render() {},
    _api: { call: async ({ config }) => { saved = config; return config; } },
  };
  moveNotificationException(panel, 0, 2);
  assert.equal(refreshes, 1);
  assert.deepEqual(draft.exceptions.map((item) => item.selector_ids[0]), ["second", "third", "first"]);
  assert.equal(draft.exceptions[2].reminder_interval, 600);
  assert.equal(draft.name, "Edited name");
  const oldWindow = globalThis.window;
  let prompts = 0;
  globalThis.window = { confirm: () => { prompts += 1; return false; } };
  try {
    await handleNotificationProfileAction.call(panel, "close-configuration-drawer", {});
    assert.equal(prompts, 1);
    assert.equal(panel._notificationProfileDraft, draft);
  } finally {
    globalThis.window = oldWindow;
  }
  await handleNotificationProfileAction.call(panel, "save-notification-profile", {});
  assert.deepEqual(saved.notification_profiles[0].exceptions, draft.exceptions);
});

test("exception reorder ignores invalid moves and works in both directions", () => {
  const exceptions = [{ selector_ids: ["a"] }, { selector_ids: ["b"] }, { selector_ids: ["c"] }];
  const panel = {
    _notificationProfileDraft: { exceptions },
    shadowRoot: { querySelector: () => null },
    _refreshSettingsConfigurationDrawer() {},
  };
  for (const [from, to] of [[-1, 0], [0, 3], [0, NaN], [0, 0], [0.5, 1]]) {
    moveNotificationException(panel, from, to);
  }
  assert.deepEqual(exceptions.map((item) => item.selector_ids[0]), ["a", "b", "c"]);
  moveNotificationException(panel, 2, 0);
  assert.deepEqual(exceptions.map((item) => item.selector_ids[0]), ["c", "a", "b"]);
  panel._busy = true;
  moveNotificationException(panel, 0, 2);
  assert.equal(exceptions[0].selector_ids[0], "c");
});

test("native sortable binds once, defers reorder until drag end and supports the keyboard", async () => {
  const previousCustomElements = globalThis.customElements;
  globalThis.customElements = { get: () => true };
  const handlers = [];
  const sortable = { isConnected: true, addEventListener: (name, handler) => handlers.push(handler) };
  const panel = {
    _notificationProfileDraft: { ...structuredClone(profile), exceptions: [
      { selector_ids: ["a"] }, { selector_ids: ["b"] }, { selector_ids: ["c"] },
    ] },
    shadowRoot: { querySelector: (selector) => selector === "#notification-exception-sortable" ? sortable : null },
    _configureSelector() {}, _configureSelect() {}, _t: t,
    _refreshSettingsConfigurationDrawer() {},
  };
  try {
    hydrateNotificationProfileControls(panel);
    hydrateNotificationProfileControls(panel);
    assert.equal(handlers.length, 1);
    handlers[0]({ detail: { oldIndex: 0, newIndex: 2 }, stopPropagation() {} });
    assert.equal(panel._notificationProfileDraft.exceptions[0].selector_ids[0], "a");
    await Promise.resolve();
    assert.equal(panel._notificationProfileDraft.exceptions[2].selector_ids[0], "a");
    sortable.onkeydown({ key: "Home", target: { closest: () => ({ dataset: { index: "2" } }) }, preventDefault() {}, stopPropagation() {} });
    assert.equal(panel._notificationProfileDraft.exceptions[0].selector_ids[0], "a");
  } finally {
    globalThis.customElements = previousCustomElements;
  }
});

// Exercise the editor against a controlled backend boundary, including pending calls.
const { cloneNotificationProfile, notificationProfileToYaml, switchNotificationEditor } =
  await import("../frontend-src/components/notification-profiles.js");

function yamlPanel() {
  const draft = cloneNotificationProfile(profile);
  return {
    _notificationProfileDraft: draft,
    _notificationProfileOriginal: JSON.stringify(draft),
    _notificationProfileId: draft.id,
    _configurationDrawer: { kind: "notification" },
    _settingsDraft: { notification_profiles: [draft] },
    _t: t,
    _errorText: (error) => error.message,
    shadowRoot: { querySelector: () => null },
    _refreshSettingsConfigurationDrawer() {},
    _refreshUiState() {},
    _api: { call: async () => cloneNotificationProfile(profile) },
  };
}

test("YAML menu and accessible unlabeled switch render in both modes", () => {
  for (const mode of ["visual", "yaml"]) {
    const markup = renderNotificationProfileDrawer({ draft: profile, mode, t });
    assert.match(markup, /data-notification-editor-menu/);
    assert.match(markup, /notification-profile-enabled[^>]*aria-label="notifications.enabled"/);
    assert.doesNotMatch(markup, /<span>notifications.enabled<\/span>/);
    if (mode === "yaml") {
      assert.match(markup, /<ha-code-editor id="notification-yaml-editor"/);
      assert.doesNotMatch(markup, /id="notification-profile-name"/);
    }
  }
});

test("visual/YAML round trip retains disabled state and ordered partial exceptions", async () => {
  const panel = yamlPanel();
  panel._notificationProfileDraft.enabled = false;
  const expected = cloneNotificationProfile(panel._notificationProfileDraft);
  panel._api.call = async (message) => {
    assert.equal(message.type, "alert_manager/notifications/yaml/validate");
    assert.equal(message.profile_id, profile.id);
    assert.match(message.yaml, /enabled: false/);
    assert.match(message.yaml, /selector_ids: \["battery"\]/);
    assert.doesNotMatch(message.yaml, /^id:/m);
    return expected;
  };
  await switchNotificationEditor(panel);
  assert.equal(panel._notificationEditorMode, "yaml");
  await switchNotificationEditor(panel);
  assert.equal(panel._notificationEditorMode, "visual");
  assert.deepEqual(panel._notificationProfileDraft, expected);
});

test("invalid YAML blocks both saving and returning, keeping the draft and local error", async () => {
  const panel = yamlPanel();
  await switchNotificationEditor(panel);
  const draft = panel._notificationProfileDraft;
  panel._notificationYaml = "name: [";
  panel._api.call = async () => { throw new Error("Invalid YAML"); };
  await switchNotificationEditor(panel);
  await handleNotificationProfileAction.call(panel, "save-notification-profile", {});
  assert.equal(panel._notificationEditorMode, "yaml");
  assert.equal(panel._notificationYaml, "name: [");
  assert.equal(panel._notificationProfileDraft, draft);
  assert.equal(panel._notificationProfileValidationError, "Invalid YAML");
  assert.equal(panel._notice, undefined);
  assert.equal(panel._busy, false);
});

test("closing changed YAML asks for confirmation and cancellation preserves it", async () => {
  const panel = yamlPanel();
  await switchNotificationEditor(panel);
  panel._notificationYaml += "# unsaved comment\n";
  const originalWindow = globalThis.window;
  let confirmations = 0;
  globalThis.window = { confirm: () => { confirmations++; return false; } };
  try {
    await handleNotificationProfileAction.call(panel, "close-configuration-drawer", {});
    assert.equal(confirmations, 1);
    assert.ok(panel._notificationProfileDraft);
    assert.match(panel._notificationYaml, /unsaved comment/);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("late validation never overwrites a newer YAML draft", async () => {
  const panel = yamlPanel();
  await switchNotificationEditor(panel);
  let complete;
  panel._api.call = () => new Promise((resolve) => { complete = resolve; });
  const pending = switchNotificationEditor(panel);
  panel._notificationYaml += "# newer\n";
  complete(cloneNotificationProfile(profile));
  await pending;
  assert.equal(panel._notificationEditorMode, "yaml");
  assert.match(panel._notificationYaml, /newer/);
});

test("YAML enabled control validates and updates the YAML while preserving exceptions", async () => {
  const panel = yamlPanel();
  await switchNotificationEditor(panel);
  const toggle = { checked: false };
  const editor = { dataset: {}, addEventListener() {} };
  panel.shadowRoot.querySelector = (selector) => ({
    "#notification-yaml-editor": editor,
    "#notification-profile-enabled": toggle,
  })[selector] ?? null;
  hydrateNotificationProfileControls(panel);
  await toggle.onchange();
  assert.equal(panel._notificationProfileDraft.enabled, false);
  assert.match(panel._notificationYaml, /enabled: false/);
  assert.match(panel._notificationYaml, /selector_ids: \["battery"\]/);
});

test("saving YAML validates before using the existing configuration save path", async () => {
  const panel = yamlPanel();
  await switchNotificationEditor(panel);
  const updated = cloneNotificationProfile(profile);
  updated.enabled = false;
  updated.name = "Updated";
  panel._notificationYaml = notificationProfileToYaml(updated);
  const calls = [];
  panel._api.call = async (message) => {
    calls.push(message.type);
    if (message.type.endsWith("/validate")) return updated;
    assert.deepEqual(message.config.notification_profiles, [updated]);
    return message.config;
  };
  panel._render = () => {};
  await handleNotificationProfileAction.call(panel, "save-notification-profile", {});
  assert.deepEqual(calls, ["alert_manager/notifications/yaml/validate", "alert_manager/config/update"]);
  assert.equal(panel._notificationProfileDraft, null);
  assert.equal(panel._configurationDrawer, null);
});

const { handleNotificationProfileMenuSelection } =
  await import("../frontend-src/components/notification-profiles.js");
const profileMenuEvent = (value) => ({ detail: { item: { value } } });

for (const mode of ["visual", "yaml"]) {
  test(`profile ${mode} menu offers duplicate and tests only a saved enabled profile`, () => {
    for (const savedProfile of [null, profile, { ...profile, enabled: false }]) {
      const markup = renderNotificationProfileDrawer({ draft: profile, savedProfile, mode, t });
      assert.match(markup, /value="duplicate-notification-profile"/);
      const deleteItem = markup.match(/<ha-dropdown-item value="delete-notification-profile"[^>]*>/)[0];
      assert.equal(deleteItem.includes("disabled"), !savedProfile);
      const testItem = markup.match(/<ha-dropdown-item value="test-notification-profile"[^>]*>/)[0];
      assert.equal(testItem.includes("disabled"), !savedProfile?.enabled);
    }
  });

  test(`duplicating a ${mode} draft creates an isolated unsaved copy and saves a new profile`, async () => {
    const panel = yamlPanel();
    const saved = structuredClone(panel._settingsDraft.notification_profiles);
    panel._notificationProfileDraft = cloneNotificationProfile(profile);
    panel._notificationProfileDraft.exceptions.push({
      selector_type: "label", selector_ids: ["second"], reminder_interval: null,
    });
    panel._notificationProfileDraft.name = "Edited owner";
    panel._notificationProfileDraft.enabled = false;
    panel._notificationProfileDraft.usage = 123;
    panel._notificationProfileDraft.pending_batches = ["batch"];
    const source = panel._notificationProfileDraft;
    const expected = cloneNotificationProfile(source);
    const calls = [];
    panel._api.call = async (message) => {
      calls.push(message.type);
      if (message.type.endsWith("/validate")) return expected;
      return message.config;
    };
    if (mode === "yaml") await switchNotificationEditor(panel);
    await handleNotificationProfileMenuSelection(panel, profileMenuEvent("duplicate-notification-profile"));
    const copy = panel._notificationProfileDraft;
    assert.notEqual(copy.id, source.id);
    assert.notEqual(copy.name, source.name);
    assert.equal(copy.enabled, false);
    assert.equal(panel._notificationProfileId, null);
    assert.equal(panel._notificationEditorMode, "visual");
    assert.deepEqual(copy.exceptions, expected.exceptions);
    assert.equal(copy.usage, undefined);
    assert.equal(copy.pending_batches, undefined);
    assert.deepEqual(panel._settingsDraft.notification_profiles, saved);
    assert.deepEqual(calls, mode === "yaml" ? ["alert_manager/notifications/yaml/validate"] : []);
    copy.targets.push("notify.other");
    copy.label_ids.push("other");
    copy.default_policy.notify_on_start = false;
    copy.exceptions[0].selector_ids.push("extra");
    assert.deepEqual(cloneNotificationProfile(source), expected);
    panel._render = () => {};
    await handleNotificationProfileAction.call(panel, "save-notification-profile", {});
    assert.equal(panel._settingsDraft.notification_profiles.length, 2);
    assert.deepEqual(panel._settingsDraft.notification_profiles[0], saved[0]);
    assert.deepEqual(panel._settingsDraft.notification_profiles[1], copy);
  });
}

test("duplicate cancellation prompts and leaves saved profiles unchanged without sending", async () => {
  const panel = yamlPanel();
  const original = structuredClone(panel._settingsDraft.notification_profiles);
  panel._api.call = () => assert.fail("Cancellation must not call the backend");
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("duplicate-notification-profile"));
  const previousWindow = globalThis.window;
  let prompts = 0;
  globalThis.window = { confirm: () => { prompts++; return true; } };
  try {
    await handleNotificationProfileAction.call(panel, "close-configuration-drawer", {});
    assert.equal(prompts, 1);
    assert.equal(panel._notificationProfileDraft, null);
    assert.deepEqual(panel._settingsDraft.notification_profiles, original);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("duplicate names avoid existing copies and stay within the backend Unicode length limit", async () => {
  const panel = yamlPanel();
  panel._t = (key) => key === "notifications.copy" ? "copie" : key;
  panel._notificationProfileDraft.name = "😀".repeat(255);
  const firstName = "😀".repeat(247) + " (copie)";
  panel._settingsDraft.notification_profiles.push({ ...profile, id: "existing-copy", name: firstName });
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("duplicate-notification-profile"));
  assert.equal(Array.from(panel._notificationProfileDraft.name).length, 255);
  assert.match(panel._notificationProfileDraft.name, / \(copie 2\)$/);
});

test("invalid YAML blocks duplication and preserves its editor error", async () => {
  const panel = yamlPanel();
  await switchNotificationEditor(panel);
  panel._notificationYaml = "name: [";
  const original = panel._notificationProfileDraft;
  panel._api.call = async () => { throw new Error("Invalid YAML"); };
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("duplicate-notification-profile"));
  assert.equal(panel._notificationProfileDraft, original);
  assert.equal(panel._notificationProfileId, original.id);
  assert.equal(panel._notificationEditorMode, "yaml");
  assert.equal(panel._notificationProfileValidationError, "Invalid YAML");
});

test("menu testing uses the saved identity and is blocked for new, disabled or busy profiles", async () => {
  const panel = yamlPanel();
  let calls = 0;
  panel._call = async (message) => {
    calls++;
    assert.deepEqual(message, { type: "alert_manager/notifications/test", profile_id: profile.id });
    return { success: true, failed_targets: [] };
  };
  panel._notificationProfileDraft = { ...profile, targets: ["notify.unsaved"] };
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("test-notification-profile"));
  assert.equal(calls, 1);
  panel._busy = true;
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("test-notification-profile"));
  panel._busy = false;
  panel._settingsDraft.notification_profiles[0].enabled = false;
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("test-notification-profile"));
  panel._notificationProfileId = null;
  await handleNotificationProfileMenuSelection(panel, profileMenuEvent("test-notification-profile"));
  assert.equal(calls, 1);
});

for (const mode of ["visual", "yaml"]) {
  test(`deleting from the ${mode} profile menu confirms and clears the editor only after saving`, async () => {
    const panel = yamlPanel();
    panel._notificationEditorMode = mode;
    panel._ensureSettingsDraft = () => {};
    panel._render = () => {};
    const previousWindow = globalThis.window;
    let confirmed = false;
    let fail = false;
    let calls = 0;
    globalThis.window = { confirm: () => confirmed };
    panel._api.call = async (message) => {
      calls++;
      assert.deepEqual(message, {
        type: "alert_manager/config/update", config: { notification_profiles: [] },
      });
      if (fail) throw new Error("Save failed");
      return message.config;
    };
    try {
      await handleNotificationProfileMenuSelection(panel, profileMenuEvent("delete-notification-profile"));
      assert.equal(calls, 0);
      confirmed = true;
      fail = true;
      await handleNotificationProfileMenuSelection(panel, profileMenuEvent("delete-notification-profile"));
      assert.equal(panel._notificationProfileId, profile.id);
      assert.equal(panel._settingsDraft.notification_profiles.length, 1);
      assert.equal(panel._notificationProfileValidationError, "Save failed");
      fail = false;
      await handleNotificationProfileMenuSelection(panel, profileMenuEvent("delete-notification-profile"));
      assert.deepEqual(panel._settingsDraft.notification_profiles, []);
      assert.equal(panel._notificationProfileDraft, null);
      assert.equal(panel._configurationDrawer, null);
    } finally {
      globalThis.window = previousWindow;
    }
  });
}


test("notification exceptions preserve effective legacy values and save explicit switches", () => {
  const draft = structuredClone(profile);
  draft.default_policy.notify_on_start = false;
  const before = structuredClone(draft);
  const markup = renderNotificationProfileDrawer({ draft, t });
  assert.deepEqual(draft, before);
  assert.doesNotMatch(markup.match(/<ha-switch id="notification-exception-start-0"[^>]*>/)[0], /checked/);
  assert.match(markup, /<ha-switch id="notification-exception-resolved-0"[^>]*checked/);
  const controls = {
    "#notification-profile-name": { value: draft.name },
    "#notification-profile-enabled": { checked: true },
    "#notification-start": { checked: false },
    "#notification-resolved": { checked: false },
    "#notification-reminder": { value: 300 },
    "#notification-exception-start-0": { checked: false },
    "#notification-exception-resolved-0": { checked: true },
    "#notification-exception-reminder-0": { value: "" },
  };
  const panel = { _notificationProfileDraft: draft, shadowRoot: { querySelector: (id) => controls[id] } };
  captureNotificationProfileDraft(panel);
  assert.equal(draft.exceptions[0].notify_on_start, false);
  assert.equal(draft.exceptions[0].notify_on_resolved, true);
  assert.equal(draft.exceptions[0].reminder_interval, null);
  controls["#notification-exception-start-0"].checked = true;
  controls["#notification-exception-reminder-0"].value = 600;
  captureNotificationProfileDraft(panel);
  assert.equal(draft.exceptions[0].notify_on_start, true);
  assert.equal(draft.exceptions[0].reminder_interval, 600);
});

test("exception summaries escape label names, inherit policy and preserve expansion through reordering", () => {
  const draft = structuredClone(profile);
  const exception = draft.exceptions[0];
  const summaryT = (key, params) => key === "notifications.exception_summary"
    ? `${params.start} / ${params.resolved} / ${params.reminder}` : t(key, params);
  const context = { draft, labels: [{ label_id: "battery", name: 'Battery <low>' }], t: summaryT };
  let markup = renderNotificationProfileDrawer(context);
  assert.match(markup, /header="Battery &lt;low&gt;" secondary="notifications.yes \/ notifications.yes \/ duration.minutes"/);
  assert.doesNotMatch(markup, /data-notification-expansion="0"[^>]*\bexpanded\b/);
  assert.match(markup, /slot="icons" class="notification-exception-heading"/);
  context.expandedExceptions = new WeakSet([exception]);
  draft.exceptions.unshift({ selector_ids: ["unknown"], reminder_interval: null });
  markup = renderNotificationProfileDrawer(context);
  assert.match(markup, /data-notification-expansion="1"[^>]* expanded/);
  assert.match(markup, /header="unknown" secondary="notifications.yes \/ notifications.no \/ notifications.never"/);
  assert.doesNotMatch(markup, /notification-exception-enabled/);
});

test("folding an exception captures edits and updates its summary without rerendering", () => {
  const draft = structuredClone(profile);
  let handler;
  const expansion = {
    expanded: true,
    hasAttribute: () => true,
    addEventListener: (name, callback) => { handler = callback; },
    removeEventListener: () => { handler = null; },
    querySelectorAll: () => [],
  };
  const controls = {
    '[data-notification-expansion="0"]': expansion,
    '#notification-profile-name': { value: draft.name },
    '#notification-profile-enabled': { checked: true },
    '#notification-exception-start-0': { checked: false },
    '#notification-exception-resolved-0': { checked: true },
    '#notification-exception-reminder-0': { value: "600" },
  };
  const panel = {
    _notificationProfileDraft: draft,
    _labels: [{ label_id: "battery", name: "Battery" }],
    _configureSelector() {},
    _t: (key, params) => key === "notifications.exception_summary" ? JSON.stringify(params) : t(key, params),
    shadowRoot: { querySelector: (selector) => controls[selector] ?? null },
  };
  hydrateNotificationProfileControls(panel);
  hydrateNotificationProfileControls(panel);
  assert.ok(panel._notificationExpandedExceptions.has(draft.exceptions[0]));
  handler({ target: expansion, detail: { expanded: false } });
  assert.equal(panel._notificationExpandedExceptions.has(draft.exceptions[0]), false);
  assert.equal(draft.exceptions[0].notify_on_start, false);
  assert.equal(draft.exceptions[0].reminder_interval, 600);
  assert.equal(expansion.header, "Battery");
  assert.equal(JSON.parse(expansion.secondary).start, "notifications.no");
});
