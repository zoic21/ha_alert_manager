export const tableStyles = `
  /* Tables and filters */
  hass-tabs-subpage-data-table {
    display: block;
    width: 100%;
    height: 100%;
    --data-table-row-height: 60px;
  }
  .table-page-top {
    display: flow-root;
  }
  .table-page-top {
    box-sizing: border-box;
    width: 100%;
    padding: 24px 24px 0;
    background: var(--primary-background-color, #fafafa);
  }
  .table-page-top .summary {
    margin-bottom: 20px;
  }
  .filter-pane-content {
    display: flex;
    min-height: 0;
    flex-direction: column;
  }
  .filter-pane-content > ha-expansion-panel {
    display: block;
    border-bottom: 1px solid var(--divider-color, #ddd);
  }
  .filter-section-header {
    display: flex;
    min-width: 0;
    align-items: center;
    width: 100%;
  }
  .filter-section-header > span:first-child {
    min-width: 0;
  }
  .filter-section-header ha-icon-button {
    margin-inline-start: auto;
    margin-inline-end: 8px;
  }
  .filter-badge {
    display: inline-block;
    margin-inline-start: 8px;
    min-width: 16px;
    box-sizing: border-box;
    border-radius: var(--ha-border-radius-circle, 50%);
    font-size: var(--ha-font-size-xs, 11px);
    background: var(--primary-color, #03a9f4);
    line-height: var(--ha-line-height-normal, 1.4);
    text-align: center;
    padding: 0 2px;
    color: var(--text-primary-color, #fff);
  }
  .facet-filter-options {
    display: flex;
    max-height: 280px;
    flex-direction: column;
    overflow: auto;
    padding: 4px 0 8px;
  }
  .filter-option {
    display: flex;
    min-height: 48px;
    align-items: center;
    gap: 16px;
    padding: 0 16px;
    cursor: pointer;
    color: var(--primary-text-color, #212121);
  }
  .filter-option:hover {
    background: var(--ha-color-fill-neutral-quiet-hover, var(--secondary-background-color, #f5f5f5));
  }
  .filter-option ha-checkbox {
    flex: none;
  }
  .filter-empty {
    padding: 12px 16px;
    color: var(--secondary-text-color, #727272);
  }
  .date-filter-fields {
    display: grid;
    gap: 12px;
    padding: 4px 16px 16px;
  }
  .date-filter-fields ha-date-range-picker {
    display: block;
    width: 100%;
  }
  .selection-actions {
    display: flex;
    align-items: center;
    gap: var(--ha-space-2, 8px);
  }
  .selection-actions ha-button[variant="danger"] {
    color: var(--error-color, #db4437);
  }
  .table-cell-link {
    color: var(--primary-color, #03a9f4);
    cursor: pointer;
    text-decoration: none;
  }
  .table-cell-link:hover, .table-cell-link:focus-visible {
    text-decoration: underline;
  }
  .table-cell-link:focus-visible {
    border-radius: var(--ha-border-radius-sm, 4px);
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: 2px;
  }
  ha-adaptive-dialog.alert-details-dialog {
    --ha-dialog-width-md: 580px;
    --ha-dialog-max-width: calc(100vw - 24px);
    --ha-bottom-sheet-height: calc(100dvh - max(var(--safe-area-inset-top), 48px));
    --ha-bottom-sheet-max-height: var(--ha-bottom-sheet-height);
  }
  .timed-acknowledgement-dialog {
    --ha-dialog-width-sm: 420px;
    --ha-bottom-sheet-height: auto;
    --ha-bottom-sheet-max-height: calc(100dvh - 48px);
  }
  .timed-acknowledgement-fields {
    display: grid;
    gap: var(--ha-space-4, 16px);
  }
  .timed-acknowledgement-custom {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--ha-space-4, 16px);
    align-items: start;
  }
  .timed-acknowledgement-fields [hidden] {
    display: none;
  }
  .timed-acknowledgement-fields ha-select,
  .timed-acknowledgement-fields ha-selector {
    min-width: 0;
    width: 100%;
  }
  .timed-acknowledgement-footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--ha-space-2, 8px);
  }
  .alert-details-notice {
    flex: none;
    margin-bottom: var(--ha-space-4, 16px);
  }
  .alert-details-summary {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    gap: var(--ha-space-3, 12px);
    margin-bottom: var(--ha-space-4, 16px);
    padding: 8px var(--ha-space-4, 16px);
    border-radius: var(--ha-border-radius-lg, 12px);
    background: color-mix(in srgb, var(--error-color, #db4437) 10%, var(--card-background-color, #fff));
    color: var(--error-color, #db4437);
  }
  .alert-details-status-pending {
    background: color-mix(in srgb, var(--warning-color, #f5a623) 12%, var(--card-background-color, #fff));
    color: var(--warning-color, #9a6b00);
  }
  .alert-details-status-acknowledged {
    background: color-mix(in srgb, var(--blue-color, var(--primary-color, #03a9f4)) 10%, var(--card-background-color, #fff));
    color: var(--blue-color, var(--primary-color, #03a9f4));
  }
  .alert-details-status-resolved {
    background: var(--secondary-background-color, #f5f5f5);
    color: var(--secondary-text-color, #727272);
  }
  .alert-details-status-icon {
    display: inline-flex;
    width: 28px;
    height: 28px;
    flex: none;
    align-items: center;
    justify-content: center;
    border-radius: var(--ha-border-radius-circle, 50%);
    background: color-mix(in srgb, currentColor 12%, transparent);
  }
  .alert-details-status-icon ha-svg-icon {
    width: 22px;
    height: 22px;
  }
  .alert-details-status-label {
    font-size: var(--ha-font-size-m, 14px);
    font-weight: var(--ha-font-weight-bold, 700);
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .alert-details-card {
    display: block;
    overflow: hidden;
    flex-shrink: 0;
    border-radius: var(--ha-card-border-radius, var(--ha-border-radius-lg, 12px));
    box-shadow: none;
  }
  .alert-details-item dt {
    color: var(--secondary-text-color, #727272);
    font-size: var(--ha-font-size-m, 14px);
    font-weight: var(--ha-font-weight-normal, 400);
  }
  .alert-details-occurrence-panel {
    border-top: 1px solid var(--divider-color);
    --expansion-panel-content-padding: 0;
  }
  .alert-details-occurrence-groups {
    max-height: 240px;
    overflow-y: auto;
    padding: 0 var(--ha-space-4, 16px) var(--ha-space-4, 16px);
  }
  .alert-details-occurrence-date {
    margin: 8px 0;
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-m, 14px);
    font-weight: var(--ha-font-weight-normal, 400);
  }
  .alert-details-occurrences {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px 12px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-variant-numeric: tabular-nums;
  }
  .alert-details-occurrence-unavailable {
    margin: 0;
    padding: 0 16px 16px;
    color: var(--secondary-text-color);
  }
  .alert-details-list {
    width: 100%;
    min-width: 0;
    margin: 0;
  }
  .alert-details-item {
    display: grid;
    min-width: 0;
    grid-template-columns: minmax(120px, .7fr) minmax(0, 1.3fr);
    align-items: start;
    gap: var(--ha-space-4, 16px);
    padding: 7px var(--ha-space-4, 16px);
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    line-height: var(--ha-line-height-normal, 1.4);
  }
  .alert-details-item:last-child {
    border-bottom: 0;
  }
  .alert-details-item dd {
    min-width: 0;
    margin: 0;
    overflow-wrap: anywhere;
    color: var(--primary-text-color, #212121);
    font-size: var(--ha-font-size-m, 14px);
    text-align: end;
    white-space: pre-wrap;
  }
  .alert-details-introduction {
    flex-shrink: 0;
    margin: 0 0 16px;
    padding: 0 4px;
  }
  .alert-details-introduction .alert-details-item {
    display: block;
    padding: 0;
    border: 0;
  }
  .alert-details-introduction dt {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .alert-details-introduction dd {
    text-align: start;
  }
  .alert-details-introduction [data-detail-key="message"] dd {
    font-weight: var(--ha-font-weight-medium, 500);
    margin-bottom: 4px;
  }
  .alert-details-introduction [data-detail-key="condition"] dd {
    color: var(--secondary-text-color);
  }
  .alert-details-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 24px;
    margin: 0;
    padding: 16px;
  }
  .alert-details-grid .alert-details-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 0;
    border: 0;
  }
  .alert-details-grid dd {
    text-align: start;
    max-width: 100%;
  }
  .alert-details-grid [data-detail-key="current-value"] {
    grid-column-start: 1;
  }
  .alert-details-grid .alert-details-item-wide {
    grid-column: 1 / -1;
  }
  .alert-details-card + .alert-details-card {
    margin-top: 12px;
  }
  .alert-details-section-title {
    margin: 0;
    padding: 10px 16px 6px;
    font-size: var(--ha-font-size-m, 14px);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .alert-details-notification {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.3fr);
    gap: 12px;
    margin: 0;
    padding: 8px 16px 12px;
  }
  .alert-details-notification + .alert-details-notification {
    border-top: 1px solid var(--divider-color);
  }
  .alert-details-notification .alert-details-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 0;
    border: 0;
  }
  .alert-details-notification dd {
    text-align: start;
    max-width: 100%;
  }
  .alert-details-identifier {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    flex-shrink: 0;
    gap: 4px 8px;
    margin-top: 8px;
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 12px);
  }
  .alert-details-identifier-value {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
    user-select: text;
  }
  .alert-details-identifier-value[aria-expanded="true"] {
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .alert-details-identifier-value:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }
  .alert-details-copy-status:not(:empty) {
    flex-basis: 100%;
  }
  .alert-details-action {
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .alert-details-timestamp {
    cursor: pointer;
    user-select: none;
    -webkit-tap-highlight-color: rgba(0, 0, 0, 0);
  }
  .alert-details-timestamp:focus-visible {
    border-radius: var(--ha-border-radius-sm, 4px);
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: 2px;
  }
`;
