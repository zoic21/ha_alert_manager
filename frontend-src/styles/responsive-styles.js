export const responsiveStyles = `
  /* Medium screens */
  @media (max-width: 1000px) {
    .summary {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .rules-layout.has-editor [data-rules-table-page] {
      --alert-manager-rule-table-width: 100%;
    }
    .rule-editor-backdrop {
      display: block;
      position: fixed;
      z-index: 5;
      inset: var(--header-height, 56px) 0 0;
      background: rgba(0, 0, 0, .32);
    }
  }

  /* Small screens */
  @media (max-width: 700px) {
    main {
      padding: 12px;
    }
    .automatic-grid {
      grid-template-columns: 1fr;
    }
    .summary ha-card {
      padding: 12px;
    }
    .summary strong {
      font-size: 24px;
    }
    .fields, .settings-grid {
      grid-template-columns: 1fr;
    }
    .settings-wide {
      grid-column: auto;
    }
    .panel {
      padding: 15px;
    }
    .coherence-panel {
      padding: 15px;
    }
    .coherence-header {
      align-items: stretch;
      flex-direction: column;
    }
    .coherence-header ha-button {
      width: 100%;
    }
    .actions ha-button {
      width: 100%;
    }
    .rules-header {
      align-items: stretch;
      flex-direction: column;
    }
    .rules-header ha-button {
      width: 100%;
    }
    .ignored-reference-add {
      align-items: stretch;
      flex-direction: column;
    }
    .ignored-reference-add ha-input {
      flex: none;
      max-width: none;
      width: 100%;
    }
    .ignored-reference-add ha-button {
      width: 100%;
      margin-top: 0;
    }
    .history-settings-row {
      grid-template-columns: 1fr;
      grid-template-areas: "label" "input" "action";
    }
    .history-actions {
      align-self: auto;
      align-items: center;
      justify-content: flex-start;
    }
    .delay-row, .pack-map-row {
      grid-template-columns: 1fr;
    }
    .delay-row ha-button, .pack-map-row > ha-button {
      width: 100%;
      margin-top: 0;
    }
    .table-page-top {
      padding: 12px 12px 0;
    }
    hass-tabs-subpage-data-table {
      --data-table-row-height: 72px;
    }
    .selection-actions {
      max-width: 44vw;
      overflow-x: auto;
    }
    ha-card.rule-editor-drawer {
      inset-block-start: var(--header-height, 56px);
      inset-block-end: calc(var(--header-height, 56px) + var(--safe-area-inset-bottom, 0px));
      inset-inline-end: 0;
      width: 100%;
      max-width: none;
      border-width: 0;
      overflow: hidden;
      --ha-card-border-radius: var(--ha-border-radius-square, 0);
    }
    .rule-editor-resize {
      display: none;
    }
    .rule-section-heading, .rule-value-footer {
      align-items: stretch;
      flex-direction: column;
    }
    .rule-value-row {
      grid-template-columns: 1fr;
    }
    .rule-value-row ha-button {
      margin-top: 0;
    }
    .rule-editor-actions {
      flex-wrap: wrap;
    }
    .rule-editor-actions .action-spacer {
      display: none;
    }
  }
`;
