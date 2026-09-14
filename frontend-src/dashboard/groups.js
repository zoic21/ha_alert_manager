import { alertLabelIds } from "../utils/alert-labels.js";

export const DASHBOARD_ICONS = Object.freeze({
  unavailable: "mdi:help-network-outline",
  connectivity: "mdi:lan-disconnect",
  battery: "mdi:battery-low",
  unifi: "mdi:router-wireless",
  execution_errors: "mdi:script-text-outline",
  flapping: "mdi:pulse",
  coherence: "mdi:check-network-outline",
  rule: "mdi:format-list-checks",
});

export function dashboardGroups(alerts, label, hass) {
  const groups = new Map();
  for (const alert of alerts) {
    if (alert.acknowledged || !alert.active_since
      || (label && !alertLabelIds(alert, hass).includes(label))) continue;
    const key = alert.device_id ? `device:${alert.device_id}` : `alert:${alert.id}`;
    if (!groups.has(key)) groups.set(key, { key, alerts: [], latest: 0 });
    const group = groups.get(key);
    group.alerts.push(alert);
    group.latest = Math.max(group.latest, Date.parse(alert.active_since) || 0);
  }
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  return [...groups.values()].map((group) => {
    group.alerts.sort((a, b) => compare(a.id, b.id));
    group.types = [...new Set(group.alerts.map((alert) => alert.type))].sort(compare);
    return group;
  }).sort((a, b) => b.latest - a.latest || compare(a.key, b.key));
}

export function dashboardTarget(group, label = "") {
  const alert = group.alerts[0];
  const params = new URLSearchParams(group.alerts.length === 1
    ? { alert: alert.id } : { device: alert.device_id });
  if (group.alerts.length > 1 && label) params.set("label", label);
  return `/alert-manager/overview?${params}`;
}
