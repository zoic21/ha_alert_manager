import assert from "node:assert/strict";
import test from "node:test";

import { openAlertDeepLink } from "../frontend-src/components/alert-table.js";
import {
  handleNotificationProfileAction,
  hydrateNotificationProfileControls,
  newNotificationProfileDraft,
  notificationProfileValidationError,
  renderNotificationProfileDrawer,
  renderNotificationProfiles,
} from "../frontend-src/components/notification-profiles.js";

const t = (key, replacements = {}) => Object.entries(replacements).reduce(
  (value, [name, replacement]) => value.replaceAll(`{${name}}`, replacement),
  key,
);

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
    selector_type: "pack",
    selector_id: "battery",
    notify_on_resolved: true,
  }],
};

test("notification profile list exposes native edit, test and delete actions", () => {
  const markup = renderNotificationProfiles({ profiles: [profile], busy: false, t });

  assert.match(markup, /<ha-card/);
  assert.match(markup, /data-action="test-notification-profile"/);
  assert.match(markup, /data-action="edit-notification-profile"/);
  assert.match(markup, /data-action="delete-notification-profile"/);
  assert.equal(markup.match(/data-profile-id="owner"/g)?.length, 3);
  assert.doesNotMatch(markup, /data-index=/);
  assert.doesNotMatch(markup, /<(button|select|input)\b/);
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
  assert.match(markup, /data-notification-exception="0"/);
  assert.match(markup, /notification-policy-switches[\s\S]*notification-policy-reminder/);
  assert.match(markup, /data-action="save-notification-profile"/);
  assert.doesNotMatch(markup, /data-options=/);
  assert.doesNotMatch(markup, /<(button|select|input)\b/);
});

test("custom exception reminders align their mode and value side by side", () => {
  const draft = structuredClone(profile);
  draft.exceptions[0].reminder_interval = 300;

  const markup = renderNotificationProfileDrawer({
    draft,
    busy: false,
    useBottomSheet: false,
    t,
  });

  assert.match(markup, /notification-exception-reminder has-custom-value/);
  assert.match(markup, /notification-exception-reminder-controls[\s\S]*notification-exception-reminder-mode-0[\s\S]*notification-exception-reminder-0/);
});

test("notification validation is rendered inside the open drawer", () => {
  const markup = renderNotificationProfileDrawer({
    draft: newNotificationProfileDraft(),
    busy: false,
    useBottomSheet: false,
    validationError: "Select one entity",
    t,
  });

  assert.match(markup, /<ha-alert class="notification-profile-error" alert-type="error">Select one entity<\/ha-alert>/);
});

test("saving without an entity refreshes the drawer and reveals the error", async () => {
  const draft = newNotificationProfileDraft();
  draft.name = "Owner";
  let refreshes = 0;
  let scrollOptions;
  const panel = {
    _notificationProfileDraft: draft,
    _notificationProfileId: null,
    _t: t,
    _refreshSettingsConfigurationDrawer: () => { refreshes += 1; },
    shadowRoot: {
      querySelector: (selector) => (
        selector === ".configuration-drawer .side-drawer-form"
          ? { scrollTo: (options) => { scrollOptions = options; } }
          : null
      ),
    },
  };

  await handleNotificationProfileAction.call(
    panel,
    "save-notification-profile",
    { dataset: {} },
  );

  assert.equal(panel._notificationProfileValidationError, "notifications.validation.targets");
  assert.equal(refreshes, 1);
  assert.deepEqual(scrollOptions, { top: 0, behavior: "smooth" });
});

test("notification exception changes refresh only the settings drawer", async () => {
  let drawerRefreshes = 0;
  const panel = {
    _notificationProfileDraft: structuredClone(profile),
    _refreshSettingsConfigurationDrawer: () => { drawerRefreshes += 1; },
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

test("notification selector options are hydrated directly from view data", () => {
  const controls = new Map();
  const panel = {
    _notificationProfileDraft: structuredClone(profile),
    _configureSelector: () => {},
    _configureSelect: (id, options) => controls.set(id, options),
    _multipleSelectorValue: (value) => value,
    _t: t,
  };

  hydrateNotificationProfileControls(panel, {
    packs: [{ id: "battery", translation_key: "battery" }],
    rules: [{ id: "freezer", name: "Freezer" }],
  });

  assert.deepEqual(controls.get("notification-exception-selector-0"), [{
    value: "battery",
    label: "packs.battery.name",
  }]);
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
