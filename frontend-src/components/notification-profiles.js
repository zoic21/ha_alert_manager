import { renderConfigurationDrawer } from "./configuration-drawer.js";
import { MDI_PLUS } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";

const POLICY_BOOLEAN_OPTIONS = ["inherit", "true", "false"];
const SELECTOR_TYPES = ["pack", "label", "rule"];

export function newNotificationProfileDraft() {
  const generatedId = globalThis.crypto?.randomUUID?.()
    ?? `profile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return {
    id: generatedId,
    name: "",
    enabled: true,
    primary_targets: [],
    fallback_targets: [],
    label_ids: [],
    default_policy: {
      notify_on_start: true,
      notify_on_resolved: true,
      reminder_interval: null,
    },
    exceptions: [],
  };
}

export function cloneNotificationProfile(profile) {
  return {
    ...profile,
    primary_targets: [...(profile.primary_targets ?? [])],
    fallback_targets: [...(profile.fallback_targets ?? [])],
    label_ids: [...(profile.label_ids ?? [])],
    default_policy: { ...(profile.default_policy ?? {}) },
    exceptions: (profile.exceptions ?? []).map((exception) => ({ ...exception })),
  };
}

export function renderNotificationProfiles({ profiles, busy, t }) {
  return `<ha-card outlined class="panel settings-card notification-profiles-card">
    <div class="notification-section-header">
      <div><h2>${esc(t("notifications.title"))}</h2><small>${esc(t("notifications.help"))}</small></div>
      <ha-button appearance="plain" data-action="new-notification-profile" ${busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("notifications.add"))}</ha-button>
    </div>
    <div class="notification-profile-list">
      ${profiles.length ? profiles.map((profile, index) => renderProfileRow(profile, index, busy, t)).join("") : `<div class="empty compact">${esc(t("notifications.empty"))}</div>`}
    </div>
  </ha-card>`;
}

function renderProfileRow(profile, index, busy, t) {
  const policy = profile.default_policy ?? {};
  const reminder = policy.reminder_interval === null
    ? t("notifications.never")
    : t("notifications.seconds", { count: policy.reminder_interval });
  return `<div class="notification-profile-row">
    <div class="notification-profile-summary">
      <div class="notification-profile-name"><strong>${esc(profile.name)}</strong><span class="notification-profile-status">${esc(t(profile.enabled ? "notifications.enabled" : "notifications.disabled"))}</span></div>
      <small>${esc(t("notifications.targets_summary", { count: profile.primary_targets.length, fallback: profile.fallback_targets.length }))}</small>
      <small>${esc(t("notifications.policy_summary", {
        start: policy.notify_on_start ? t("notifications.yes") : t("notifications.no"),
        resolved: policy.notify_on_resolved ? t("notifications.yes") : t("notifications.no"),
        reminder,
        exceptions: profile.exceptions.length,
      }))}</small>
    </div>
    <div class="actions notification-profile-actions">
      <ha-button appearance="plain" data-action="test-notification-profile" data-profile-id="${esc(profile.id)}" ${busy || !profile.enabled ? "disabled" : ""}>${esc(t("notifications.test"))}</ha-button>
      <ha-button appearance="plain" data-action="edit-notification-profile" data-index="${index}" ${busy ? "disabled" : ""}>${esc(t("rules.modify"))}</ha-button>
      <ha-button appearance="plain" variant="danger" data-action="delete-notification-profile" data-index="${index}" ${busy ? "disabled" : ""}>${esc(t("buttons.delete"))}</ha-button>
    </div>
  </div>`;
}

export function renderNotificationProfileDrawer({
  draft, packs, rules, busy, useBottomSheet, t,
}) {
  if (!draft) return "";
  const policy = draft.default_policy;
  const content = `<div class="fields configuration-drawer-fields notification-profile-fields">
    <div class="field full"><span class="field-label">${esc(t("notifications.name"))}</span><ha-input id="notification-profile-name" type="text" value="${esc(draft.name)}" required aria-label="${esc(t("notifications.name"))}"></ha-input></div>
    <div class="field full"><div class="switch-field-row"><span class="field-label">${esc(t("notifications.enabled"))}</span><ha-switch id="notification-profile-enabled" aria-label="${esc(t("notifications.enabled"))}" ${draft.enabled ? "checked" : ""}></ha-switch></div></div>
    <div class="field full"><span class="field-label">${esc(t("notifications.primary_targets"))}</span><ha-selector id="notification-primary-targets"></ha-selector><small>${esc(t("notifications.primary_targets_help"))}</small></div>
    <div class="field full"><span class="field-label">${esc(t("notifications.fallback_targets"))}</span><ha-selector id="notification-fallback-targets"></ha-selector><small>${esc(t("notifications.fallback_help"))}</small></div>
    <div class="field full"><span class="field-label">${esc(t("notifications.labels"))}</span><ha-selector id="notification-labels"></ha-selector><small>${esc(t("notifications.labels_help"))}</small></div>
  </div>
  <h3>${esc(t("notifications.defaults"))}</h3>
  <div class="notification-policy-grid">
    ${renderPolicySwitch("notification-start", t("notifications.on_start"), policy.notify_on_start)}
    ${renderPolicySwitch("notification-resolved", t("notifications.on_resolved"), policy.notify_on_resolved)}
    <div class="field"><span class="field-label">${esc(t("notifications.reminder"))}</span><ha-input id="notification-reminder" type="number" min="60" max="31536000" step="1" value="${esc(policy.reminder_interval ?? "")}" aria-label="${esc(t("notifications.reminder"))}"><span slot="end">${esc(t("units.seconds"))}</span></ha-input><small>${esc(t("notifications.reminder_help"))}</small></div>
  </div>
  <div class="notification-exceptions-header"><div><h3>${esc(t("notifications.exceptions"))}</h3><small>${esc(t("notifications.exceptions_help"))}</small></div><ha-button appearance="plain" data-action="add-notification-exception"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button></div>
  <div class="notification-exception-list">${draft.exceptions.length
    ? draft.exceptions.map((exception, index) => renderException(exception, index, packs, rules, t)).join("")
    : `<div class="empty compact">${esc(t("notifications.no_exceptions"))}</div>`}</div>`;
  return renderConfigurationDrawer({
    title: draft.name || t("notifications.new"),
    ariaLabel: t("notifications.close_aria"),
    content,
    saveAction: "save-notification-profile",
    saveLabel: t("buttons.save"),
    busy,
    useBottomSheet,
  });
}

function renderPolicySwitch(id, label, checked) {
  return `<div class="field"><div class="switch-field-row"><span class="field-label">${esc(label)}</span><ha-switch id="${id}" aria-label="${esc(label)}" ${checked ? "checked" : ""}></ha-switch></div></div>`;
}

function renderException(exception, index, packs, rules, t) {
  const type = exception.selector_type ?? "pack";
  const reminderMode = Object.hasOwn(exception, "reminder_interval")
    ? (exception.reminder_interval === null ? "never" : "custom")
    : "inherit";
  return `<ha-card outlined class="notification-exception" data-notification-exception="${index}">
    <div class="notification-exception-heading"><strong>${esc(t("notifications.exception_number", { count: index + 1 }))}</strong><ha-button appearance="plain" variant="danger" data-action="remove-notification-exception" data-index="${index}">${esc(t("buttons.delete"))}</ha-button></div>
    <div class="notification-exception-grid">
      <div class="field"><span class="field-label">${esc(t("notifications.selector_type"))}</span><ha-select id="notification-exception-type-${index}"></ha-select></div>
      <div class="field"><span class="field-label">${esc(t("notifications.selector"))}</span>${renderSelectorControl(type, exception.selector_id ?? "", index, packs, rules, t)}</div>
      ${renderOverrideSelect(`notification-exception-start-${index}`, t("notifications.on_start"), booleanOverrideValue(exception, "notify_on_start"))}
      ${renderOverrideSelect(`notification-exception-resolved-${index}`, t("notifications.on_resolved"), booleanOverrideValue(exception, "notify_on_resolved"))}
      <div class="field"><span class="field-label">${esc(t("notifications.reminder"))}</span><ha-select id="notification-exception-reminder-mode-${index}"></ha-select>${reminderMode === "custom" ? `<ha-input id="notification-exception-reminder-${index}" type="number" min="60" max="31536000" step="1" value="${esc(exception.reminder_interval)}" required aria-label="${esc(t("notifications.reminder"))}"><span slot="end">${esc(t("units.seconds"))}</span></ha-input>` : ""}</div>
    </div>
  </ha-card>`;
}

function renderSelectorControl(type, selectorId, index, packs, rules, t) {
  if (type === "label") {
    return `<ha-selector id="notification-exception-selector-${index}"></ha-selector>`;
  }
  const options = type === "rule"
    ? rules.map((rule) => ({ value: rule.id, label: rule.name }))
    : packs.map((pack) => ({
      value: pack.id,
      label: t(`packs.${pack.translation_key || pack.id}.name`),
    }));
  return `<ha-select id="notification-exception-selector-${index}" data-options="${esc(JSON.stringify(options))}" data-value="${esc(selectorId)}"></ha-select>`;
}

function renderOverrideSelect(id, label, value) {
  return `<div class="field"><span class="field-label">${esc(label)}</span><ha-select id="${id}" data-value="${esc(value)}"></ha-select></div>`;
}

function booleanOverrideValue(exception, key) {
  return Object.hasOwn(exception, key) ? String(exception[key]) : "inherit";
}

export function hydrateNotificationProfileControls(panel) {
  const draft = panel._notificationProfileDraft;
  if (!draft) return;
  const notifySelector = { entity: { multiple: true, filter: { domain: "notify" } } };
  panel._configureSelector(
    "notification-primary-targets",
    notifySelector,
    draft.primary_targets,
    (value) => { draft.primary_targets = panel._multipleSelectorValue(value, draft.primary_targets); },
  );
  panel._configureSelector(
    "notification-fallback-targets",
    notifySelector,
    draft.fallback_targets,
    (value) => { draft.fallback_targets = panel._multipleSelectorValue(value, draft.fallback_targets); },
  );
  panel._configureSelector(
    "notification-labels",
    { label: { multiple: true } },
    draft.label_ids,
    (value) => { draft.label_ids = panel._multipleSelectorValue(value, draft.label_ids); },
  );
  draft.exceptions.forEach((exception, index) => {
    panel._configureSelect(
      `notification-exception-type-${index}`,
      SELECTOR_TYPES.map((value) => ({
        value,
        label: panel._t(`notifications.selector_types.${value}`),
      })),
      exception.selector_type,
      (value) => {
        captureNotificationProfileDraft(panel);
        exception.selector_type = value;
        exception.selector_id = "";
        panel._render();
      },
    );
    if (exception.selector_type === "label") {
      panel._configureSelector(
        `notification-exception-selector-${index}`,
        { label: {} },
        exception.selector_id,
        (value) => { exception.selector_id = typeof value === "string" ? value : ""; },
      );
    } else {
      const element = panel.shadowRoot.querySelector(`#notification-exception-selector-${index}`);
      let options = [];
      try { options = JSON.parse(element?.dataset?.options ?? "[]"); } catch (_error) { options = []; }
      panel._configureSelect(
        `notification-exception-selector-${index}`,
        options,
        exception.selector_id,
        (value) => { exception.selector_id = value ?? ""; },
      );
    }
    for (const [suffix, key] of [["start", "notify_on_start"], ["resolved", "notify_on_resolved"]]) {
      panel._configureSelect(
        `notification-exception-${suffix}-${index}`,
        POLICY_BOOLEAN_OPTIONS.map((value) => ({
          value,
          label: panel._t(`notifications.override.${value}`),
        })),
        booleanOverrideValue(exception, key),
        (value) => setBooleanOverride(exception, key, value),
      );
    }
    const reminderMode = Object.hasOwn(exception, "reminder_interval")
      ? (exception.reminder_interval === null ? "never" : "custom")
      : "inherit";
    panel._configureSelect(
      `notification-exception-reminder-mode-${index}`,
      ["inherit", "never", "custom"].map((value) => ({
        value,
        label: panel._t(`notifications.reminder_modes.${value}`),
      })),
      reminderMode,
      (value) => {
        captureNotificationProfileDraft(panel);
        if (value === "inherit") delete exception.reminder_interval;
        else if (value === "never") exception.reminder_interval = null;
        else exception.reminder_interval = 300;
        panel._render();
      },
    );
  });
}

