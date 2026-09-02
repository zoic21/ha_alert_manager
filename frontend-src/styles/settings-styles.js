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
  .settings-form {
    width: 100%;
    max-width: 1120px;
    margin-inline: auto;
  }
  .settings-card {
    display: grid;
    gap: 18px;
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
    justify-content: flex-end;
    border-top: 1px solid var(--divider-color, #ddd);
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
    grid-template-columns: minmax(260px, 420px) auto;
    grid-template-areas: "label ." "input action";
    align-items: center;
    gap: 6px 16px;
  }
  .history-limit-label {
    grid-area: label;
  }
  #history-limit {
    grid-area: input;
  }
  .history-actions {
    grid-area: action;
    align-self: start;
    min-height: 56px;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: nowrap;
  }
  .history-limit-help {
    margin-top: 0;
    max-width: 620px;
  }
  .settings-save-actions {
    justify-content: flex-end;
    margin-top: 4px;
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
    max-width: 520px;
    padding: 8px 24px 20px;
    white-space: pre-line;
  }

  /* Coherence */
  .coherence-panel {
    padding: 20px;
  }
  .coherence-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    padding: 0;
  }
  .coherence-header > div {
    min-width: 0;
  }
  .coherence-header ha-button {
    flex: none;
  }
  .coherence-actions {
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
    gap: 16px;
    width: 100%;
    max-width: 1120px;
    margin-inline: auto;
  }
  .automatic-actions {
    grid-column: 1/-1;
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
`;
