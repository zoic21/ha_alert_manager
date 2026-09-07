import { esc } from "../utils/escaping.js";
import { MDI_CLOSE } from "../utils/constants.js";

export function confirmConfigurationDiscard(panel, value, original) {
  return original === undefined || JSON.stringify(value) === original
    || window.confirm(panel._t("settings.discard_confirm"));
}

export function renderConfigurationRemove(label, action, attributes = {}) {
  const attrs = Object.entries(attributes).map(([key, value]) => `${key}="${esc(value)}"`).join(" ");
  return `<ha-icon-button class="configuration-remove" data-action="${esc(action)}" ${attrs} aria-label="${esc(label)}" title="${esc(label)}"><ha-icon icon="mdi:delete-outline"></ha-icon></ha-icon-button>`;
}

export const SIDE_DRAWER_OPEN_ACTIONS = new Set([
  "new-rule",
  "open-automatic-configuration",
  "open-deleted-entities",
  "open-settings-configuration",
  "new-notification-profile",
  "edit-notification-profile",
]);

export const isCompanionApp = () => Boolean(
  window.externalAppV2
  || window.externalApp
  || window.webkit?.messageHandlers?.externalBus,
);

export function useNativeBottomSheet() {
  return Boolean(this._narrow && customElements.get("ha-resizable-bottom-sheet"));
}

// Home Assistant registers this native component in its lazy automation editor
// bundle. Load that same route instead of maintaining a local bottom-sheet copy.
export async function loadNativeBottomSheet(force = false) {
  if (!force && (!this._narrow || this._useNativeBottomSheet())) return true;
  if (this._nativeBottomSheetLoadPromise) return this._nativeBottomSheetLoadPromise;
  this._nativeBottomSheetLoadPromise = (async () => {
    const homeAssistant = document.querySelector?.("home-assistant");
    const main = homeAssistant?.shadowRoot?.querySelector?.("home-assistant-main");
    const resolver = main?.shadowRoot?.querySelector?.("partial-panel-resolver");
    const configPath = Object.values(this._hass?.panels ?? {})
      .find((panel) => panel.component_name === "config")?.url_path;
    const loadConfig = configPath
      ? resolver?.routerOptions?.routes?.[configPath]?.load
      : undefined;
    if (typeof loadConfig === "function") await loadConfig();
    if (!customElements.get("ha-panel-config")) return false;
    const configPanel = document.createElement("ha-panel-config");
    const loadAutomation = configPanel.routerOptions?.routes?.automation?.load;
    if (typeof loadAutomation === "function") await loadAutomation();
    return Boolean(customElements.get("ha-resizable-bottom-sheet"));
  })().catch(() => false);
  return this._nativeBottomSheetLoadPromise;
}

export function updateDrawerLayout(previousNarrow) {
  if (
    Boolean(previousNarrow) === this._narrow
    || !this.isConnected
    || (this._editingRule === null && !this._configurationDrawer)
  ) return;
  if (this._editingRule !== null) this._captureRuleDraft();
  if (this._activeTab === "settings" || this._configurationDrawer?.kind === "automatic") this._captureAutomaticConfigurationValues();
  if (this._activeTab === "settings") {
    this._captureEntityDelayValues();
    this._captureNotificationProfileDraft();
  }
  if (!this._narrow) {
    this._render();
    return;
  }
  void this._loadNativeBottomSheet().then((loaded) => {
    if (loaded && this.isConnected && this._narrow) this._render();
  });
}

export async function handleBottomSheetClosed(panel, actionHandlers, event) {
  const action = event.target?.dataset?.closeAction;
  if (!action) return;
  const button = { dataset: { action } };
  for (const handler of actionHandlers) {
    if (await handler.call(panel, action, button, event)) {
      // A native swipe already closed the sheet; remount it if discard was refused.
      if (action === "close-configuration-drawer" && panel._configurationDrawer) panel._render();
      return;
    }
  }
}

export function renderSideDrawer({
  drawer,
  backdropClass,
  closeAction,
  useBottomSheet = false,
}) {
  if (useBottomSheet) {
    return `<ha-resizable-bottom-sheet class="side-drawer-bottom-sheet" data-close-action="${esc(closeAction)}">
      ${drawer}
    </ha-resizable-bottom-sheet>`;
  }
  return `<div class="side-drawer-backdrop ${esc(backdropClass)}" data-action="${esc(closeAction)}" aria-hidden="true"></div>
    ${drawer}`;
}

export function renderDrawerResizeHandle(label) {
  return `<div class="rule-editor-resize" role="separator" aria-orientation="vertical" aria-label="${esc(label)}" tabindex="0"><div class="resize-indicator"></div></div>`;
}

