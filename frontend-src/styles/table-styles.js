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
`;
