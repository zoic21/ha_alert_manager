export const DASHBOARD_MOBILE_QUERY = "(max-width: 600px)";

export const dashboardStyles = `
  :host { display: block; }
  :host([hidden]) { display: none !important; }
  .dashboard { text-align: left; }
  .dashboard[data-alignment="center"] { text-align: center; }
  .dashboard[data-alignment="right"] { text-align: right; }
  .tiles { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-start; }
  [data-alignment="center"] .tiles { justify-content: center; }
  [data-alignment="right"] .tiles { justify-content: flex-end; }
  .tiles > ha-card, .tile-tail > ha-card { flex: 0 1 300px; max-width: 100%; min-width: 0; height: auto; box-sizing: border-box; text-align: start; }
  ha-card { height: 100%; overflow: hidden; }
  a { color: var(--primary-text-color); text-decoration: none; }
  .tile { display: flex; box-sizing: border-box; align-items: center; gap: 12px; padding: 12px; height: 100%; min-height: 68px; }
  a.tile, a.more { position: relative; --ha-ripple-color: var(--alert-icon-color);
    --ha-ripple-hover-opacity: 0.04; --ha-ripple-pressed-opacity: 0.12; }
  .more ha-ripple { --ha-ripple-color: var(--secondary-text-color); }
  .tile:focus-visible, .more:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -3px; border-radius: var(--ha-card-border-radius, 12px); }
  .content { min-width: 0; flex: 1; }
  .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .message { color: var(--secondary-text-color); font-size: 14px; line-height: 20px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
  .message.with-age { display: flex; gap: 4px; }
  .message-text { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .age { flex: 0 0 auto; max-width: 60%; overflow: hidden; text-overflow: ellipsis; }
  .types { display: flex; gap: 4px; flex-wrap: wrap; flex: 0 0 auto; max-width: 60px; align-items: center; }
  ha-icon { color: var(--alert-icon-color); flex: none; border-radius: 50%; padding: 8px;
    background: color-mix(in srgb, var(--alert-icon-color) 12%, transparent); }
  .types ha-icon { --mdc-icon-size: 20px; padding: 4px; }
  .tile-tail { display: flex; gap: 8px; flex: 0 1 auto; min-width: 0; max-width: 100%; }
  .tile-tail > ha-card:not(.overflow) { width: 300px; }
  .tile-tail > .overflow { flex: 0 0 auto; align-self: center; --ha-card-border-radius: 24px;
    background: transparent; border: none; box-shadow: none; }
  .more { display: flex; align-items: center; justify-content: center; gap: 4px; box-sizing: border-box;
    height: 44px; min-width: 64px; padding: 0 12px; color: var(--secondary-text-color); font-size: 16px; font-weight: 500; }
  .more ha-icon { color: inherit; background: none; padding: 0; }
  .status { padding: 12px; color: var(--secondary-text-color); font-size: 14px; }
  [data-style="bubble"] { --bubble-base-color: var(--ha-card-background, var(--card-background-color)); }
  [data-style="bubble"] .tiles ha-card { --ha-card-border-radius: 34px;
    background: color-mix(in srgb, var(--alert-icon-color) 14%, var(--bubble-base-color));
    border: none; box-shadow: none; }
  [data-style="bubble"] .tile { min-height: 62px; padding: 8px; gap: 10px; }
  .bubble-icon { position: relative; display: grid; place-items: center; flex: 0 0 44px;
    width: 44px; height: 44px; border-radius: 50%;
    background: color-mix(in srgb, var(--alert-icon-color) 6%, var(--bubble-base-color)); }
  .bubble-icon ha-icon { padding: 0; background: none; }
  .bubble-count { position: absolute; top: -3px; right: -2px; display: grid; place-items: center;
    box-sizing: border-box; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 10px;
    font-size: 11px; line-height: 18px; font-weight: 500; color: var(--primary-text-color);
    background: color-mix(in srgb, var(--alert-icon-color) 28%, var(--bubble-base-color)); }
  [data-style="bubble"] .message { font-size: 12px; line-height: 18px; }
  [data-style="bubble"] .tile-tail > .overflow {
    background: color-mix(in srgb, var(--secondary-text-color) 10%, var(--bubble-base-color)); }
  [data-style="bubble"] .more { min-width: 44px; padding: 0 10px; font-size: 14px; }
  @media ${DASHBOARD_MOBILE_QUERY} {
    .tiles > ha-card, .tiles > .tile-tail { flex: 0 0 100%; }
    .tile-tail > ha-card:not(.overflow) { flex: 1 1 0; width: 0; }
  }
`;
