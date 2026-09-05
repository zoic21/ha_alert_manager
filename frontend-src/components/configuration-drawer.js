import { esc } from "../utils/escaping.js";
import { MDI_CLOSE } from "../utils/constants.js";

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
export async function loadNativeBottomSheet() {
  if (!this._narrow || this._useNativeBottomSheet()) return true;
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
    if (await handler.call(panel, action, button, event)) return;
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

export function renderConfigurationDrawer({
  title,
  ariaLabel,
  headerAction = "",
  banner = "",
  content,
  saveAction,
  saveLabel,
  busy,
  useBottomSheet = false,
}) {
  const drawer = `<ha-card outlined class="side-drawer configuration-drawer" role="dialog" aria-modal="false" aria-label="${esc(ariaLabel)}">
      <ha-dialog-header show-border>
        <ha-icon-button slot="navigationIcon" path="${MDI_CLOSE}" data-action="close-configuration-drawer" aria-label="${esc(ariaLabel)}"></ha-icon-button>
        <span slot="title">${esc(title)}</span>
        ${headerAction}
      </ha-dialog-header>
      ${banner ? `<div class="configuration-drawer-banner">${banner}</div>` : ""}
      <div class="side-drawer-form">
        <section class="side-drawer-section">${content}</section>
        <div class="actions side-drawer-actions"><span class="action-spacer"></span><ha-button type="button" appearance="accent" variant="brand" data-action="${esc(saveAction)}" ${busy ? "disabled" : ""}>${esc(saveLabel)}</ha-button></div>
      </div>
    </ha-card>`;
  return renderSideDrawer({
    drawer,
    backdropClass: "configuration-drawer-backdrop",
    closeAction: "close-configuration-drawer",
    useBottomSheet,
  });
}

function restoreDrawerScroll(scroller, scrollTop) {
  if (!scroller) return;
  scroller.scrollTop = scrollTop;
  if (typeof globalThis.requestAnimationFrame !== "function") return;
  globalThis.requestAnimationFrame(() => {
    scroller.scrollTop = scrollTop;
    globalThis.requestAnimationFrame(() => { scroller.scrollTop = scrollTop; });
  });
}

export function replaceConfigurationDrawer(root, markup) {
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
      restoreDrawerScroll(nextScroller, scrollTop);
      return;
    }
  }
  currentBottomSheet?.remove?.();
  root?.querySelector?.(".configuration-drawer-backdrop")?.remove?.();
  root?.querySelector?.(".configuration-drawer")?.remove?.();
  if (root && markup) {
    root.insertAdjacentHTML("beforeend", markup);
    const nextScroller = root.querySelector?.(
      ".configuration-drawer .side-drawer-form",
    );
    restoreDrawerScroll(nextScroller, scrollTop);
  }
}
