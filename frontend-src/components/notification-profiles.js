import { durationFieldValue, renderDurationControl } from "./duration-field.js";
import { loadNativeBottomSheet, renderConfigurationDrawer, renderConfigurationRemove } from "./configuration-drawer.js";
import {
  MAX_DURATION_SECONDS,
  MDI_PLUS,
  MDI_DOTS_VERTICAL,
  MIN_NOTIFICATION_REMINDER_SECONDS,
} from "../utils/constants.js";
import { durationText } from "../utils/formatting.js";
import { esc } from "../utils/escaping.js";

const exceptionLabelIds = (exception) => exception.selector_ids
  ?? (exception.selector_id ? [exception.selector_id] : []);

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
    exceptions: (profile.exceptions ?? []).map((exception) => {
      const copy = { ...exception, selector_ids: [...exceptionLabelIds(exception)] };
      delete copy.selector_id;
      return copy;
    }),
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
    ${profiles.length ? `<small>${esc(t("notifications.usage_period"))}</small>` : ""}
  </ha-card>`;
}

function renderProfileRow(profile, usage, busy, t) {
  return `<div class="notification-profile-row">
    <div class="notification-profile-summary">
      <div class="notification-profile-name"><strong>${esc(profile.name)}</strong></div>
      <div class="notification-profile-meta"><span class="notification-profile-status">${esc(t(profile.enabled ? "notifications.enabled" : "notifications.disabled"))}</span><span aria-hidden="true">·</span><span class="notification-profile-usage" data-notification-profile-usage="${esc(profile.id)}">${esc(notificationUsageText(usage[profile.id] ?? 0, t))}</span></div>
    </div>
    <div class="actions notification-profile-actions">
      <ha-button type="button" appearance="plain" data-action="edit-notification-profile" data-profile-id="${esc(profile.id)}" ${busy ? "disabled" : ""}>${esc(t("rules.modify"))}</ha-button>
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
  draft, busy, useBottomSheet, validationError = null, mode = "visual", savedProfile = null, labels = [], expandedExceptions, t,
}) {
  if (!draft) return "";
  const policy = draft.default_policy;
  const content = mode === "yaml"
    ? `<section class="yaml-rule-section"><small>${esc(t("notifications.yaml_help"))}</small><ha-code-editor id="notification-yaml-editor" mode="yaml" aria-label="${esc(t("notifications.yaml_title"))}"></ha-code-editor></section>`
    : `<div class="fields configuration-drawer-fields notification-profile-fields">
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
      <div class="field notification-policy-reminder"><span class="field-label">${esc(t("notifications.reminder"))}</span>${renderDurationControl("notification-reminder", t("notifications.reminder"), policy.reminder_interval, MIN_NOTIFICATION_REMINDER_SECONDS, MAX_DURATION_SECONDS, { required: false })}<small>${esc(t("notifications.reminder_help"))}</small></div>
    </ha-card>
  </section>
  <section class="notification-profile-section">
  <div class="notification-exceptions-header"><div><h3>${esc(t("notifications.exceptions"))}</h3><small>${esc(t("notifications.exceptions_help"))}</small></div><ha-button type="button" appearance="plain" data-action="add-notification-exception"><ha-svg-icon slot="start" path="${MDI_PLUS}"></ha-svg-icon>${esc(t("buttons.add"))}</ha-button></div>
  <ha-sortable id="notification-exception-sortable" handle-selector=".notification-exception-reorder" draggable-selector=".notification-exception"><div class="notification-exception-list">${draft.exceptions.length
    ? draft.exceptions.map((exception, index) => renderException(exception, index, t, draft.default_policy, labels, expandedExceptions)).join("")
    : `<div class="empty compact">${esc(t("notifications.no_exceptions"))}</div>`}</div></ha-sortable>
  </section>`;
  return renderConfigurationDrawer({
    resizeLabel: t("rules.aria_resize"),
    title: draft.name || t("notifications.new"),
    ariaLabel: t("notifications.close_aria"),
    headerAction: `<div slot="actionItems" class="notification-profile-header-toggle"><ha-switch id="notification-profile-enabled" title="${esc(t(draft.enabled ? "notifications.enabled" : "notifications.disabled"))}" aria-label="${esc(t("notifications.enabled"))}" ${draft.enabled ? "checked" : ""}></ha-switch><ha-dropdown data-notification-editor-menu size="m" placement="bottom-end"><ha-icon-button slot="trigger" aria-label="${esc(t("rules.aria_menu"))}" title="${esc(t("rules.aria_menu"))}"><ha-svg-icon path="${MDI_DOTS_VERTICAL}"></ha-svg-icon></ha-icon-button><ha-dropdown-item value="switch-editor"><ha-icon slot="icon" icon="mdi:playlist-edit"></ha-icon>${esc(t(mode === "yaml" ? "rules.edit_visually" : "rules.edit_yaml"))}</ha-dropdown-item><ha-dropdown-item value="duplicate-notification-profile" ${busy ? "disabled" : ""}><ha-icon slot="icon" icon="mdi:plus-circle-multiple-outline"></ha-icon>${esc(t("notifications.duplicate"))}</ha-dropdown-item><ha-dropdown-item value="test-notification-profile" title="${esc(t("notifications.test_saved_help"))}" ${busy || !savedProfile?.enabled ? "disabled" : ""}><ha-icon slot="icon" icon="mdi:send-check-outline"></ha-icon>${esc(t("notifications.test"))}</ha-dropdown-item><ha-dropdown-item value="delete-notification-profile" variant="danger" ${busy || !savedProfile ? "disabled" : ""}><ha-icon slot="icon" icon="mdi:delete"></ha-icon>${esc(t("buttons.delete"))}</ha-dropdown-item></ha-dropdown></div>`,
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

function notificationExceptionTitle(exception, labels, t) {
  return exceptionLabelIds(exception).map((id) =>
    labels.find((label) => label.label_id === id)?.name || id,
  ).join(", ") || t("notifications.new_exception");
}

function notificationExceptionSummary(exception, defaults, t) {
  const policy = { ...defaults, ...exception };
  return t("notifications.exception_summary", {
    start: t(policy.notify_on_start ? "notifications.yes" : "notifications.no"),
    resolved: t(policy.notify_on_resolved ? "notifications.yes" : "notifications.no"),
    reminder: policy.reminder_interval == null ? t("notifications.never")
      : durationText.call({ _t: t }, policy.reminder_interval),
  });
}

function renderException(exception, index, t, defaults, labels, expandedExceptions) {
  const policy = { ...defaults, ...exception };
  return `<ha-card outlined class="notification-exception" data-notification-exception="${index}">
    <ha-expansion-panel left-chevron data-notification-expansion="${index}" header="${esc(notificationExceptionTitle(exception, labels, t))}" secondary="${esc(notificationExceptionSummary(exception, defaults, t))}" ${(expandedExceptions?.has(exception) ?? !exceptionLabelIds(exception).length) ? "expanded" : ""}>
    <div slot="icons" class="notification-exception-heading"><ha-icon-button class="notification-exception-reorder" data-index="${index}" aria-label="${esc(t("notifications.reorder_exception", { count: index + 1 }))}" title="${esc(t("notifications.reorder_help"))}"><ha-icon icon="mdi:reorder-horizontal"></ha-icon></ha-icon-button>${renderConfigurationRemove(t("buttons.delete"), "remove-notification-exception", { "data-index": index })}</div>
    <div class="notification-exception-grid">
      <div class="field full"><span class="field-label">${esc(t("notifications.selector"))}</span><ha-selector id="notification-exception-selector-${index}"></ha-selector><small>${esc(t("notifications.selector_help"))}</small></div>
      <div class="notification-policy-card full">
        <div class="notification-policy-switches">
          ${renderPolicySwitch(`notification-exception-start-${index}`, t("notifications.on_start"), policy.notify_on_start)}
          ${renderPolicySwitch(`notification-exception-resolved-${index}`, t("notifications.on_resolved"), policy.notify_on_resolved)}
        </div>
        <div class="field notification-policy-reminder"><span class="field-label">${esc(t("notifications.reminder"))}</span>${renderDurationControl(`notification-exception-reminder-${index}`, t("notifications.reminder"), policy.reminder_interval, MIN_NOTIFICATION_REMINDER_SECONDS, MAX_DURATION_SECONDS, { required: false })}<small>${esc(t("notifications.reminder_help"))}</small></div>
      </div>
    </div>
    </ha-expansion-panel>
  </ha-card>`;
}

export function hydrateNotificationProfileControls(panel) {
  const draft = panel._notificationProfileDraft;
  if (!draft) return;
  const menu = panel.shadowRoot?.querySelector("[data-notification-editor-menu]");
  if (menu && !menu.dataset.configured) {
    menu.addEventListener("wa-select", (event) => {
      event.stopPropagation();
      void handleNotificationProfileMenuSelection(panel, event);
    });
    menu.dataset.configured = "true";
  }
  if (panel._notificationEditorMode === "yaml") {
    const editor = panel.shadowRoot?.querySelector("#notification-yaml-editor");
    if (editor) {
      editor.hass = panel._hass;
      editor.value = panel._notificationYaml;
      editor.lineNumbers = true;
      if (!editor.dataset.configured) {
        editor.addEventListener("value-changed", (event) => {
          panel._notificationYaml = String(event.detail?.value ?? editor.value ?? "");
        });
        editor.dataset.configured = "true";
      }
    }
    const toggle = panel.shadowRoot?.querySelector("#notification-profile-enabled");
    if (toggle) toggle.onchange = async () => {
      if (panel._busy) return;
      const enabled = toggle.checked;
      if (await validateNotificationYaml(panel)) {
        panel._notificationProfileDraft.enabled = enabled;
        panel._notificationYaml = notificationProfileToYaml(panel._notificationProfileDraft);
      }
      panel._refreshSettingsConfigurationDrawer();
    };
    return;
  }
  hydrateNotificationExceptionSorting(panel);
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
    const expansion = panel.shadowRoot?.querySelector(`[data-notification-expansion="${index}"]`);
    if (expansion) {
      panel._notificationExpandedExceptions ??= new WeakSet();
      if (expansion.expanded || expansion.hasAttribute("expanded")) panel._notificationExpandedExceptions.add(exception);
      if (expansion._notificationExpansionHandler) expansion.removeEventListener("expanded-changed", expansion._notificationExpansionHandler);
      expansion._notificationExpansionHandler = (event) => {
        if (event.target !== expansion) return;
        if (event.detail.expanded) panel._notificationExpandedExceptions.add(exception);
        else {
          panel._notificationExpandedExceptions.delete(exception);
          captureNotificationProfileDraft(panel);
          expansion.header = notificationExceptionTitle(exception, panel._labels ?? [], (key) => panel._t(key));
          expansion.secondary = notificationExceptionSummary(exception, draft.default_policy, (key, replacements) => panel._t(key, replacements));
        }
      };
      expansion.addEventListener("expanded-changed", expansion._notificationExpansionHandler);
      // Prevent the header toggle while keeping delegated deletion and keyboard sorting.
      expansion.querySelectorAll(".notification-exception-heading ha-icon-button").forEach((button) => {
        button.onclick = (event) => event.preventDefault();
        if (button.dataset.action) button.onkeydown = (event) => event.stopPropagation();
      });
    }
    const selectorId = `notification-exception-selector-${index}`;
    panel._configureSelector(
      selectorId,
      { label: { multiple: true } },
      exceptionLabelIds(exception),
      (value) => {
        exception.selector_ids = panel._multipleSelectorValue(value);
        delete exception.selector_id;
      },
    );
  });
}

// The automation editor registers HA's sortable and bottom-sheet components.
function hydrateNotificationExceptionSorting(panel) {
  const sortable = panel.shadowRoot?.querySelector("#notification-exception-sortable");
  if (!sortable) return;
  if (!customElements.get("ha-sortable")) void loadNativeBottomSheet.call(panel, true);
  sortable.disabled = Boolean(panel._busy);
  sortable.onkeydown = (event) => {
    const handle = event.target.closest?.(".notification-exception-reorder");
    if (!handle || !["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const oldIndex = Number(handle.dataset.index);
    const newIndex = event.key === "Home" ? 0
      : event.key === "End" ? panel._notificationProfileDraft.exceptions.length - 1
      : oldIndex + (event.key === "ArrowUp" ? -1 : 1);
    moveNotificationException(panel, oldIndex, newIndex);
  };
  // Property callbacks keep repeated hydration idempotent.
  sortable._notificationItemMoved = (event) => {
    event.stopPropagation();
    const { oldIndex, newIndex } = event.detail;
    // Let HA finish its drag-end rollback before replacing the drawer content.
    queueMicrotask(() => {
      if (sortable.isConnected) moveNotificationException(panel, oldIndex, newIndex);
    });
  };
  if (!sortable._notificationSortingBound) {
    sortable.addEventListener("item-moved", (event) => sortable._notificationItemMoved(event));
    sortable._notificationSortingBound = true;
  }
}

export function moveNotificationException(panel, oldIndex, newIndex) {
  const exceptions = panel._notificationProfileDraft?.exceptions;
  if (panel._busy || !exceptions || !Number.isInteger(oldIndex)
    || !Number.isInteger(newIndex) || oldIndex < 0 || newIndex < 0
    || oldIndex >= exceptions.length || newIndex >= exceptions.length
    || oldIndex === newIndex) return;
  captureNotificationProfileDraft(panel);
  exceptions.splice(newIndex, 0, exceptions.splice(oldIndex, 1)[0]);
  panel._refreshSettingsConfigurationDrawer();
  panel.shadowRoot.querySelector(
    `.notification-exception-reorder[data-index="${newIndex}"]`,
  )?.focus();
}

export function captureNotificationProfileDraft(panel) {
  const draft = panel._notificationProfileDraft;
  if (!draft || !panel.shadowRoot.querySelector("#notification-profile-name")) return;
  draft.name = String(panel.shadowRoot.querySelector("#notification-profile-name")?.value ?? draft.name).trim();
  draft.enabled = Boolean(panel.shadowRoot.querySelector("#notification-profile-enabled")?.checked);
  draft.default_policy.notify_on_start = Boolean(panel.shadowRoot.querySelector("#notification-start")?.checked);
  draft.default_policy.notify_on_resolved = Boolean(panel.shadowRoot.querySelector("#notification-resolved")?.checked);
  const reminder = String(durationFieldValue(panel.shadowRoot.querySelector("#notification-reminder")) ?? "").trim();
  draft.default_policy.reminder_interval = reminder === "" ? null : Number(reminder);
  draft.exceptions.forEach((exception, index) => {
    for (const [suffix, key] of [["start", "notify_on_start"], ["resolved", "notify_on_resolved"]]) {
      const control = panel.shadowRoot.querySelector(`#notification-exception-${suffix}-${index}`);
      if (control) exception[key] = Boolean(control.checked);
    }
    const value = durationFieldValue(panel.shadowRoot.querySelector(`#notification-exception-reminder-${index}`));
    if (value !== undefined) exception.reminder_interval = value === "" ? null : Number(value);
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
    if (!exceptionLabelIds(exception).length) return t("notifications.validation.selector");
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
  setNotificationProfileDraft(panel,
    profile ? cloneNotificationProfile(profile) : newNotificationProfileDraft(),
    profile?.id ?? null,
  );
}

function setNotificationProfileDraft(panel, draft, profileId) {
  panel._notificationProfileDraft = draft;
  panel._notificationExpandedExceptions = undefined;
  panel._notificationEditorMode = "visual";
  panel._notificationYaml = "";
  panel._notificationYamlOriginal = "";
  panel._notificationProfileOriginal = JSON.stringify(draft);
  panel._notificationProfileId = profileId;
  panel._notificationProfileValidationError = null;
  panel._notice = null;
  panel._configurationDrawer = { kind: "notification" };
  panel._refreshSettingsConfigurationDrawer();
}

export async function handleNotificationProfileMenuSelection(panel, event) {
  if (panel._busy) return;
  const action = event.detail?.item?.value;
  if (action === "switch-editor") return switchNotificationEditor(panel);
  if (action === "test-notification-profile") {
    const saved = panel._settingsDraft.notification_profiles.find(
      (profile) => profile.id === panel._notificationProfileId,
    );
    if (!saved?.enabled) return;
  } else if (!["duplicate-notification-profile", "delete-notification-profile"].includes(action)) return;
  return handleNotificationProfileAction.call(panel, action, {
    dataset: { profileId: panel._notificationProfileId },
  });
}

function notificationCopyName(panel, sourceName) {
  const names = new Set(panel._settingsDraft.notification_profiles.map((profile) => profile.name));
  names.add(sourceName);
  for (let number = 1; ; number++) {
    const suffix = ` (${panel._t("notifications.copy")}${number === 1 ? "" : ` ${number}`})`;
    // Match the backend's 255-character limit, including Unicode code points.
    const name = Array.from(sourceName).slice(0, 255 - Array.from(suffix).length).join("") + suffix;
    if (!names.has(name)) return name;
  }
}

function confirmNotificationDiscard(panel) {
  captureNotificationProfileDraft(panel);
  return !panel._notificationProfileDraft
    || (JSON.stringify(panel._notificationProfileDraft) === panel._notificationProfileOriginal
      && (panel._notificationEditorMode !== "yaml"
        || panel._notificationYaml === panel._notificationYamlOriginal))
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
  if (action === "duplicate-notification-profile") {
    if (this._busy || !this._notificationProfileDraft) return true;
    if (this._notificationEditorMode === "yaml") {
      if (!await validateNotificationYaml(this)) {
        this._refreshSettingsConfigurationDrawer();
        return true;
      }
    } else captureNotificationProfileDraft(this);
    const copy = cloneNotificationProfile(this._notificationProfileDraft);
    copy.id = newNotificationProfileDraft().id;
    copy.name = notificationCopyName(this, copy.name);
    setNotificationProfileDraft(this, copy, null);
    // A newly duplicated configuration is unsaved even before another edit.
    this._notificationProfileOriginal = null;
    return true;
  }
  if (action === "save-notification-profile") {
    if (this._busy) return true;
    if (this._notificationEditorMode === "yaml" && !await validateNotificationYaml(this)) {
      this._refreshSettingsConfigurationDrawer();
      return true;
    }
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
      true,
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
      selector_ids: [],
      ...this._notificationProfileDraft.default_policy,
    });
    this._notificationExpandedExceptions ??= new WeakSet();
    this._notificationExpandedExceptions.add(this._notificationProfileDraft.exceptions.at(-1));
    this._refreshSettingsConfigurationDrawer(
      `[data-notification-exception="${this._notificationProfileDraft.exceptions.length - 1}"]`,
    );
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

export function notificationProfileToYaml(profile) {
  const { id, default_policy: policy, exceptions, ...fields } = cloneNotificationProfile(profile);
  const entry = ([key, value]) => `${key}: ${JSON.stringify(value)}`;
  return [
    ...Object.entries(fields).map(entry),
    "default_policy:",
    ...Object.entries(policy).map((item) => `  ${entry(item)}`),
    exceptions.length ? "exceptions:" : "exceptions: []",
    ...exceptions.flatMap((exception) => Object.entries(exception).map(
      (item, index) => `${index === 0 ? "  - " : "    "}${entry(item)}`,
    )),
    "",
  ].join("\n");
}

async function validateNotificationYaml(panel) {
  const draft = panel._notificationProfileDraft;
  const yaml = panel._notificationYaml;
  panel._busy = true;
  panel._refreshUiState();
  try {
    const validated = await panel._api.call({
      type: "alert_manager/notifications/yaml/validate",
      profile_id: draft.id,
      yaml,
    });
    if (panel._notificationProfileDraft !== draft || panel._notificationYaml !== yaml) return false;
    panel._notificationProfileDraft = cloneNotificationProfile(validated);
    panel._notificationProfileValidationError = null;
    return true;
  } catch (error) {
    if (panel._notificationProfileDraft !== draft || panel._notificationYaml !== yaml) return false;
    panel._notificationProfileValidationError = panel._errorText(error);
    return false;
  } finally {
    panel._busy = false;
    panel._refreshUiState();
  }
}

export async function switchNotificationEditor(panel) {
  if (panel._busy) return;
  if (panel._notificationEditorMode !== "yaml") {
    captureNotificationProfileDraft(panel);
    panel._notificationYaml = notificationProfileToYaml(panel._notificationProfileDraft);
    panel._notificationYamlOriginal = panel._notificationYaml;
    panel._notificationEditorMode = "yaml";
    panel._notificationProfileValidationError = null;
  } else if (await validateNotificationYaml(panel)) {
    panel._notificationEditorMode = "visual";
  }
  panel._refreshSettingsConfigurationDrawer();
}
