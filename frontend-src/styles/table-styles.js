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
  ha-dialog.alert-details-dialog {
    --mdc-dialog-min-width: min(560px, calc(100vw - 32px));
    --mdc-dialog-max-width: 640px;
  }
  .alert-details-summary {
    display: flex;
    align-items: center;
    gap: var(--ha-space-4, 16px);
    margin-bottom: var(--ha-space-4, 16px);
    padding: var(--ha-space-4, 16px);
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
    width: 44px;
    height: 44px;
    flex: none;
    align-items: center;
    justify-content: center;
    border-radius: var(--ha-border-radius-circle, 50%);
    background: color-mix(in srgb, currentColor 12%, transparent);
  }
  .alert-details-status-icon ha-svg-icon {
    width: 26px;
    height: 26px;
  }
  .alert-details-summary-text {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: var(--ha-space-1, 4px);
  }
  .alert-details-status-label {
    font-size: var(--ha-font-size-s, 12px);
    font-weight: var(--ha-font-weight-bold, 700);
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .alert-details-entity {
    overflow: hidden;
    color: var(--primary-text-color, #212121);
    font-size: var(--ha-font-size-xl, 22px);
    font-weight: var(--ha-font-weight-bold, 700);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .alert-details-item dt {
    color: var(--secondary-text-color, #727272);
    font-size: var(--ha-font-size-s, 12px);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .alert-details-list {
    width: 100%;
    min-width: 0;
    margin: 0;
  }
  .alert-details-item {
    display: grid;
    min-width: 0;
    grid-template-columns: minmax(100px, .45fr) minmax(0, 1.55fr);
    gap: var(--ha-space-4, 16px);
    padding: var(--ha-space-2, 8px) 0;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }
  .alert-details-item:last-child {
    border-bottom: 0;
  }
  .alert-details-item dd {
    min-width: 0;
    margin: 0;
    overflow-wrap: anywhere;
    color: var(--primary-text-color, #212121);
    line-height: var(--ha-line-height-normal, 1.4);
    white-space: pre-wrap;
  }
`;
