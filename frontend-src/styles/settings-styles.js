export const settingsStyles = `
  /* History and settings */
  .history-empty {
    margin-bottom: 20px;
  }
  .history-empty .empty h2 {
    margin-bottom: 8px;
  }
  .history-empty .empty ha-button {
    margin-top: 16px;
  }
  .settings-page,
  .settings-form,
  .automatic-section {
    width: 100%;
    max-width: 1120px;
    margin-inline: auto;
  }
  .settings-card {
    display: grid;
    gap: 18px;
  }
  .settings-navigation {
    display: grid;
    gap: 12px;
  }
  .settings-navigation h2 {
    margin: 0;
  }
  .settings-navigation-actions {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
  }
  .settings-navigation-actions ha-button {
    width: 100%;
  }
  .settings-scroll-section {
    scroll-margin-block-start: 16px;
  }
  .settings-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 20px 24px;
    max-width: 920px;
  }
  .settings-wide {
    grid-column: 1/-1;
  }
  .configuration-entry {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .configuration-entry ha-button {
    flex: none;
  }
  .settings-configuration-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 12px;
  }
  .settings-configuration-entry {
    min-height: 40px;
    justify-content: flex-start;
  }
  .automatic-configuration-entry {
    min-height: 40px;
    margin-top: 18px;
    padding-top: 12px;
    flex-wrap: wrap;
    justify-content: flex-end;
    border-top: 1px solid var(--divider-color, #ddd);
  }
  .automatic-configuration-entry.has-multiple-configurations {
    justify-content: space-between;
  }
  .fields.configuration-drawer-fields {
    grid-template-columns: 1fr;
    width: 100%;
    margin: 0;
  }
  .fields.configuration-drawer-fields .full {
    grid-column: auto;
  }
  .configuration-section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }
  .configuration-section-heading > div {
    min-width: 0;
    flex: 1;
  }
  .configuration-section-heading small {
    margin-top: 0;
  }
  .configuration-section-heading ha-button {
    flex: none;
  }
  .ignored-reference-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    max-width: 100%;
    padding: 10px 12px;
    border-radius: var(--ha-border-radius-m, 8px);
    background: var(--secondary-background-color, #f5f5f5);
  }
  .ignored-reference-add {
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }
  .ignored-reference-add ha-input {
    flex: 0 1 420px;
  }
  .ignored-reference-add ha-button {
    flex: none;
    margin-top: 8px;
  }
  .history-settings {
    display: grid;
    gap: 8px;
    max-width: 720px;
  }
  .history-settings-row {
    display: grid;
    max-width: 420px;
    align-items: center;
    gap: 6px;
  }
  .history-limit-help {
    margin-top: 0;
    max-width: 620px;
  }
  .settings-fab-positioner {
    display: flex;
    justify-content: flex-end;
  }
  .settings-fab-positioner ha-button[slot="fab"] {
    position: fixed;
    right: unset;
    left: unset;
    bottom: calc(-80px - var(--safe-area-inset-bottom, 0px));
    z-index: 4;
    transition: bottom 0.3s;
    --ha-button-box-shadow: var(--ha-box-shadow-l);
  }
  .settings-fab-positioner ha-button[slot="fab"].dirty {
    bottom: calc(16px + var(--safe-area-inset-bottom, 0px));
  }
  .notification-section-header,
  .notification-profile-row,
  .notification-exception-heading,
  .notification-exceptions-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .notification-section-header > div,
  .notification-profile-summary,
  .notification-exceptions-header > div {
    min-width: 0;
  }
  .notification-profile-list,
  .notification-profile-summary,
  .notification-exception-list {
    display: grid;
    gap: 8px;
  }
  .notification-profile-row {
    min-height: 64px;
    padding: 10px 0;
    border-top: 1px solid var(--divider-color, #ddd);
  }
  .notification-profile-name {
    line-height: 1.4;
  }
  .notification-profile-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    color: var(--secondary-text-color, #727272);
    font-size: var(--ha-font-size-s, 12px);
  }
  .notification-profile-status,
  .notification-profile-usage {
    line-height: 1.4;
  }
  .notification-profile-actions {
    flex: none;
    flex-wrap: wrap;
  }
  .notification-profile-fields,
  .notification-exception-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }
  .fields.configuration-drawer-fields.notification-profile-fields {
    grid-template-columns: 1fr;
    gap: 14px;
  }
  .fields.notification-profile-fields .full {
    grid-column: 1 / -1;
    margin-top: 0;
  }
  .notification-profile-header-toggle {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-inline-end: 8px;
    color: var(--primary-text-color);
    font-size: var(--ha-font-size-m, 14px);
    white-space: nowrap;
  }
  .notification-profile-section {
    margin-top: 20px;
  }
  .notification-profile-section > h3 {
    margin: 0 0 8px;
  }
  .notification-policy-card {
    display: grid;
    grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
    align-items: stretch;
    gap: 16px;
    padding: 12px;
  }
  .notification-policy-switches {
    display: grid;
    align-content: center;
    gap: 4px;
    padding-inline-end: 16px;
    border-inline-end: 1px solid var(--divider-color, #ddd);
  }
  .notification-policy-switches .field {
    justify-content: center;
  }
  .notification-policy-reminder {
    justify-content: center;
  }
  .configuration-drawer-banner {
    flex: none;
    padding: 12px 16px;
    background: var(--card-background-color, #fff);
    border-bottom: 1px solid var(--divider-color, #ddd);
  }
  .notification-profile-error {
    display: block;
  }
  .notification-exceptions-header {
    align-items: flex-start;
  }
  .notification-exception {
    display: grid;
    gap: 12px;
    padding: 12px;
  }
  .notification-exception-reminder.has-custom-value {
    grid-column: 1 / -1;
  }
  .notification-exception-reminder-controls {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
    gap: 16px;
  }
  .notification-exception-reminder.has-custom-value
    .notification-exception-reminder-controls {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .notification-exception h3,
  .notification-exceptions-header h3,
  .side-drawer-section > h3 {
    margin: 0;
  }
  .config-backups {
    display: grid;
    gap: 12px;
  }
  .config-backups h3 {
    margin: 0;
    font-size: var(--ha-font-size-l, 16px);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .config-backups small {
    margin-top: 4px;
  }
  .config-backup-list {
    display: grid;
  }
  .config-backup-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    min-height: 56px;
    border-top: 1px solid var(--divider-color, #ddd);
  }
  .config-backup-details {
    display: flex;
    min-width: 0;
    flex-wrap: wrap;
    gap: 4px 12px;
  }
  .config-backup-details span {
    color: var(--secondary-text-color, #727272);
  }
  .config-backup-actions {
    flex-wrap: wrap;
  }
  .config-backup-confirmation {
    white-space: pre-line;
  }

  /* Coherence */
  .coherence-panel, .history-panel {
    padding: 20px;
  }
  .coherence-header, .history-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    padding: 0;
  }
  .coherence-header > div, .history-header > div {
    min-width: 0;
  }
  .coherence-header ha-button, .history-header ha-button {
    flex: none;
  }
  .coherence-actions, .history-page-actions {
    display: grid;
    flex: none;
    gap: 8px;
  }
  .coherence-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 20px;
    margin-top: 12px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--secondary-text-color, #727272);
    font-size: var(--ha-font-size-s, 12px);
  }
  .coherence-stats .warning {
    color: var(--warning-color, #9a6b00);
  }
  .coherence-scan-date.stale {
    color: var(--error-color, #db4437);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .deleted-entities-description {
    margin: 0 0 16px;
    color: var(--secondary-text-color, #727272);
  }
  .deleted-entities-list {
    display: grid;
  }
  .deleted-entity-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    min-height: 56px;
    padding: 8px 0;
    border-top: 1px solid var(--divider-color, #ddd);
  }
  .deleted-entity-primary, .deleted-entity-metadata {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 3px;
  }
  .deleted-entity-primary code {
    overflow: hidden;
    color: var(--primary-text-color, #212121);
    font-weight: var(--ha-font-weight-medium, 500);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .deleted-entity-primary span, .deleted-entity-metadata {
    color: var(--secondary-text-color, #727272);
    font-size: var(--ha-font-size-s, 12px);
  }
  .deleted-entity-metadata {
    align-items: flex-end;
    text-align: end;
  }

  /* Code */
  code {
    font-family: var(--ha-font-family-code, ui-monospace, SFMono-Regular, monospace);
    font-size: 12px;
    word-break: break-all;
  }

  /* Automatic rules and form controls */
  .stack {
    display: grid;
    gap: 16px;
  }
  .automatic-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0 24px;
  }
  .automatic-section-title {
    margin: 0;
  }
  .category-card {
    min-width: 0;
    padding: 18px 0;
    border-top: 1px solid var(--divider-color, #ddd);
  }
  .category-header {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: start;
    gap: 16px;
  }
  .category-header h2 {
    margin: 0;
  }
  .category-header ha-switch {
    align-self: start;
  }
  .category-card p {
    font-size: 13px;
    margin-top: 4px;
  }
  .fields {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-top: 18px;
  }
  .full {
    grid-column: 1/-1;
    margin-top: 16px;
  }
  .field {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 6px;
  }
  .switch-field-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 16px;
    min-height: 48px;
  }
  .field-label {
    font-size: var(--ha-font-size-m, 14px);
    font-weight: var(--ha-font-weight-normal, 400);
  }
  ha-input, ha-select, ha-selector {
    display: block;
    width: 100%;
    font-weight: var(--ha-font-weight-normal, 400);
  }
  ha-input {
    --ha-input-padding-bottom: 0;
  }
  ha-input > [slot="end"] {
    padding-inline-start: var(--ha-space-2, 8px);
    color: var(--secondary-text-color, #727272);
    white-space: nowrap;
  }
  small {
    display: block;
    margin-top: 8px;
    color: var(--secondary-text-color, #727272);
    font-weight: var(--ha-font-weight-normal, 400);
  }
  .pack-map-list {
    display: grid;
    gap: 10px;
    width: 100%;
    margin-top: 16px;
  }
  .pack-map-heading {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    width: 100%;
    padding: 4px 0 16px;
    border-bottom: 1px solid var(--divider-color, #ddd);
  }
  .pack-map-heading .field-label {
    display: block;
    font-size: var(--ha-font-size-l, 16px);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .pack-map-heading small {
    max-width: none;
    line-height: 1.45;
  }
  .pack-map-empty {
    padding-block: 32px;
  }
  .pack-map-row {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) minmax(120px, 180px) auto;
    gap: 10px;
    width: 100%;
    align-items: start;
  }
  .pack-map-row > ha-button {
    margin-top: 8px;
  }
  .pack-settings-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .pack-settings-values {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: repeat(3, minmax(110px, 1fr));
    align-items: stretch;
    gap: 10px;
  }
  .pack-configuration[hidden],
  .pack-settings-values[hidden] {
    display: none;
  }
  .pack-target-field,
  .pack-setting-field {
    display: grid;
    gap: 6px;
    min-width: 0;
  }
  .pack-setting-field {
    grid-template-rows: 1fr auto;
  }
  .pack-setting-field .field-label {
    line-height: 1.3;
  }
  .pack-source-list {
    display: grid;
    gap: 12px;
    width: 100%;
    margin-top: 16px;
  }
  .pack-source-row {
    display: grid;
    gap: 12px;
    padding: 12px;
    border: 1px solid var(--divider-color, #ddd);
    border-radius: 12px;
  }
`;
