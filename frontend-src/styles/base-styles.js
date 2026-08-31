export const baseStyles = `
  /* Host */
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color, #fafafa);
  }

  /* Base elements */
  * {
    box-sizing: border-box;
  }
  main {
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 24px;
  }
  h2 {
    font-size: var(--ha-font-size-xl, 20px);
    font-weight: var(--ha-font-weight-normal, 400);
    line-height: var(--ha-line-height-condensed, 1.4);
    margin: 0 0 6px;
  }
  p {
    margin: 0;
    color: var(--secondary-text-color, #727272);
  }

  /* Summary */
  .summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 20px;
  }
  .summary ha-card, .panel {
    padding: 20px;
  }
  .summary ha-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .summary ha-card[data-action="filter-summary-status"] {
    cursor: pointer;
  }
  .summary ha-card[data-action="filter-summary-status"]:hover {
    background: var(--ha-color-fill-neutral-quiet-hover, var(--secondary-background-color, #f5f5f5));
  }
  .summary ha-card[data-action="filter-summary-status"]:focus-visible {
    outline: var(--wa-focus-ring, 2px solid var(--primary-color, #03a9f4));
    outline-offset: 2px;
  }
  .summary ha-card[data-action="filter-summary-status"][aria-pressed="true"] {
    box-shadow: inset 0 0 0 2px var(--primary-color, #03a9f4);
  }
  .summary strong {
    font-size: 30px;
  }
  .danger {
    color: var(--error-color, #db4437);
  }
  .acknowledged {
    color: var(--blue-color, var(--primary-color, #03a9f4));
  }
  .pending {
    color: var(--warning-color, #f5a623);
  }
`;
