import assert from "node:assert/strict";
import test from "node:test";
import {
  durationFieldValue, durationSelectorValue, hydrateDurationFields,
  renderDurationControl, renderDurationField, validateDurationFields, reportFormValidity,
} from "../frontend-src/components/duration-field.js";
import { captureNotificationProfileDraft } from "../frontend-src/components/notification-profiles.js";
import { captureRuleDraftFromForm, refreshRuleConditionSection } from "../frontend-src/components/rule-editor.js";
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

test("pack duration and sparse overrides retain seconds while clearing restores inheritance", () => {
  const delay = durationField(900, false);
  const window = durationField(7200);
  const source = durationField(null, false);
  Object.assign(source.dataset, { packSetting: "flapping", packField: "entity_overrides", packIndex: "0", settingId: "recovery" });
  setup([delay, window, source]);
  const draft = { flapping: { delay: null, window: 60, entity_overrides: [{ target_id: "sensor.a", recovery: 10 }] } };
  const panel = {
    _ensureAutomaticDraft() {}, _automaticMapDraft: draft,
    _packs: [{ id: "flapping", config_fields: [{ id: "window", type: "number" }] }],
    shadowRoot: {
      querySelector: (selector) => ({ "#auto-flapping-delay": delay, "#auto-flapping-window": window })[selector],
      querySelectorAll: (selector) => selector === "[data-pack-setting], [data-pack-default]" ? [source] : [],
    },
  };
  captureAutomaticConfigurationValues.call(panel);
  assert.equal(draft.flapping.delay, 900);
  assert.equal(draft.flapping.window, 7200);
  assert.equal(draft.flapping.entity_overrides[0].recovery, undefined);
  change(source, { minutes: 2 });
  captureAutomaticMapValues.call(panel);
  assert.equal(draft.flapping.entity_overrides[0].recovery, 120);
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

test("transition editor preserves separate hold and expiration durations", async () => {
  const { serializeRuleDraft, renderRuleConditionSection } = await import("../frontend-src/components/rule-editor.js");
  const draft = { source: "value_transition", attribute: "mode", name: "Edge", entity_ids: ["sensor.test"], from_value: "A", to_value: "B", duration: 30, auto_resolve: 600 };
  const form = { querySelector() { return null; }, querySelectorAll() { return []; }, elements: { namedItem(name) { return ({ auto_resolve: { value: { minutes: 10 }, dataset: { durationValue: "600" } }, duration: { value: { seconds: 30 }, dataset: { durationValue: "30" } } })[name]; } } };
  const payload = serializeRuleDraft(captureRuleDraftFromForm(form, draft));
  assert.equal(payload.duration, 30);
  assert.equal(payload.auto_resolve, 600);
  assert.equal(payload.from_value, "A");
  assert.equal(payload.to_value, "B");
  assert.equal(payload.attribute, "mode");
  const html = renderRuleConditionSection({ rule: draft, t: (key) => key, renderTextField: (key) => `<ha-textfield name="${key}"></ha-textfield>`, renderNumberField: (key, label, value) => renderDurationControl(key, label, value, 1, 31536000) });
  assert.match(html, /name="from_value"/);
  assert.match(html, /name="to_value"/);
  assert.match(html, /data-duration-value="600"/);
  assert.doesNotMatch(html, /id="rule-operator"/);
});


test("page validation skips the open drawer while drawer Save still validates it", () => {
  const form = { id: "settings-form", reportValidity: () => true, querySelectorAll: () => [] };
  const drawer = {};
  let validations = 0;
  const panel = {
    _configurationDrawer: { kind: "settings" },
    shadowRoot: { querySelector: () => drawer },
    _reportFormValidity: (element) => { assert.equal(element, drawer); validations++; return false; },
  };
  assert.equal(reportFormValidity.call(panel, form, { includeDrawer: false }), true);
  assert.equal(validations, 0);
  assert.equal(reportFormValidity.call(panel, form), false);
  assert.equal(validations, 1);
});


test("transition duration is hydrated after each partial resolution-mode refresh", () => {
  for (const attribute of [null, "mode"]) {
    let fields = [];
    let inputEvents = 0;
    const section = {
      set outerHTML(markup) {
        fields = [...markup.matchAll(/<ha-selector[^>]*data-duration-value="([^"]*)"[^>]*>/g)]
          .map((match) => durationField(match[1]));
      },
      querySelectorAll() { return fields; },
    };
    const panel = {
      _editingRule: { source: "value_transition", attribute, resolve_mode: "state", auto_resolve: 125 },
      _configuredControls: new WeakSet(), _hass: {}, _t: (key) => key,
      _textField: () => "",
      _numberField: (name, label, value, _unit, min, max, options) =>
        renderDurationField(name, label, value, min, max, options),
      _hydrateRuleEditorControls() {},
      _refreshRuleEditor() { assert.fail("mode changes must retain the editor and its scroll position"); },
      _handleInput({ target }) {
        inputEvents += 1;
        this._editingRule.auto_resolve = durationFieldValue(target);
      },
      shadowRoot: { querySelector() { return section; } },
    };
    for (const mode of ["state", "duration", "state", "duration"]) {
      panel._editingRule.resolve_mode = mode;
      refreshRuleConditionSection.call(panel);
      if (mode === "state") {
        assert.equal(fields.length, 0);
        continue;
      }
      assert.equal(fields.length, 1);
      const field = fields[0];
      assert.deepEqual(field.selector, { duration: { enable_day: false, enable_millisecond: false, enable_second: true } });
      assert.equal(field.hass, panel._hass);
      assert.equal(durationFieldValue(field), panel._editingRule.auto_resolve);
      // Rehydration must not attach a second input callback.
      hydrateDurationFields(section, panel);
      change(field, { minutes: 3, seconds: 7 });
      assert.equal(panel._editingRule.auto_resolve, 187);
    }
    assert.equal(inputEvents, 2);
  }
});

test("invalid duration reports the visible field label and sequence step before saving", () => {
  for (const [name, label, expected] of [
    ["auto_resolve", "Résolution automatique", "Résolution automatique"],
    ["sequence-1-duration", "Durée", "Étape 2 — Durée"],
  ]) {
    const field = {
      dataset: { durationValue: "0", durationMin: "1", durationMax: "31536000", field: name },
      value: { seconds: 0 }, required: true,
      getAttribute: () => label,
    };
    const form = { reportValidity: () => true, querySelectorAll: (selector) => selector === "[data-duration-value]" ? [field] : [] };
    const panel = {
      _editingRule: {}, _durationText: (value) => `${value} s`,
      _t: (key, params) => key === "errors.duration_field_bounds" ? `Entre ${params.min} et ${params.max}`
        : `${key === "errors.sequence_field_context" ? `Étape ${params.step} — ` : ""}${params.field} : ${params.detail}`,
      _captureRuleDraft() {}, _refreshRuleEditor() {}, _refreshUiState() {},
    };
    assert.equal(reportFormValidity.call(panel, form), false);
    assert.ok(panel._ruleEditorError.startsWith(expected), panel._ruleEditorError);
    assert.match(panel._ruleEditorError, /Entre 1 s et 31536000 s/);
  }
});

test("new sequence and transition rules display and serialize one-second resolution", async () => {
  const { normalizeRuleDraft, serializeRuleDraft, renderResolutionEditor } = await import("../frontend-src/components/rule-editor.js");
  for (const source of ["value_sequence", "value_transition"]) {
    const rule = normalizeRuleDraft({ source });
    assert.equal(serializeRuleDraft(rule).auto_resolve, 1);
    const html = renderResolutionEditor({ rule, t: (key) => key, renderNumberField: (id, label, value, _unit, min, max) => renderDurationControl(id, label, value, min, max) });
    assert.match(html, /data-duration-value="1"/);
    assert.match(html, /data-duration-min="1"/);
  }
});
