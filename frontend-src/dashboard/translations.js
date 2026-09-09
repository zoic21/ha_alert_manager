import englishDashboardSource from "../../custom_components/alert_manager/translations/en.json" with { type: "json" };
import frenchDashboardSource from "../../custom_components/alert_manager/translations/fr.json" with { type: "json" };

// Only the sections used by the card are embedded by the build. Status messages
// must remain readable even when the integration or connection is unavailable.
const dashboardLanguages = { en: englishDashboardSource, fr: frenchDashboardSource };

export function dashboardText(language, key, params = {}) {
  const read = (source) => key.split(".").reduce((value, part) => value?.[part], source.config_panel);
  const text = read(dashboardLanguages[language?.split("-")[0]] ?? englishDashboardSource)
    ?? read(englishDashboardSource) ?? key;
  return String(text).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => (
    Object.hasOwn(params, name) ? String(params[name] ?? "") : match
  ));
}
