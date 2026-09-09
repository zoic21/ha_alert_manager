export const dashboardStyles = `
  :host { display: block; }
  :host([hidden]) { display: none !important; }
  .dashboard { text-align: left; }
  .dashboard[data-alignment="center"] { text-align: center; }
  .dashboard[data-alignment="right"] { text-align: right; }
  .tiles { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-start; }
  [data-alignment="center"] .tiles { justify-content: center; }
  [data-alignment="right"] .tiles { justify-content: flex-end; }
  .tiles > ha-card { flex: 0 1 300px; max-width: 100%; min-width: 0; height: auto; box-sizing: border-box; text-align: start; }
  ha-card { height: 100%; overflow: hidden; }
  a { color: var(--primary-text-color); text-decoration: none; }
  .tile { display: flex; box-sizing: border-box; align-items: center; gap: 12px; padding: 12px; height: 100%; min-height: 68px; }
  a.tile, a.more { position: relative; --ha-ripple-color: var(--alert-icon-color);
    --ha-ripple-hover-opacity: 0.04; --ha-ripple-pressed-opacity: 0.12; }
  .more ha-ripple { --ha-ripple-color: var(--secondary-text-color); }
  .startup { color: var(--secondary-text-color); }
  .startup ha-icon { color: var(--state-inactive-color, var(--secondary-text-color)); background: none; }
  .tile:focus-visible, .more:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -3px; border-radius: var(--ha-card-border-radius, 12px); }
  .content { min-width: 0; flex: 1; }
  .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .message { color: var(--secondary-text-color); font-size: 14px; line-height: 20px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
  .types { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
  ha-icon { color: var(--alert-icon-color); flex: none; border-radius: 50%; padding: 8px;
    background: color-mix(in srgb, var(--alert-icon-color) 12%, transparent); }
  .types ha-icon { --mdc-icon-size: 20px; padding: 4px; }
  .tiles > .overflow { flex: 0 0 auto; align-self: center; --ha-card-border-radius: 24px;
    background: transparent; border: none; box-shadow: none; }
  .more { display: flex; align-items: center; justify-content: center; gap: 4px; box-sizing: border-box;
    height: 44px; min-width: 64px; padding: 0 12px; color: var(--secondary-text-color); font-size: 16px; font-weight: 500; }
  .more ha-icon { color: inherit; background: none; padding: 0; }
  .status { padding: 12px; color: var(--secondary-text-color); font-size: 14px; }
`;
