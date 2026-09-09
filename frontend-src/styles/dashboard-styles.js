export const dashboardStyles = `
  :host { display: block; }
  :host([hidden]) { display: none !important; }
  .dashboard { text-align: left; }
  .dashboard[data-alignment="center"] { text-align: center; }
  .dashboard[data-alignment="right"] { text-align: right; }
  .tiles { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-start; }
  [data-alignment="center"] .tiles { justify-content: center; }
  [data-alignment="right"] .tiles { justify-content: flex-end; }
  .tiles > ha-card { flex: 0 1 300px; max-width: 100%; min-width: 0; height: auto; box-sizing: border-box; text-align: start;
    box-shadow: var(--ha-card-box-shadow, 0 2px 4px color-mix(in srgb, var(--primary-text-color) 8%, transparent)); }
  ha-card { height: 100%; overflow: hidden; }
  a { color: var(--primary-text-color); text-decoration: none; }
  .tile { display: flex; box-sizing: border-box; align-items: center; gap: 12px; padding: 12px; height: 100%; min-height: 76px; }
  .tile:hover { background: var(--secondary-background-color); }
  .tile:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -3px; border-radius: var(--ha-card-border-radius, 12px); }
  .content { min-width: 0; flex: 1; }
  .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .message { color: var(--secondary-text-color); font-size: 14px; line-height: 20px; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
  .types { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
  ha-icon { color: var(--alert-icon-color); flex: none; border-radius: 50%; padding: 8px;
    background: color-mix(in srgb, var(--alert-icon-color) 12%, transparent); }
  .types ha-icon { --mdc-icon-size: 20px; padding: 4px; }
  .more { display: inline-block; color: var(--primary-color); padding: 8px 0 0; font-size: 14px; }
  .status { padding: 12px; color: var(--secondary-text-color); font-size: 14px; }
`;
