import assert from "node:assert/strict";
import test from "node:test";
import {
  durationFieldValue, durationSelectorValue, hydrateDurationFields,
  renderDurationControl, validateDurationFields,
} from "../frontend-src/components/duration-field.js";
import { captureNotificationProfileDraft } from "../frontend-src/components/notification-profiles.js";
import { captureRuleDraftFromForm } from "../frontend-src/components/rule-editor.js";
import { captureAutomaticConfigurationValues, captureAutomaticMapValues } from "../frontend-src/views/automatic.js";

function durationField(seconds, required = true, min = 0, max = 31536000) {
  return Object.assign(new EventTarget(), {
    dataset: { durationValue: String(seconds ?? ""), durationRequired: String(required), durationMin: String(min), durationMax: String(max) },
  });
}
function setup(fields, onChange) {
  const panel = {
    _configuredControls: new WeakSet(), _hass: {},
    _handleInput: onChange ?? (() => {}),
    _t: (key, params) => `${key}:${JSON.stringify(params)}`,
    _durationText: String,
  };
  const root = { querySelectorAll: () => fields };
  hydrateDurationFields(root, panel);
  return { panel, root };
}
function change(field, value) {
  const event = new Event("value-changed", { bubbles: true });
  event.detail = { value };
  field.dispatchEvent(event);
}

test("native duration selectors round-trip seconds, including zero and large existing delays", () => {
  for (const seconds of [0, 10, 30, 60, 3661, 86400, 31536000]) {
    const field = durationField(seconds);
    setup([field]);
    assert.deepEqual(field.selector, { duration: { enable_day: false, enable_millisecond: false, enable_second: true } });
    assert.deepEqual(field.value, durationSelectorValue(seconds));
    assert.equal(durationFieldValue(field), seconds);
  }
  assert.match(renderDurationControl("delay", "Delay", 30, 10, 300), /<ha-selector[^>]*data-duration-value="30"/);
});

test("controlled value-changed events update drafts once and preserve optional clearing", () => {
  const field = durationField(null, false);
  const captured = [];
  const { root, panel } = setup([field], ({ target }) => captured.push(durationFieldValue(target)));
  assert.equal(field.required, false);
  assert.equal(field.value, undefined);
  hydrateDurationFields(root, panel);
  field.dispatchEvent(new Event("input"));
  assert.deepEqual(captured, []);
  change(field, { hours: 2, minutes: 3, seconds: 4 });
  change(field, undefined);
  change(field, { hours: 0, minutes: 0, seconds: 0 });
  assert.deepEqual(captured, [7384, "", 0]);
});

test("batching limits and incomplete or invalid duration values cannot pass validation", () => {
  const field = durationField(30, true, 10, 300);
  const { root, panel } = setup([field]);
  for (const [value, valid] of [
    [{ seconds: 9 }, false], [{ seconds: 10 }, true], [{ minutes: 5 }, true],
    [{ minutes: 5, seconds: 1 }, false], [undefined, false],
    [{ hours: -1, minutes: 61 }, false], [{ seconds: 10.5 }, false],
    [{ seconds: NaN }, false],
  ]) {
    change(field, value);
    assert.equal(validateDurationFields(root, panel), valid);
    assert.equal(Boolean(field.helper), !valid);
  }
});

test("rule form converts native duration objects and retains inherited flapping values", () => {
  const duration = durationField(3661);
  const window = durationField(7200, false);
  const recovery = durationField(null, false);
  setup([duration, window, recovery]);
  const controls = { duration, flapping_window: window, flapping_recovery: recovery };
  const form = { querySelector: (selector) => controls[selector.match(/data-field="([^"]+)"/)?.[1]] };
  const result = captureRuleDraftFromForm(form, { duration: 900, flapping_window: 60 });
  assert.equal(result.duration, 3661);
  assert.equal(result.flapping_window, 7200);
  assert.equal(result.flapping_recovery, null);
  change(window, undefined);
  assert.equal(captureRuleDraftFromForm(form, result).flapping_window, null);
});

test("pack duration and nested overrides retain seconds while cleared overrides stay null", () => {
  const delay = durationField(900, false);
  const window = durationField(7200);
  const source = durationField(null, false);
  Object.assign(source.dataset, { packSourceSetting: "flapping", packField: "packs", sourcePackId: "battery", settingId: "recovery" });
  setup([delay, window, source]);
  const draft = { flapping: { delay: null, window: 60, packs: { battery: { recovery: 10 } } } };
  const panel = {
    _ensureAutomaticDraft() {}, _automaticMapDraft: draft,
    _packs: [{ id: "flapping", config_fields: [{ id: "window", type: "number" }] }],
    shadowRoot: {
      querySelector: (selector) => ({ "#auto-flapping-delay": delay, "#auto-flapping-window": window })[selector],
      querySelectorAll: (selector) => selector === "[data-pack-source-setting]" ? [source] : [],
    },
  };
  captureAutomaticConfigurationValues.call(panel);
  assert.equal(draft.flapping.delay, 900);
  assert.equal(draft.flapping.window, 7200);
  assert.equal(draft.flapping.packs.battery.recovery, null);
  change(source, { minutes: 2 });
  captureAutomaticMapValues.call(panel);
  assert.equal(draft.flapping.packs.battery.recovery, 120);
});

test("notification reminders serialize native durations and clearing still means never", () => {
  const reminder = durationField(3600, false);
  const exception = durationField(60);
  setup([reminder, exception]);
  const draft = { name: "Phone", default_policy: {}, exceptions: [{ reminder_interval: 60 }] };
  const controls = { "#notification-profile-name": { value: "Phone" }, "#notification-reminder": reminder, "#notification-exception-reminder-0": exception };
  const panel = { _notificationProfileDraft: draft, shadowRoot: { querySelector: (selector) => controls[selector] } };
  change(exception, { hours: 1, minutes: 30 });
  captureNotificationProfileDraft(panel);
  assert.equal(draft.default_policy.reminder_interval, 3600);
  assert.equal(draft.exceptions[0].reminder_interval, 5400);
  change(reminder, undefined);
  captureNotificationProfileDraft(panel);
  assert.equal(draft.default_policy.reminder_interval, null);
});
