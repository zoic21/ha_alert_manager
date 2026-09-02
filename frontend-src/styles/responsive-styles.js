export const responsiveStyles = `
  /* The companion app already provides the panel toolbar. Its native tabs
   * subpage still reserves another one in narrow mode, so only cancel that
   * duplicate in the app. A narrow desktop browser still needs its toolbar. */
  :host([companion-app][narrow]) #panel-shell {
    margin-block-start: calc(0px - var(--header-height, 56px));
  }

  /* The native bottom sheet is selected from Home Assistant's narrow state,
   * which becomes active before this panel's small-screen media query. Keep
   * these overrides tied to the component so the desktop drawer cannot remain
   * visible inside it at intermediate widths. */
  ha-resizable-bottom-sheet.side-drawer-bottom-sheet {
    position: fixed;
    z-index: 6;
    inset: 0;
    width: 100%;
    height: 100%;
    --side-drawer-mobile-border-radius: var(
      --ha-dialog-border-radius,
      var(--ha-border-radius-2xl, 14px)
    );
    --ha-bottom-sheet-border-radius: var(--side-drawer-mobile-border-radius);
    --ha-bottom-sheet-border-width: 2px;
    --ha-bottom-sheet-border-style: solid;
    --ha-bottom-sheet-border-color: var(--primary-color);
    --ha-bottom-sheet-surface-background: var(--card-background-color);
  }
  .side-drawer-bottom-sheet ha-card.side-drawer {
    position: static;
    width: 100%;
    height: 100%;
    max-width: none;
    border-width: 0;
    overflow: hidden;
    --ha-card-border-radius: var(--side-drawer-mobile-border-radius);
    border-start-start-radius: var(--side-drawer-mobile-border-radius);
    border-start-end-radius: var(--side-drawer-mobile-border-radius);
    border-end-start-radius: 0;
    border-end-end-radius: 0;
  }
  .side-drawer-bottom-sheet .side-drawer-form {
    min-height: 0;
  }
  .side-drawer-bottom-sheet .rule-editor-resize {
    display: none;
  }
  .side-drawer-bottom-sheet .side-drawer-actions {
    flex-wrap: wrap;
  }
  .side-drawer-bottom-sheet .side-drawer-actions .action-spacer {
    display: none;
  }

  /* Medium screens */
  @media (max-width: 1000px) {
    .summary {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .rules-layout.has-editor [data-rules-table-page] {
      --alert-manager-rule-table-width: 100%;
    }
    .side-drawer-backdrop {
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
    .deleted-entity-row {
      grid-template-columns: 1fr;
    }
    .deleted-entity-metadata {
      align-items: flex-start;
      text-align: start;
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
    .config-backup-row {
      grid-template-columns: 1fr;
      padding: 12px 0;
    }
    .config-backup-actions {
      justify-content: flex-start;
    }
    .config-backup-actions ha-button {
      width: auto;
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
    .alert-details-list {
      width: 100%;
      min-width: 0;
    }
    .alert-details-item {
      grid-template-columns: minmax(90px, .7fr) minmax(0, 1.3fr);
      gap: var(--ha-space-3, 12px);
      padding: 7px var(--ha-space-3, 12px);
    }
    .alert-details-summary {
      padding: var(--ha-space-3, 12px);
    }
    .alert-details-status-icon {
      width: 36px;
      height: 36px;
    }
    .rule-editor-resize {
      display: none;
    }
    .rule-section-heading, .rule-value-footer {
      align-items: stretch;
      flex-direction: column;
    }
    .configuration-section-heading {
      align-items: center;
    }
    .rule-value-row {
      grid-template-columns: 1fr;
    }
    .rule-value-row ha-button {
      margin-top: 0;
    }
    .side-drawer-actions {
      flex-wrap: wrap;
    }
    .side-drawer-actions .action-spacer {
      display: none;
    }
  }
`;
