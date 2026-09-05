import { renderConfigurationDrawer } from "./configuration-drawer.js";
import {
  DEFAULT_NOTIFICATION_REMINDER_SECONDS,
  MAX_DURATION_SECONDS,
  MDI_PLUS,
  MIN_NOTIFICATION_REMINDER_SECONDS,
} from "../utils/constants.js";
import { esc } from "../utils/escaping.js";

const POLICY_BOOLEAN_OPTIONS = ["inherit", "true", "false"];

export function newNotificationProfileDraft() {
  const generatedId = globalThis.crypto?.randomUUID?.()
    ?? `profile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return {
    id: generatedId,
    name: "",
    enabled: true,
    targets: [],
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
    id: profile.id,
    name: profile.name,
    enabled: profile.enabled,
    targets: [...(profile.targets ?? [])],
    label_ids: [...(profile.label_ids ?? [])],
    default_policy: { ...(profile.default_policy ?? {}) },
    exceptions: (profile.exceptions ?? []).map((exception) => ({ ...exception })),
  };
}

export function renderNotificationProfiles({ profiles, usage = {}, busy, t, batchDelayField = "" }) {
  return `<ha-card id="settings-section-notifications" outlined class="panel settings-card notification-profiles-card settings-scroll-section">
    <div class="notification-section-header">
      <div><h2>${esc(t("notifications.title"))}</h2><small>${esc(t("notifications.help"))}</small></div>
      <ha-button type="button" appearance="plain" data-action="new-notification-profile" ${busy ? "disabled" : ""}><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("notifications.add"))}</ha-button>
    </div>
    <div class="settings-grid">${batchDelayField}</div>
    <div class="notification-profile-list">
      ${profiles.length ? profiles.map((profile) => renderProfileRow(profile, usage, busy, t)).join("") : `<div class="empty compact">${esc(t("notifications.empty"))}</div>`}
    </div>
  </ha-card>`;
}

function renderProfileRow(profile, usage, busy, t) {
  return `<div class="notification-profile-row">
    <div class="notification-profile-summary">
      <div class="notification-profile-name"><strong>${esc(profile.name)}</strong></div>
      <div class="notification-profile-meta"><span class="notification-profile-status">${esc(t(profile.enabled ? "notifications.enabled" : "notifications.disabled"))}</span><span aria-hidden="true">·</span><span class="notification-profile-usage" data-notification-profile-usage="${esc(profile.id)}">${esc(notificationUsageText(usage[profile.id] ?? 0, t))}</span></div>
    </div>
    <div class="actions notification-profile-actions">
      <ha-button type="button" appearance="plain" data-action="test-notification-profile" data-profile-id="${esc(profile.id)}" ${busy || !profile.enabled ? "disabled" : ""}>${esc(t("notifications.test"))}</ha-button>
      <ha-button type="button" appearance="plain" data-action="edit-notification-profile" data-profile-id="${esc(profile.id)}" ${busy ? "disabled" : ""}>${esc(t("rules.modify"))}</ha-button>
      <ha-button type="button" appearance="plain" variant="danger" data-action="delete-notification-profile" data-profile-id="${esc(profile.id)}" ${busy ? "disabled" : ""}>${esc(t("buttons.delete"))}</ha-button>
    </div>
  </div>`;
}

function notificationUsageText(value, t) {
  const count = Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
  const key = count === 1
    ? "notifications.usage_last_24h_one"
    : "notifications.usage_last_24h";
  return t(key, { count });
}

export function updateNotificationProfileUsage(root, usage, t) {
  root?.querySelectorAll?.("[data-notification-profile-usage]").forEach((element) => {
    element.textContent = notificationUsageText(
      usage[element.dataset.notificationProfileUsage] ?? 0,
      t,
    );
  });
}

export function renderNotificationProfileDrawer({
  draft, busy, useBottomSheet, validationError = null, t,
}) {
  if (!draft) return "";
  const policy = draft.default_policy;
  const content = `<div class="fields configuration-drawer-fields notification-profile-fields">
    <div class="field full"><span class="field-label">${esc(t("notifications.name"))}</span><ha-input id="notification-profile-name" type="text" value="${esc(draft.name)}" required aria-label="${esc(t("notifications.name"))}"></ha-input></div>
    <div class="field full"><span class="field-label">${esc(t("notifications.targets"))}</span><ha-selector id="notification-targets"></ha-selector><small>${esc(t("notifications.targets_help"))}</small></div>
    <div class="field full"><span class="field-label">${esc(t("notifications.labels"))}</span><ha-selector id="notification-labels"></ha-selector><small>${esc(t("notifications.labels_help"))}</small></div>
  </div>
  <section class="notification-profile-section notification-policy-section">
    <h3>${esc(t("notifications.defaults"))}</h3>
    <ha-card outlined class="notification-policy-card">
      <div class="notification-policy-switches">
        ${renderPolicySwitch("notification-start", t("notifications.on_start"), policy.notify_on_start)}
        ${renderPolicySwitch("notification-resolved", t("notifications.on_resolved"), policy.notify_on_resolved)}
      </div>
      <div class="field notification-policy-reminder"><span class="field-label">${esc(t("notifications.reminder"))}</span><ha-input id="notification-reminder" type="number" min="${MIN_NOTIFICATION_REMINDER_SECONDS}" max="${MAX_DURATION_SECONDS}" step="1" value="${esc(policy.reminder_interval ?? "")}" aria-label="${esc(t("notifications.reminder"))}"><span slot="end">${esc(t("units.seconds"))}</span></ha-input><small>${esc(t("notifications.reminder_help"))}</small></div>
    </ha-card>
  </section>
  <section class="notification-profile-section">
  <div class="notification-exceptions-header"><div><h3>${esc(t("notifications.exceptions"))}</h3><small>${esc(t("notifications.exceptions_help"))}</small></div><ha-button type="button" appearance="plain" data-action="add-notification-exception"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button></div>
  <div class="notification-exception-list">${draft.exceptions.length
    ? draft.exceptions.map((exception, index) => renderException(exception, index, t)).join("")
    : `<div class="empty compact">${esc(t("notifications.no_exceptions"))}</div>`}</div>
  </section>`;
  return renderConfigurationDrawer({
    title: draft.name || t("notifications.new"),
    ariaLabel: t("notifications.close_aria"),
    headerAction: `<div slot="actionItems" class="notification-profile-header-toggle"><span>${esc(t("notifications.enabled"))}</span><ha-switch id="notification-profile-enabled" aria-label="${esc(t("notifications.enabled"))}" ${draft.enabled ? "checked" : ""}></ha-switch></div>`,
    banner: validationError
      ? `<ha-alert class="notification-profile-error" alert-type="error">${esc(validationError)}</ha-alert>`
      : "",
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

function renderException(exception, index, t) {
  const reminderMode = Object.hasOwn(exception, "reminder_interval")
    ? (exception.reminder_interval === null ? "never" : "custom")
    : "inherit";
  return `<ha-card outlined class="notification-exception" data-notification-exception="${index}">
    <div class="notification-exception-heading"><strong>${esc(t("notifications.exception_number", { count: index + 1 }))}</strong><ha-button type="button" appearance="plain" variant="danger" data-action="remove-notification-exception" data-index="${index}">${esc(t("buttons.delete"))}</ha-button></div>
    <div class="notification-exception-grid">
      <div class="field"><span class="field-label">${esc(t("notifications.selector"))}</span><ha-selector id="notification-exception-selector-${index}"></ha-selector></div>
      ${renderOverrideSelect(`notification-exception-start-${index}`, t("notifications.on_start"), booleanOverrideValue(exception, "notify_on_start"))}
      ${renderOverrideSelect(`notification-exception-resolved-${index}`, t("notifications.on_resolved"), booleanOverrideValue(exception, "notify_on_resolved"))}
      <div class="field notification-exception-reminder ${reminderMode === "custom" ? "has-custom-value" : ""}"><span class="field-label">${esc(t("notifications.reminder"))}</span><div class="notification-exception-reminder-controls"><ha-select id="notification-exception-reminder-mode-${index}"></ha-select>${reminderMode === "custom" ? `<ha-input id="notification-exception-reminder-${index}" type="number" min="${MIN_NOTIFICATION_REMINDER_SECONDS}" max="${MAX_DURATION_SECONDS}" step="1" value="${esc(exception.reminder_interval)}" required aria-label="${esc(t("notifications.reminder"))}"><span slot="end">${esc(t("units.seconds"))}</span></ha-input>` : ""}</div></div>
    </div>
  </ha-card>`;
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
    "notification-targets",
    notifySelector,
    draft.targets,
    (value) => { draft.targets = panel._multipleSelectorValue(value, draft.targets); },
  );
  panel._configureSelector(
    "notification-labels",
    { label: { multiple: true } },
    draft.label_ids,
    (value) => { draft.label_ids = panel._multipleSelectorValue(value, draft.label_ids); },
  );
  draft.exceptions.forEach((exception, index) => {
    panel._configureSelector(
      `notification-exception-selector-${index}`,
      { label: {} },
      exception.selector_id,
      (value) => { exception.selector_id = typeof value === "string" ? value : ""; },
    );
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
        else exception.reminder_interval = DEFAULT_NOTIFICATION_REMINDER_SECONDS;
        panel._refreshSettingsConfigurationDrawer();
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
  if (!draft || !panel.shadowRoot.querySelector("#notification-profile-name")) return;
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
  if (!draft.targets.length) return t("notifications.validation.targets");
  const reminder = draft.default_policy.reminder_interval;
  if (invalidReminder(reminder)) {
    return t("notifications.validation.reminder");
  }
  for (const exception of draft.exceptions) {
    if (!exception.selector_id) return t("notifications.validation.selector");
    const fields = ["notify_on_start", "notify_on_resolved", "reminder_interval"];
    if (!fields.some((field) => Object.hasOwn(exception, field))) {
      return t("notifications.validation.override");
    }
    if (Object.hasOwn(exception, "reminder_interval")
      && invalidReminder(exception.reminder_interval)) {
      return t("notifications.validation.reminder");
    }
  }
  return null;
}

function invalidReminder(value) {
  return value !== null && (
    !Number.isInteger(value) || value < MIN_NOTIFICATION_REMINDER_SECONDS
  );
}

async function saveNotificationProfiles(panel, candidateProfiles, savedDraft = false) {
  const profiles = candidateProfiles.map(cloneNotificationProfile);
  panel._busy = true;
  panel._notice = null;
  panel._refreshUiState();
  let saved = false;
  try {
    panel._config = await panel._api.call({
      type: "alert_manager/config/update",
      config: { notification_profiles: profiles },
    });
    panel._settingsDraft.notification_profiles = (
      panel._config.notification_profiles ?? []
    ).map(cloneNotificationProfile);
    if (savedDraft) {
      panel._notificationProfileDraft = null;
      panel._notificationProfileId = null;
      panel._notificationProfileOriginal = null;
    }
    panel._configurationDrawer = null;
    panel._notice = { kind: "success", text: panel._t("success.settings_saved") };
    saved = true;
  } catch (error) {
    panel._notice = null;
    panel._notificationProfileValidationError = panel._errorText(error);
  } finally {
    panel._busy = false;
    if (saved) panel._render();
    else panel._refreshSettingsConfigurationDrawer();
  }
}

function openNotificationProfile(panel, profile = null) {
  if (panel._notificationProfileDraft
    && panel._notificationProfileId === (profile?.id ?? null)) {
    panel._configurationDrawer = { kind: "notification" };
    panel._refreshSettingsConfigurationDrawer();
    return;
  }
  if (!confirmNotificationDiscard(panel)) return;
  panel._notificationProfileDraft = profile
    ? cloneNotificationProfile(profile)
    : newNotificationProfileDraft();
  panel._notificationProfileOriginal = JSON.stringify(panel._notificationProfileDraft);
  panel._notificationProfileId = profile?.id ?? null;
  panel._notificationProfileValidationError = null;
  panel._configurationDrawer = { kind: "notification" };
  panel._refreshSettingsConfigurationDrawer();
}

function confirmNotificationDiscard(panel) {
  captureNotificationProfileDraft(panel);
  return !panel._notificationProfileDraft
    || JSON.stringify(panel._notificationProfileDraft) === panel._notificationProfileOriginal
    || window.confirm(panel._t("notifications.discard_confirm"));
}

export async function handleNotificationProfileAction(action, button) {
  if (action === "new-notification-profile") {
    this._ensureSettingsDraft();
    openNotificationProfile(this);
    return true;
  }
  if (action === "edit-notification-profile") {
    this._ensureSettingsDraft();
    const profile = this._settingsDraft.notification_profiles.find(
      (item) => item.id === button.dataset.profileId,
    );
    if (profile) openNotificationProfile(this, profile);
    return true;
  }
  if (action === "save-notification-profile") {
    captureNotificationProfileDraft(this);
    const error = notificationProfileValidationError(
      this._notificationProfileDraft,
      (key) => this._t(key),
    );
    if (error) {
      this._notificationProfileValidationError = error;
      this._refreshSettingsConfigurationDrawer();
      return true;
    }
    this._notificationProfileValidationError = null;
    const profile = cloneNotificationProfile(this._notificationProfileDraft);
    const profiles = (this._settingsDraft.notification_profiles ?? []).map(
      cloneNotificationProfile,
    );
    const index = profiles.findIndex((item) => item.id === this._notificationProfileId);
    if (index < 0) profiles.push(profile);
    else profiles[index] = profile;
    await saveNotificationProfiles(this, profiles, true);
    return true;
  }
  if (action === "delete-notification-profile") {
    this._ensureSettingsDraft();
    const profile = this._settingsDraft.notification_profiles.find(
      (item) => item.id === button.dataset.profileId,
    );
    if (!profile || !window.confirm(
      this._t("notifications.delete_confirm", { name: profile.name }),
    )) return true;
    await saveNotificationProfiles(
      this,
      this._settingsDraft.notification_profiles.filter(
        (item) => item.id !== profile.id,
      ),
    );
    return true;
  }
  if (action === "test-notification-profile") {
    const result = await this._call({
      type: "alert_manager/notifications/test",
      profile_id: button.dataset.profileId,
    }, "");
    if (!result) return true;
    const failed = (result.failed_targets ?? []).map(
      (item) => item.entity_id,
    ).join(", ");
    this._notice = result.success
      ? { kind: "success", text: this._t("notifications.test_success") }
      : {
        kind: "error",
        text: this._t("notifications.test_failed", { targets: failed }),
      };
    this._refreshUiState();
    return true;
  }
  if (action === "add-notification-exception") {
    captureNotificationProfileDraft(this);
    this._notificationProfileDraft.exceptions.push({
      selector_type: "label",
      selector_id: "",
    });
    this._refreshSettingsConfigurationDrawer();
    return true;
  }
  if (action === "remove-notification-exception") {
    captureNotificationProfileDraft(this);
    this._notificationProfileDraft.exceptions.splice(Number(button.dataset.index), 1);
    this._refreshSettingsConfigurationDrawer();
    return true;
  }
  if (
    action === "close-configuration-drawer"
    && this._configurationDrawer?.kind === "notification"
  ) {
    if (!confirmNotificationDiscard(this)) return true;
    this._configurationDrawer = null;
    this._notificationProfileDraft = null;
    this._notificationProfileId = null;
    this._notificationProfileValidationError = null;
    this._refreshSettingsConfigurationDrawer();
    return true;
  }
  return false;
}
