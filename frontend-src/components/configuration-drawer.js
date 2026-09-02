import { esc } from "../utils/escaping.js";

export function renderConfigurationDrawer({
  title,
  ariaLabel,
  content,
  saveAction,
  saveLabel,
  busy,
}) {
  return `<div class="side-drawer-backdrop configuration-drawer-backdrop" data-action="close-configuration-drawer" aria-hidden="true"></div>
    <ha-card outlined class="side-drawer configuration-drawer" role="dialog" aria-modal="false" aria-label="${esc(ariaLabel)}">
      <ha-dialog-header show-border>
        <ha-icon-button slot="navigationIcon" data-action="close-configuration-drawer" aria-label="${esc(ariaLabel)}"></ha-icon-button>
        <span slot="title">${esc(title)}</span>
      </ha-dialog-header>
      <div class="side-drawer-form">
        <section class="side-drawer-section">${content}</section>
        <div class="actions side-drawer-actions"><span class="action-spacer"></span><ha-button appearance="accent" variant="brand" data-action="${esc(saveAction)}" ${busy ? "disabled" : ""}>${esc(saveLabel)}</ha-button></div>
      </div>
    </ha-card>`;
}

export function replaceConfigurationDrawer(root, markup) {
  root?.querySelector?.(".configuration-drawer-backdrop")?.remove?.();
  root?.querySelector?.(".configuration-drawer")?.remove?.();
  if (root && markup) root.insertAdjacentHTML("beforeend", markup);
}
