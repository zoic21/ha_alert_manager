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

// Accept the original single-label argument as well as the card's current options.
export function dashboardLabels(config = {}) {
  if (typeof config === "string") return { include: config ? [config] : [], exclude: [] };
  return { include: config.labels ?? (config.label ? [config.label] : []),
    exclude: config.exclude_labels ?? [] };
}

export function dashboardName(alert, t = (key) => key) {
  return alert.type === "coherence" ? t("dashboard.coherence")
    : alert.device_name || alert.name || alert.rule_name || alert.entity_id || t("dashboard.alert");
}

export function dashboardGroups(alerts, config = {}, hass, t) {
  const { include, exclude } = dashboardLabels(config);
  const included = new Set(include), excluded = new Set(exclude);
  const groups = new Map();
  for (const alert of alerts) {
    if (alert.acknowledged || !alert.active_since || alert.resolved_at) continue;
    if (included.size || excluded.size) {
      const labels = alertLabelIds(alert, hass);
      if (labels.some((label) => excluded.has(label))
        || (included.size && !labels.some((label) => included.has(label)))) continue;
    }
    const key = config.group_by_device !== false && alert.device_id
      ? `device:${alert.device_id}` : `alert:${alert.id}`;
    if (!groups.has(key)) groups.set(key, { key, alerts: [], latest: null, oldest: null });
    const group = groups.get(key);
    group.alerts.push(alert);
    const activated = Date.parse(alert.active_since);
    if (Number.isFinite(activated)) {
      group.latest = group.latest === null ? activated : Math.max(group.latest, activated);
      group.oldest = group.oldest === null ? activated : Math.min(group.oldest, activated);
    }
  }
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const collator = config.sort === "alphabetical"
    ? new Intl.Collator(hass?.locale?.language, { sensitivity: "base", numeric: true }) : null;
  return [...groups.values()].map((group) => {
    group.alerts.sort((a, b) => compare(a.id, b.id));
    group.types = [...new Set(group.alerts.map((alert) => alert.type))].sort(compare);
    group.name = dashboardName(group.alerts[0], t);
    return group;
  }).sort((a, b) => {
    let order;
    if (config.sort === "alphabetical") order = collator.compare(a.name, b.name);
    else if (config.sort === "oldest") order = (a.oldest ?? Infinity) - (b.oldest ?? Infinity);
    else order = (b.latest ?? -Infinity) - (a.latest ?? -Infinity);
    return order || compare(a.key, b.key);
  });
}

export function dashboardTarget(group, config = {}) {
  const alert = group?.alerts[0];
  const individual = group?.alerts.length === 1;
  const params = new URLSearchParams(!group ? { dashboard: "1" }
    : individual ? { alert: alert.id } : { device: alert.device_id });
  if (!individual) {
    const { include, exclude } = dashboardLabels(config);
    include.forEach((label) => params.append("label", label));
    exclude.forEach((label) => params.append("exclude_label", label));
  }
  return `/alert-manager/overview?${params}`;
}
