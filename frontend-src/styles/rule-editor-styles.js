export const ruleEditorStyles = `
  /* Rule editor */
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }
  .rule-entities {
    display: flex;
    min-width: 0;
    flex-direction: column;
  }
  .rules-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
  }
  .rules-header > div {
    min-width: 0;
  }
  .rules-header ha-button {
    flex: none;
  }
  .rules-layout {
    --rule-editor-width: 560px;
    --rule-editor-inline-end: 24px;
    --rule-editor-content-gap: 16px;
  }
  .rules-layout [data-rules-table-page] {
    --alert-manager-rule-table-width: 100%;
  }
  .rules-layout.has-editor [data-rules-table-page] {
    --alert-manager-rule-table-width: calc(
      100% - var(--rule-editor-width) - var(--rule-editor-inline-end) - var(--rule-editor-content-gap)
    );
  }
  ha-card.rule-editor-drawer {
    position: fixed;
    z-index: 6;
    inset-block-start: calc(var(--header-height, 56px) + 16px);
    inset-block-end: 16px;
    inset-inline-end: var(--rule-editor-inline-end);
    width: var(--rule-editor-width);
    max-width: calc(100vw - 64px);
    display: flex;
    flex-direction: column;
    overflow: visible;
    border-color: var(--primary-color, #03a9f4);
    border-width: 2px;
    --ha-card-border-radius: var(--ha-dialog-border-radius, var(--ha-border-radius-2xl, 14px));
    border-radius: var(--ha-card-border-radius);
  }
  .rule-editor-drawer ha-dialog-header {
    flex: none;
    background: var(--ha-dialog-surface-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius);
    border-end-start-radius: 0;
    border-end-end-radius: 0;
  }
  .rule-editor-form {
    flex: 1;
    min-height: 0;
    overflow: auto;
    margin: 0;
    padding: 0;
    background: var(--primary-background-color, #fafafa);
    border-end-start-radius: var(--ha-card-border-radius);
    border-end-end-radius: var(--ha-card-border-radius);
  }
  .rule-editor-section {
    padding: 20px;
    background: var(--card-background-color, #fff);
    border-bottom: 1px solid var(--divider-color, #ddd);
  }
  .rule-section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }
  .rule-section-heading h3 {
    font-size: var(--ha-font-size-l, 16px);
    font-weight: var(--ha-font-weight-medium, 500);
    line-height: 1.4;
    margin: 0;
  }
  .rule-section-heading small {
    display: block;
    margin-top: 2px;
  }
  .rule-editor-form .full {
    margin-top: 0;
  }
  .rule-attribute-field[hidden] {
    display: none;
  }
  .rule-values-field {
    gap: 10px;
  }
  .rule-value-list {
    display: grid;
    gap: 10px;
  }
  .rule-value-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    align-items: start;
  }
  .rule-value-row ha-button {
    margin-top: 8px;
  }
  .rule-value-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .rule-value-footer small {
    margin: 0;
  }
  .yaml-rule-section {
    min-height: 0;
    display: flex;
    flex: 1;
    flex-direction: column;
  }
  .yaml-rule-section ha-code-editor {
    display: block;
    flex: 1;
    min-height: 360px;
    border: 1px solid var(--divider-color, #ddd);
    border-radius: var(--ha-border-radius-m, 8px);
    overflow: hidden;
  }
  .yaml-error {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: var(--ha-border-radius-m, 8px);
    background: color-mix(in srgb, var(--error-color, #db4437) 14%, transparent);
    color: var(--error-color, #db4437);
    overflow-wrap: anywhere;
  }
  .rule-editor-actions {
    position: sticky;
    bottom: 0;
    z-index: 1;
    align-items: center;
    justify-content: flex-start;
    flex-wrap: wrap;
    padding: 12px 20px max(12px, var(--safe-area-inset-bottom, 0px));
    background: var(--card-background-color, #fff);
    border-top: 1px solid var(--divider-color, #ddd);
    box-shadow: 0 -2px 8px rgba(0, 0, 0, .08);
  }
  .rule-editor-error {
    flex: 1 0 100%;
    width: 100%;
    margin: 0 0 4px;
  }
  .action-spacer {
    flex: 1;
  }
  .rule-editor-resize {
    position: absolute;
    inset-block: var(--ha-card-border-radius) var(--ha-card-border-radius);
    inset-inline-start: -12px;
    width: 24px;
    z-index: 7;
    cursor: ew-resize;
    display: flex;
    align-items: center;
    justify-content: center;
    touch-action: none;
  }
  .resize-indicator {
    height: 100%;
    width: 4px;
    border-radius: var(--ha-border-radius-pill, 999px);
    background: var(--primary-color, #03a9f4);
    opacity: 0;
    transform: scaleX(0);
    transition: opacity 180ms ease-in-out, transform 180ms ease-in-out;
  }
  .rule-editor-resize:hover .resize-indicator, .rule-editor-resize:focus-visible .resize-indicator, .rule-editor-resize.is-resizing .resize-indicator {
    opacity: 1;
    transform: scaleX(1);
  }
  .rule-editor-resize:focus-visible {
    outline: none;
  }
  .rule-editor-backdrop {
    display: none;
  }
  .delay-list {
    display: grid;
    gap: 10px;
    margin-top: 16px;
  }
  .delay-add-action {
    justify-content: flex-start;
    margin-top: 16px;
  }
  .delay-row {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) minmax(180px, 260px) auto;
    gap: 10px;
    align-items: start;
  }
  .delay-row ha-input {
    min-width: 0;
  }
  .delay-row > ha-button {
    margin-top: 8px;
  }
  .configuration-transfer {
    display: grid;
    gap: 16px;
  }
  .transfer-actions {
    justify-content: flex-start;
  }
`;
