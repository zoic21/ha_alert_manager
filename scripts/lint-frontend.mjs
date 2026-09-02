import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const filenames = [
  "alert-manager-panel.js",
  "api/alert-manager-api.js",
  "components/alert-table.js",
  "components/config-backups.js",
  "components/configuration-drawer.js",
  "components/rule-editor.js",
  "styles/base-styles.js",
  "styles/table-styles.js",
  "styles/settings-styles.js",
  "styles/rule-editor-styles.js",
  "styles/state-styles.js",
  "styles/responsive-styles.js",
  "styles/panel-styles.js",
  "utils/constants.js",
  "utils/escaping.js",
  "utils/formatting.js",
  "utils/table-preferences.js",
  "utils/translations.js",
  "views/automatic.js",
  "views/coherence.js",
  "views/history.js",
  "views/overview.js",
  "views/rules.js",
  "views/settings.js",
];

const sources = new Map();
for (const filename of filenames) {
  const file = new URL(`../frontend-src/${filename}`, import.meta.url);
  const result = spawnSync(process.execPath, ["--check", file.pathname], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    process.stderr.write(result.stderr);
    process.exit(result.status ?? 1);
  }
  sources.set(filename, await readFile(file, "utf8"));
}

const source = [...sources.values()].join("\n");
for (const token of ["eval(", "new Function(", "document.cookie"] ) {
  if (source.includes(token)) throw new Error(`Forbidden frontend construct: ${token}`);
}
const localStorageUses = source.match(/window\.localStorage/g) ?? [];
if (localStorageUses.length !== 6 || source.includes("globalThis.localStorage")) {
  throw new Error("Frontend storage must stay limited to the namespaced table preferences");
}
if (!source.includes("customElements.define")) {
  throw new Error("Panel custom element is not registered");
}
if ((sources.get("alert-manager-panel.js").match(/\n/g) ?? []).length > 750) {
  throw new Error("The panel entry point must remain an orchestrator, not a monolith");
}
if (/\.prototype\s*=|Object\.assign\([^\n]*\.prototype/.test(source)) {
  throw new Error("Frontend responsibilities must use explicit composition");
}
for (const [filename, content] of sources) {
  if (filename !== "api/alert-manager-api.js" && content.includes(".callWS(")) {
    throw new Error(`WebSocket access must go through the API module: ${filename}`);
  }
}

for (const token of ["<button", "<select", "<textarea", "<table", "<thead", "<tbody"]) {
  if (source.includes(token)) {
    throw new Error(`Use a Home Assistant display component instead of ${token}`);
  }
}
for (const token of ["<ha-alert", "<ha-card", "<hass-tabs-subpage-data-table"]) {
  if (!source.includes(token)) throw new Error(`Expected Home Assistant display component: ${token}`);
}
for (const selector of [".monitoring-warning", ".table-wrap", ".rule-row"]) {
  if (source.includes(selector)) throw new Error(`Obsolete custom UI rule remains: ${selector}`);
}
const compactMobileQueries = source.match(/@media\s*\(\s*max-width:\s*700px\s*\)/g) ?? [];
if (compactMobileQueries.length !== 1) {
  throw new Error("Keep the compact mobile rules in a single media query");
}
console.log("Frontend architecture, syntax and safety checks passed");
