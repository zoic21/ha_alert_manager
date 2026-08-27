import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const file = new URL("../frontend-src/alert-manager-panel.js", import.meta.url);
const result = spawnSync(process.execPath, ["--check", file.pathname], {
  encoding: "utf8",
});
if (result.status !== 0) {
  process.stderr.write(result.stderr);
  process.exit(result.status ?? 1);
}

const source = await readFile(file, "utf8");
const forbidden = ["eval(", "new Function(", "document.cookie"];
for (const token of forbidden) {
  if (source.includes(token)) {
    throw new Error(`Forbidden frontend construct: ${token}`);
  }
}
const localStorageUses = source.match(/window\.localStorage/g) ?? [];
if (localStorageUses.length !== 2 || source.includes("globalThis.localStorage")) {
  throw new Error("Frontend storage must stay limited to the namespaced table preferences");
}
if (!source.includes("customElements.define")) {
  throw new Error("Panel custom element is not registered");
}

const forbiddenNativeUi = ["<button", "<select", "<textarea", "<table", "<thead", "<tbody"];
for (const token of forbiddenNativeUi) {
  if (source.includes(token)) {
    throw new Error(`Use a Home Assistant display component instead of ${token}`);
  }
}

const requiredHomeAssistantUi = ["<ha-alert", "<ha-card", "<ha-data-table"];
for (const token of requiredHomeAssistantUi) {
  if (!source.includes(token)) {
    throw new Error(`Expected Home Assistant display component: ${token}`);
  }
}

const obsoleteCss = [".monitoring-warning", ".table-wrap", ".rule-row"];
for (const selector of obsoleteCss) {
  if (source.includes(selector)) {
    throw new Error(`Obsolete custom UI rule remains: ${selector}`);
  }
}

const compactMobileQueries = source.match(/@media\(max-width:700px\)/g) ?? [];
if (compactMobileQueries.length !== 1) {
  throw new Error("Keep the compact mobile rules in a single media query");
}
console.log("Frontend syntax and safety checks passed");