function setBooleanOverride(exception, key, value) {
  if (value === "inherit") delete exception[key];
  else exception[key] = value === "true";
}

export function captureNotificationProfileDraft(panel) {
  const draft = panel._notificationProfileDraft;
  if (!draft) return;
  draft.name = String(panel.shadowRoot.querySelector("#notification-profile-name")?.value ?? draft.name).trim();
  draft.enabled = Boolean(panel.shadowRoot.querySelector("#notification-profile-enabled")?.checked);
  draft.default_policy.notify_on_start = Boolean(panel.shadowRoot.querySelector("#notification-start")?.checked);
  draft.default_policy.notify_on_resolved = Boolean(panel.shadowRoot.querySelector("#notification-resolved")?.checked);
  const reminder = String(panel.shadowRoot.querySelector("#notification-reminder")?.value ?? "").trim();
  draft.default_policy.reminder_interval = reminder === "" ? null : Number(reminder);
  draft.exceptions.forEach((exception, index) => {
    if (!Object.hasOwn(exception, "reminder_interval") || exception.reminder_interval === null) return;
    const value = panel.shadowRoot.querySelector(`#notification-exception-reminder-${index}`)?.value;
    if (value !== undefined) exception.reminder_interval = Number(value);
  });
}

export function notificationProfileValidationError(draft, t) {
  if (!draft.name) return t("notifications.validation.name");
  if (!draft.primary_targets.length) return t("notifications.validation.primary");
  const targets = new Set(draft.primary_targets);
  if (draft.fallback_targets.some((target) => targets.has(target))) {
    return t("notifications.validation.duplicate_target");
  }
  const reminder = draft.default_policy.reminder_interval;
  if (reminder !== null && (!Number.isInteger(reminder) || reminder < 60)) {
    return t("notifications.validation.reminder");
  }
  for (const exception of draft.exceptions) {
    if (!exception.selector_id) return t("notifications.validation.selector");
    const fields = ["notify_on_start", "notify_on_resolved", "reminder_interval"];
    if (!fields.some((field) => Object.hasOwn(exception, field))) {
      return t("notifications.validation.override");
    }
    if (Object.hasOwn(exception, "reminder_interval")
      && exception.reminder_interval !== null
      && (!Number.isInteger(exception.reminder_interval) || exception.reminder_interval < 60)) {
      return t("notifications.validation.reminder");
    }
  }
  return null;
}