export function renderConfigurationDrawer({
  title,
  ariaLabel,
  resizeLabel,
  headerAction = "",
  banner = "",
  content,
  saveAction,
  saveLabel,
  busy,
  useBottomSheet = false,
}) {
  const drawer = `<ha-card outlined class="side-drawer configuration-drawer" role="dialog" aria-modal="false" aria-label="${esc(ariaLabel)}">
      ${renderDrawerResizeHandle(resizeLabel)}
      <ha-dialog-header show-border>
        <ha-icon-button slot="navigationIcon" path="${MDI_CLOSE}" data-action="close-configuration-drawer" aria-label="${esc(ariaLabel)}"></ha-icon-button>
        <span slot="title">${esc(title)}</span>
        ${headerAction}
      </ha-dialog-header>
      ${banner ? `<div class="configuration-drawer-banner">${banner}</div>` : ""}
      <div class="side-drawer-form">
        <section class="side-drawer-section"><div data-active-notice></div>${content}</section>
      </div>
      <div class="actions side-drawer-actions"><span class="action-spacer"></span><ha-button type="button" appearance="accent" variant="brand" data-action="${esc(saveAction)}" ${busy ? "disabled" : ""}>${esc(saveLabel)}</ha-button></div>
    </ha-card>`;
  return renderSideDrawer({
    drawer,
    backdropClass: "configuration-drawer-backdrop",
    closeAction: "close-configuration-drawer",
    useBottomSheet,
  });
}

export function revealAddedRow(root, selector) {
  if (!selector) return;
  const row = root?.querySelector?.(selector);
  if (!row) return;
  const reveal = () => {
    if (row.isConnected !== false) row.scrollIntoView?.({ block: "nearest" });
  };
  if (typeof globalThis.requestAnimationFrame === "function") {
    globalThis.requestAnimationFrame(reveal);
  } else reveal();
}

function restoreDrawerScroll(scroller, scrollTop, revealSelector) {
  if (!scroller) return;
  scroller.scrollTop = scrollTop;
  if (typeof globalThis.requestAnimationFrame !== "function") {
    revealAddedRow(scroller, revealSelector);
    return;
  }
  globalThis.requestAnimationFrame(() => {
    scroller.scrollTop = scrollTop;
    globalThis.requestAnimationFrame(() => {
      scroller.scrollTop = scrollTop;
      revealAddedRow(scroller, revealSelector);
    });
  });
}

export function mountConfigurationDrawer(root) {
  // Like the rule editor, drawers must sit outside hass-tabs-subpage's
  // scrolling content and stacking context, above its mobile navigation.
  const drawer = root?.querySelector?.(".configuration-drawer");
  if (!drawer) return;
  const sheet = drawer.closest?.(".side-drawer-bottom-sheet");
  const backdrop = root.querySelector?.(".configuration-drawer-backdrop");
  if (backdrop && backdrop.parentNode !== root) root.append(backdrop);
  const overlay = sheet ?? drawer;
  if (overlay.parentNode !== root) root.append(overlay);
}

export function replaceConfigurationDrawer(root, markup, revealSelector) {
  root?.querySelector?.(".settings-page")?.classList?.toggle("has-editor", Boolean(markup));
  const currentBottomSheet = root?.querySelector?.(".side-drawer-bottom-sheet");
  const currentDrawer = currentBottomSheet?.querySelector?.(".configuration-drawer")
    ?? root?.querySelector?.(".configuration-drawer");
  const scrollTop = currentDrawer?.querySelector?.(".side-drawer-form")?.scrollTop ?? 0;
  if (currentBottomSheet && markup) {
    const template = document.createElement("template");
    template.innerHTML = markup.trim();
    const nextBottomSheet = template.content.querySelector(
      ".side-drawer-bottom-sheet",
    );
    const nextDrawer = nextBottomSheet?.querySelector(
      ".configuration-drawer",
    );
    if (currentDrawer && nextDrawer) {
      currentDrawer.replaceWith(nextDrawer);
      const nextScroller = nextDrawer.querySelector?.(".side-drawer-form");
      restoreDrawerScroll(nextScroller, scrollTop, revealSelector);
      return;
    }
  }
  currentBottomSheet?.remove?.();
  root?.querySelector?.(".configuration-drawer-backdrop")?.remove?.();
  root?.querySelector?.(".configuration-drawer")?.remove?.();
  if (root && markup) {
    const template = document.createElement("template");
    template.innerHTML = markup;
    root.append(template.content);
    const nextScroller = root.querySelector?.(
      ".configuration-drawer .side-drawer-form",
    );
    restoreDrawerScroll(nextScroller, scrollTop, revealSelector);
  }
}

export function activeNoticeTarget() {
  return this._timedAcknowledgementDialog || this._alertDetailsDialog
    || this._backupRestoreCandidate || this._configurationDrawer;
}

export function refreshActiveNotice() {
  const target = this._noticeTarget();
  const root = this._timedAcknowledgementDialog || this._alertDetailsDialog
    || (this._backupRestoreCandidate
      ? this.shadowRoot?.querySelector?.("#config-backup-restore-dialog")
      : this.shadowRoot?.querySelector?.(".configuration-drawer"));
  const container = root?.querySelector?.("[data-active-notice]");
  if (container) {
    const notice = target?.notice;
    container.innerHTML = notice
      ? `<ha-alert class="alert-details-notice" data-alert-details-notice alert-type="${esc(notice.kind)}" role="${notice.kind === "error" ? "alert" : "status"}">${esc(notice.text)}</ha-alert>` : "";
  }
}
