import assert from "node:assert/strict";
import test from "node:test";

import { openAlertDeepLink } from "../frontend-src/components/alert-table.js";
import {
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
  primary_targets: ["notify.phone"],
  fallback_targets: ["notify.tablet"],
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

  assert.match(markup, /id="notification-primary-targets"/);
  assert.match(markup, /data-notification-exception="0"/);
  assert.match(markup, /data-action="save-notification-profile"/);
  assert.doesNotMatch(markup, /<(button|select|input)\b/);
});

test("new profiles default to a small valid policy but require a destination", () => {
  const draft = newNotificationProfileDraft();
  draft.name = "Owner";
  assert.equal(
    notificationProfileValidationError(draft, t),
    "notifications.validation.primary",
  );
  draft.primary_targets = ["notify.phone"];
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
