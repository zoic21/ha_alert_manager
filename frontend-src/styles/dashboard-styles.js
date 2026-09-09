export const dashboardStyles = `
  :host { display: block; }
  :host([hidden]) { display: none !important; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: 8px; }
  ha-card { height: 100%; overflow: hidden; }
  a { color: var(--primary-text-color); text-decoration: none; }
  .tile { display: flex; box-sizing: border-box; align-items: center; gap: 12px; padding: 12px; height: 100%; min-height: 76px; }
  .tile:hover { background: var(--secondary-background-color); }
  .tile:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -3px; border-radius: var(--ha-card-border-radius, 12px); }
  .content { min-width: 0; flex: 1; }
  .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .message { color: var(--secondary-text-color); font-size: 14px; line-height: 20px; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
  .types { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
  ha-icon { color: var(--state-icon-color); flex: none; }
  .types ha-icon { --mdc-icon-size: 20px; }
  .more { display: inline-block; color: var(--primary-color); padding: 8px 0 0; font-size: 14px; }
  .status { padding: 12px; color: var(--secondary-text-color); font-size: 14px; }
`;
